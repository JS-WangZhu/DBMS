import sys
import types
from types import SimpleNamespace

import pytest

from app.services import mysql_session_probe as probe
from app.extensions import db
from app.models.db_asset import DatabaseInstance


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.sql = ""
        self.description = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql):
        self.sql = sql
        self.connection.executed.append(sql)
        if "information_schema.PROCESSLIST" in sql:
            self.description = [(name,) for name in ("ID", "USER", "HOST", "DB", "COMMAND", "TIME", "STATE", "INFO")]

    def fetchone(self):
        if self.sql == "SELECT CONNECTION_ID()":
            return (900,)
        return None

    def fetchall(self):
        if "information_schema.PROCESSLIST" not in self.sql:
            return []
        return [
            (900, "monitor", "localhost", None, "Query", 0, "executing", self.sql),
            (123, "app", "10.0.0.5:50000", "orders", "Query", 65, "Sending data", "SELECT  *\nFROM orders"),
            (124, "system user", "", None, "Connect", 500, "Waiting for source", None),
            (125, "event_scheduler", "localhost", None, "Daemon", 500, "Waiting on empty queue", None),
            (126, "repl", "10.0.0.9:3306", None, "Binlog Dump GTID", 500, "Source has sent all binlog to replica", None),
            (127, "replica_reader", "10.0.0.10:3306", None, "Connect", 500, "Waiting for master to send event", None),
        ]


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.closed = False
        self.ping_count = 0

    def cursor(self):
        return FakeCursor(self)

    def ping(self, reconnect=False):
        assert reconnect is False
        self.ping_count += 1

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def clean_sessions():
    probe.close_all_probe_sessions()
    yield
    probe.close_all_probe_sessions()


def _start(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setitem(sys.modules, "pymysql", types.SimpleNamespace(connect=lambda **_kwargs: connection))
    instance = SimpleNamespace(
        id=7,
        name="mysql-orders",
        access_mode="server",
        resolved_ip="10.0.0.8",
        host_input="mysql.local",
        port=3306,
        username="monitor",
    )
    data = probe.start_probe_session(instance, "secret", user_id=11)
    return connection, data


def test_session_probe_fetches_formats_kills_and_closes(monkeypatch):
    connection, started = _start(monkeypatch)

    result = probe.fetch_processlist(started["token"], user_id=11)
    assert len(result["sessions"]) == 2
    assert {item["user"] for item in result["sessions"]} == {"monitor", "app"}
    assert result["sessions"][0]["is_probe_connection"] is True
    assert result["sessions"][1] == {
        "id": 123,
        "user": "app",
        "host": "10.0.0.5:50000",
        "database": "orders",
        "command": "Query",
        "time_seconds": 65,
        "state": "Sending data",
        "sql": "SELECT * FROM orders",
        "is_probe_connection": False,
    }

    assert probe.kill_process(started["token"], user_id=11, process_id=123) == {"process_id": 123, "killed": True}
    assert "KILL CONNECTION 123" in connection.executed
    assert probe.close_probe_session(started["token"], user_id=11) is True
    assert connection.closed is True


def test_session_probe_protects_probe_connection_and_user(monkeypatch):
    _connection, started = _start(monkeypatch)

    with pytest.raises(probe.SessionProbeError, match="does not belong"):
        probe.fetch_processlist(started["token"], user_id=12)
    with pytest.raises(probe.SessionProbeError, match="cannot kill"):
        probe.kill_process(started["token"], user_id=11, process_id=900)


def test_session_probe_rejects_agent_access_mode():
    instance = SimpleNamespace(id=8, name="remote", access_mode="agent")
    with pytest.raises(probe.SessionProbeError, match="Agent"):
        probe.start_probe_session(instance, "secret", user_id=11)


def test_session_probe_api_flow(client, monkeypatch):
    connection = FakeConnection()
    monkeypatch.setitem(sys.modules, "pymysql", types.SimpleNamespace(connect=lambda **_kwargs: connection))
    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    headers = {"Authorization": f"Bearer {login.get_json()['data']['access_token']}"}
    instance = DatabaseInstance(
        name="mysql-api-probe",
        db_type="mysql",
        host_input="127.0.0.1",
        port=3306,
        username="monitor",
        enabled=True,
        access_mode="server",
    )
    db.session.add(instance)
    db.session.commit()

    started = client.post("/api/v1/mysql/session-probes", json={"instance_id": instance.id}, headers=headers)
    assert started.status_code == 201
    token = started.get_json()["data"]["token"]

    fetched = client.get(f"/api/v1/mysql/session-probes/{token}/processlist", headers=headers)
    assert fetched.status_code == 200
    assert fetched.get_json()["data"]["sessions"][1]["id"] == 123

    killed = client.post(
        f"/api/v1/mysql/session-probes/{token}/kill",
        json={"process_id": 123},
        headers=headers,
    )
    assert killed.status_code == 200

    stopped = client.post(f"/api/v1/mysql/session-probes/{token}/stop", headers=headers)
    assert stopped.status_code == 200
    assert stopped.get_json()["data"]["closed"] is True
    assert connection.closed is True
