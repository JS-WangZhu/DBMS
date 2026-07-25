import sys
import types
from types import SimpleNamespace

import pytest

from app.services import mongodb_session_probe as probe


class FakeAdmin:
    def __init__(self, connection):
        self.connection = connection

    def command(self, command):
        self.connection.commands.append(command)
        if command == "ping":
            return {"ok": 1}
        if command.get("currentOp"):
            return {"inprog": [
                {"opid": 10, "op": "command", "ns": "orders.$cmd", "client": "10.0.0.5:50000", "appName": "orders-api", "secs_running": 65, "active": True, "command": {"find": "orders", "filter": {"status": "open"}}},
                {"opid": 11, "op": "command", "ns": "admin.$cmd", "appName": self.connection.appname, "secs_running": 0, "active": True, "command": {"currentOp": 1}},
            ]}
        return {"ok": 1}


class FakeClient:
    def __init__(self, *_args, **kwargs):
        self.appname = kwargs.get("appname")
        self.commands = []
        self.closed = False
        self.admin = FakeAdmin(self)

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def clean_sessions():
    probe.close_all_probe_sessions()
    yield
    probe.close_all_probe_sessions()


def _start(monkeypatch):
    clients = []
    def create_client(*args, **kwargs):
        client = FakeClient(*args, **kwargs)
        clients.append(client)
        return client
    monkeypatch.setitem(sys.modules, "pymongo", types.SimpleNamespace(MongoClient=create_client))
    instance = SimpleNamespace(id=7, name="mongo-orders", access_mode="server", resolved_ip="10.0.0.8", host_input="mongo.local", port=27017, username="monitor", extra_json={})
    return clients, probe.start_probe_session(instance, "secret", user_id=11)


def test_session_probe_fetches_formats_kills_and_closes(monkeypatch):
    clients, started = _start(monkeypatch)
    result = probe.fetch_operations(started["token"], user_id=11)
    assert [item["id"] for item in result["sessions"]] == ["10", "11"]
    assert result["sessions"][0]["command"] == {"find": "orders", "filter": {"status": "open"}}
    assert result["sessions"][1]["is_probe_connection"] is True
    assert probe.kill_operation(started["token"], user_id=11, operation_id="10") == {"operation_id": "10", "killed": True}
    assert {"killOp": 1, "op": 10} in clients[0].commands
    assert probe.close_probe_session(started["token"], user_id=11) is True
    assert clients[0].closed is True


def test_session_probe_protects_user_and_probe_operation(monkeypatch):
    _clients, started = _start(monkeypatch)
    with pytest.raises(probe.SessionProbeError, match="does not belong"):
        probe.fetch_operations(started["token"], user_id=12)
    with pytest.raises(probe.SessionProbeError, match="cannot kill"):
        probe.kill_operation(started["token"], user_id=11, operation_id="11")


def test_session_probe_rejects_agent_access_mode():
    with pytest.raises(probe.SessionProbeError, match="Agent"):
        probe.start_probe_session(SimpleNamespace(id=8, name="remote", access_mode="agent"), "secret", user_id=11)
