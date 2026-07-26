import sys
import types
from types import SimpleNamespace

from app.services.collectors import doris as collector


class FakeCursor:
    def __init__(self):
        self.statement = None
        self.description = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement):
        self.statement = statement
        if statement == "SHOW FRONTENDS":
            self.description = [("Name",), ("Alive",)]
        elif statement == "SHOW BACKENDS":
            self.description = [("BackendId",), ("Alive",)]

    def fetchone(self):
        return (1, "Apache Doris 3.0")

    def fetchall(self):
        if self.statement == "SHOW FRONTENDS":
            return [("fe-1", "true"), ("fe-2", "false")]
        if self.statement == "SHOW BACKENDS":
            return [(1, True), (2, False)]
        return []


class FakeConnection:
    def __init__(self):
        self.closed = False

    def cursor(self):
        return FakeCursor()

    def close(self):
        self.closed = True


def test_doris_server_collects_frontend_backend_and_host_status(monkeypatch):
    connection = FakeConnection()
    monkeypatch.setitem(
        sys.modules,
        "pymysql",
        types.SimpleNamespace(connect=lambda **_kwargs: connection),
    )
    monkeypatch.setattr(
        collector,
        "collect_node_exporter_metrics",
        lambda _instance: {"host_cpu_usage_pct": 12.5},
    )
    instance = SimpleNamespace(
        resolved_ip="10.20.1.30",
        host_input="doris-fe",
        port=9030,
        username="root",
    )

    payload = collector.collect_doris_status(instance, "secret")

    assert payload["ok"] is True
    assert payload["ping_ok"] is True
    assert payload["version"] == "Apache Doris 3.0"
    assert payload["frontend_count"] == 2
    assert payload["frontend_alive_count"] == 1
    assert payload["backend_count"] == 2
    assert payload["backend_alive_count"] == 1
    assert payload["frontends"][0]["Name"] == "fe-1"
    assert payload["backends"][0]["BackendId"] == 1
    assert payload["warnings"] == []
    assert payload["host_cpu_usage_pct"] == 12.5
    assert connection.closed is True

