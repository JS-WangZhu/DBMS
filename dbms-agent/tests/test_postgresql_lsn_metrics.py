import sys
import types
from datetime import datetime

from app.services import instance_probe


class FakeCursor:
    def __init__(self, replication_row):
        self.replication_row = replication_row
        self.query = ""

    def __enter__(self): return self
    def __exit__(self, *_args): return False

    def execute(self, query):
        self.query = query

    def fetchone(self):
        if "SELECT version()" in self.query:
            return ("PostgreSQL 18", "postgres", True, 100, 200)
        if "FROM pg_stat_activity" in self.query:
            return (10, 2, 0)
        if "WITH receiver AS" in self.query:
            return self.replication_row
        if "FROM pg_stat_database" in self.query:
            return (100, 2, 0, 1024)
        raise AssertionError(self.query)


class FakeConnection:
    def __init__(self, row):
        self.cursor_value = FakeCursor(row)
        self.autocommit = False
        self.closed = False

    def cursor(self): return self.cursor_value
    def close(self): self.closed = True


def collect(monkeypatch, row):
    connection = FakeConnection(row)
    monkeypatch.setitem(sys.modules, "psycopg2", types.SimpleNamespace(connect=lambda **_kwargs: connection))
    payload = instance_probe._postgresql(
        {"host_input": "127.0.0.1", "port": 5432, "username": "monitor", "extra_json": {}},
        "secret",
    )
    assert connection.closed is True
    return payload


def test_postgresql_agent_reports_lsn_and_byte_backlog(monkeypatch):
    payload = collect(monkeypatch, (
        "streaming", "0/3000", "0/2800", "0/2000",
        4096, 2048, 2048, 12.3456, False, datetime(2026, 7, 19, 12, 0, 0),
    ))
    assert payload["wal_source_lsn"] == "0/3000"
    assert payload["wal_receive_lsn"] == "0/2800"
    assert payload["wal_replay_lsn"] == "0/2000"
    assert payload["replication_lag_bytes"] == 4096
    assert payload["receive_lag_bytes"] == 2048
    assert payload["replay_lag_bytes"] == 2048
    assert payload["replication_lag_seconds"] == 12.346
    assert payload["wal_receiver_status"] == "streaming"


def test_postgresql_agent_idle_replica_has_zero_lag(monkeypatch):
    payload = collect(monkeypatch, (
        "streaming", "0/3000", "0/3000", "0/3000",
        0, 0, 0, 0, False, datetime(2026, 7, 19, 12, 0, 0),
    ))
    assert payload["replication_lag_bytes"] == 0
    assert payload["replication_lag_seconds"] == 0.0
