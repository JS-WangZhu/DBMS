import sys
import types
from types import SimpleNamespace

import pytest

from app.services import postgresql_session_probe as probe


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.sql = ""
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.sql = sql
        self.params = params
        self.connection.executed.append((sql, params))

    def fetchall(self):
        if "pg_catalog.pg_stat_activity" not in self.sql:
            return []
        return [
            (900, "monitor", "postgres", None, "dbms-session-probe", "active", None, None, 0, self.sql),
            (123, "app", "orders", "10.0.0.5", "order-api", "active", "Lock", "transactionid", 65, "SELECT  *\nFROM orders"),
            (124, "app", "orders", "10.0.0.6", "worker", "idle", "Client", "ClientRead", 5, None),
        ]

    def fetchone(self):
        if "pg_terminate_backend" in self.sql:
            return (True,)
        return None


class FakeConnection:
    def __init__(self):
        self.autocommit = False
        self.closed = False
        self.executed = []

    def get_backend_pid(self):
        return 900

    def cursor(self):
        return FakeCursor(self)

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def clean_sessions():
    probe.close_all_probe_sessions()
    yield
    probe.close_all_probe_sessions()


def _start(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setitem(sys.modules, "psycopg2", types.SimpleNamespace(connect=lambda **_kwargs: connection))
    instance = SimpleNamespace(id=7, name="pg-orders", access_mode="server", resolved_ip="10.0.0.8", host_input="pg.local", port=5432, username="monitor", extra_json={"database": "postgres", "sslmode": "require"})
    return connection, probe.start_probe_session(instance, "secret", user_id=11)


def test_session_probe_fetches_formats_terminates_and_closes(monkeypatch):
    connection, started = _start(monkeypatch)
    assert connection.autocommit is True
    result = probe.fetch_sessions(started["token"], user_id=11)
    assert "::bigint, query FROM pg_catalog.pg_stat_activity" in connection.executed[0][0]
    assert "::bigint), query" not in connection.executed[0][0]
    assert result["sessions"][0]["is_probe_connection"] is True
    assert result["sessions"][1] == {
        "id": 123, "user": "app", "database": "orders", "client": "10.0.0.5",
        "application_name": "order-api", "state": "active", "wait_event_type": "Lock",
        "wait_event": "transactionid", "time_seconds": 65, "sql": "SELECT * FROM orders",
        "is_probe_connection": False,
    }
    assert probe.terminate_backend(started["token"], user_id=11, process_id=123) == {"process_id": 123, "terminated": True}
    assert connection.executed[-1][1] == (123,)
    assert probe.close_probe_session(started["token"], user_id=11) is True
    assert connection.closed is True


def test_session_probe_protects_probe_connection_and_user(monkeypatch):
    _connection, started = _start(monkeypatch)
    with pytest.raises(probe.SessionProbeError, match="does not belong"):
        probe.fetch_sessions(started["token"], user_id=12)
    with pytest.raises(probe.SessionProbeError, match="cannot terminate"):
        probe.terminate_backend(started["token"], user_id=11, process_id=900)


def test_session_probe_rejects_agent_access_mode():
    instance = SimpleNamespace(id=8, name="remote", access_mode="agent")
    with pytest.raises(probe.SessionProbeError, match="Agent"):
        probe.start_probe_session(instance, "secret", user_id=11)
