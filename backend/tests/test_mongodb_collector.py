import sys
import types
from types import SimpleNamespace


def test_mongodb_collector_authenticates_against_admin_only(monkeypatch):
    from app.services.collectors import mongodb

    calls = []

    class FakeDatabase:
        def command(self, name):
            if name == "ping":
                return {"ok": 1}
            if name in {"hello", "isMaster"}:
                return {"isWritablePrimary": True}
            if name in {"replSetGetStatus", "replSetGetConfig"}:
                raise RuntimeError("not a replica set")
            if name == "serverStatus":
                return {"connections": {}, "opcounters": {}}
            raise AssertionError(f"unexpected command: {name}")

    class FakeMongoClient:
        def __init__(self, host, port, **options):
            calls.append((host, port, options))
            self.admin = FakeDatabase()

        def server_info(self):
            return {"version": "7.0.0"}

        def close(self):
            return None

    monkeypatch.setitem(sys.modules, "pymongo", types.SimpleNamespace(MongoClient=FakeMongoClient))
    monkeypatch.setattr(mongodb, "collect_node_exporter_metrics", lambda _instance: {})

    instance = SimpleNamespace(
        id=1,
        resolved_ip="10.100.60.69",
        host_input="mongo.example.test",
        port=27017,
        username="dbms",
        extra_json={"auth_source": "local", "auth_db": "custom"},
    )

    result = mongodb.collect_mongodb_status(instance, "secret")

    assert result["ok"] is True
    assert len(calls) == 1
    assert calls[0][2]["authSource"] == "admin"
