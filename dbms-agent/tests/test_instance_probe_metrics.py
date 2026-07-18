import importlib.util
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "services" / "instance_probe.py"
SPEC = importlib.util.spec_from_file_location("agent_instance_probe", MODULE_PATH)
instance_probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(instance_probe)


class FakeMysqlCursor:
    description = None

    def __init__(self, read_only="OFF", super_read_only="OFF", replica=True):
        self.sql = ""
        self.read_only = read_only
        self.super_read_only = super_read_only
        self.replica = replica

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql):
        self.sql = sql
        if "replication_group_members" in sql:
            raise RuntimeError("not MGR")

    def fetchone(self):
        if self.sql == "SELECT 1, VERSION()":
            return (1, "8.0.36")
        if "SHOW GLOBAL STATUS" in self.sql:
            values = {
                "Threads_connected": "12",
                "Threads_running": "3",
                "Uptime": "100",
                "Questions": "500",
                "Com_commit": "40",
                "Com_rollback": "10",
                "Innodb_row_lock_current_waits": "2",
            }
            key = next((key for key in values if key in self.sql), None)
            return (key, values[key]) if key else None
        if "SHOW GLOBAL VARIABLES" in self.sql:
            values = {
                "max_connections": "200",
                "super_read_only": self.super_read_only,
                "read_only": self.read_only,
            }
            key = next((key for key in values if key in self.sql), None)
            return (key, values[key]) if key else None
        if self.sql == "SHOW REPLICA STATUS" and self.replica:
            self.description = [
                ("Replica_IO_Running",),
                ("Replica_SQL_Running",),
                ("Seconds_Behind_Source",),
                ("Source_Host",),
                ("Source_Port",),
            ]
            return ("Yes", "Yes", 4, "mysql-primary", 3306)
        return None

    def fetchall(self):
        return []


class FakeMysqlConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.closed = False

    def cursor(self):
        return self._cursor

    def close(self):
        self.closed = True


def install_fake_pymysql(monkeypatch, cursor):
    connection = FakeMysqlConnection(cursor)
    module = types.SimpleNamespace(connect=lambda **_kwargs: connection)
    monkeypatch.setitem(sys.modules, "pymysql", module)
    return connection


def test_mysql_agent_collects_operational_and_replication_metrics(monkeypatch):
    monkeypatch.setattr(instance_probe, "_collect_host_metrics", lambda _instance: {
        "host_cpu_usage_pct": 35.0,
        "host_memory_usage_pct": 62.0,
        "host_data_disk_usage_pct": 71.0,
        "host_net_rates": [{"device": "eth0", "rx_bps": 1024.0, "tx_bps": 512.0}],
    })
    connection = install_fake_pymysql(monkeypatch, FakeMysqlCursor())
    payload = instance_probe._mysql(
        {"host_input": "127.0.0.1", "port": 3306, "username": "monitor"},
        "secret",
    )

    assert payload["threads_connected"] == 12
    assert payload["threads_running"] == 3
    assert payload["max_connections"] == 200
    assert payload["qps"] == 5.0
    assert payload["tps"] == 0.5
    assert payload["lock_waits"] == 2
    assert payload["replication_role"] == "slave"
    assert payload["replica_io_running"] is True
    assert payload["replica_sql_running"] is True
    assert payload["seconds_behind_master"] == 4
    assert payload["replica_source_host"] == "mysql-primary"
    assert payload["started_at"]
    assert connection.closed is True
    assert payload["host_cpu_usage_pct"] == 35.0
    assert payload["host_memory_usage_pct"] == 62.0
    assert payload["host_data_disk_usage_pct"] == 71.0
    assert payload["host_net_rates"][0]["rx_bps"] == 1024.0


def test_mysql_agent_preserves_unknown_read_only_state(monkeypatch):
    monkeypatch.setattr(instance_probe, "_collect_host_metrics", lambda _instance: {})
    install_fake_pymysql(monkeypatch, FakeMysqlCursor(read_only=None, super_read_only=None, replica=False))
    payload = instance_probe._mysql(
        {"host_input": "127.0.0.1", "port": 3306, "username": "monitor"},
        "secret",
    )

    assert payload["effective_read_only"] is None
    assert payload["replication_role"] == "unknown"


class FakeMongoAdmin:
    def command(self, command):
        if command == "ping":
            return {"ok": 1.0}
        if command == "serverStatus":
            return {
                "process": "mongod",
                "uptime": 120,
                "connections": {"current": 20, "available": 80},
                "opcounters": {"insert": 4, "query": 10, "getmore": 2, "update": 3, "delete": 1},
                "globalLock": {"currentQueue": {"total": 2}},
                "wiredTiger": {"cache": {"bytes currently in the cache": 25, "maximum bytes configured": 100}},
                "mem": {"resident": 128},
            }
        if command == "hello":
            return {"setName": "rs0", "secondary": True, "hosts": ["mongo-1:27017", "mongo-2:27017"]}
        if command == "replSetGetStatus":
            now = datetime.now()
            return {
                "set": "rs0",
                "myState": 2,
                "members": [
                    {"stateStr": "PRIMARY", "optimeDate": now},
                    {"stateStr": "SECONDARY", "self": True, "optimeDate": now - timedelta(seconds=3)},
                ],
            }
        if command == "replSetGetConfig":
            return {"config": {"_id": "rs0", "version": 5}}
        raise AssertionError(command)


class FakeMongoClient:
    last_options = None

    def __init__(self, _host, _port, **options):
        FakeMongoClient.last_options = options
        self.admin = FakeMongoAdmin()
        self.closed = False

    def server_info(self):
        return {"version": "7.0.9"}

    def close(self):
        self.closed = True


def test_mongodb_agent_collects_full_database_metrics(monkeypatch):
    monkeypatch.setitem(sys.modules, "pymongo", types.SimpleNamespace(MongoClient=FakeMongoClient))
    payload = instance_probe._mongodb(
        {
            "host_input": "mongo-2",
            "port": 27017,
            "username": "monitor",
            "extra_json": {"auth_source": "admin", "direct_connection": True, "tls": True},
        },
        "secret",
    )

    assert payload["mongo_role"] == "secondary"
    assert payload["mongo_topology"] == "replica_set"
    assert payload["connections_current"] == 20
    assert payload["connections_max"] == 100
    assert payload["lock_waits"] == 2
    assert payload["repl_lag_seconds"] == 3
    assert payload["cache_used_pct"] == 25.0
    assert payload["op_read"] == 12
    assert payload["op_write"] == 8
    assert payload["op_read_pct"] == 60.0
    assert payload["repl"]["myState"] == 2
    assert payload["repl"]["rs_conf"]["config"]["version"] == 5
    assert FakeMongoClient.last_options["directConnection"] is True
    assert FakeMongoClient.last_options["tls"] is True
    assert not any(key.startswith("host_") for key in payload)
