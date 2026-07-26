import json
from datetime import datetime
from types import SimpleNamespace

from app.extensions import db
from app.models.backup_agent import BackupAgent
from app.models.db_asset import DatabaseInstance


def test_mcp_status_includes_whitelisted_instance_and_physical_machine_metadata(app, monkeypatch):
    from app.services import mcp_status

    monkeypatch.setattr(mcp_status, "latest_snapshots_by_instance_ids", lambda *_args: {})

    with app.app_context():
        agent = BackupAgent(name="probe-a", url="http://agent.example", api_key="agent-secret")
        db.session.add(agent)
        db.session.flush()
        instance = DatabaseInstance(
            name="mysql-a",
            db_type="mysql",
            host_input="db.example.com",
            resolved_ip="10.20.1.8",
            port=3306,
            access_mode="agent",
            probe_agent_id=agent.id,
            extra_json={
                "domain": "db.example.com",
                "physical_address": "192.0.2.10",
                "physical_discovery_mode": "auto",
                "physical_discovery_source": "vc-a",
                "physical_discovered_at": "2026-07-08T01:02:03",
                "internal_secret": "must-not-leak",
            },
        )
        db.session.add(instance)
        db.session.commit()

        row = mcp_status.build_mcp_instance_status()["instances"][0]

        assert row["host_domain"] == "db.example.com"
        assert row["access_mode"] == "agent"
        assert row["probe_agent"] == {"id": agent.id, "name": "probe-a"}
        assert row["created_at"] == instance.created_at.isoformat()
        assert row["physical_machine"] == {
            "address": "192.0.2.10",
            "discovery_mode": "auto",
            "discovery_source": "vc-a",
            "discovered_at": "2026-07-08T01:02:03",
        }
        assert "extra_json" not in row
        assert "must-not-leak" not in json.dumps(row)
        assert "agent-secret" not in json.dumps(row)


def test_mcp_status_has_stable_physical_machine_defaults(app, monkeypatch):
    from app.services import mcp_status

    monkeypatch.setattr(mcp_status, "latest_snapshots_by_instance_ids", lambda *_args: {})

    with app.app_context():
        instance = DatabaseInstance(
            name="redis-a",
            db_type="redis",
            host_input="10.20.1.9",
            port=6379,
            extra_json={"physical_discovery_mode": "unexpected"},
        )
        db.session.add(instance)
        db.session.commit()

        row = mcp_status.build_mcp_instance_status()["instances"][0]

        assert row["host_domain"] is None
        assert row["probe_agent"] is None
        assert row["physical_machine"] == {
            "address": None,
            "discovery_mode": "auto",
            "discovery_source": None,
            "discovered_at": None,
        }


def test_mcp_status_exposes_redis_operational_metrics(app, monkeypatch):
    from app.services import mcp_status

    with app.app_context():
        instance = DatabaseInstance(name="redis-metrics", db_type="redis", host_input="10.20.1.10", port=6379)
        db.session.add(instance)
        db.session.commit()
        snapshot = SimpleNamespace(
            id=1,
            metric_type="status",
            collected_at=datetime.now(),
            payload_json={
                "ok": True,
                "ping_ok": True,
                "maxclients": 1000,
                "connection_usage_pct": 12.5,
                "used_memory_peak": 1024,
                "keyspace_db_count": 2,
                "keyspace_hits": 80,
                "keyspace_misses": 20,
                "redis_mode": "cluster",
                "cluster_state": "ok",
                "cluster_info": {"cluster_slots_assigned": "16384"},
                "replication_source": "redis-primary:6379",
                "connected_slaves": 2,
            },
        )
        monkeypatch.setattr(
            mcp_status,
            "latest_snapshots_by_instance_ids",
            lambda *_args: {instance.id: snapshot},
        )

        row = mcp_status.build_mcp_instance_status()["instances"][0]

        assert row["metrics"] == {
            "maxclients": 1000,
            "connection_usage_pct": 12.5,
            "used_memory_peak": 1024,
            "keyspace_db_count": 2,
            "keyspace_hits": 80,
            "keyspace_misses": 20,
            "redis_mode": "cluster",
            "cluster_state": "ok",
            "cluster_info": {"cluster_slots_assigned": "16384"},
            "connected_slaves": 2,
            "replication_source": "redis-primary:6379",
        }

def test_mcp_metrics_expose_all_safe_collector_status_fields():
    from app.services import mcp_status

    common_keys = {
        "warnings",
        "node_exporter_enabled",
        "node_exporter_mode",
        "node_exporter_status",
        "node_exporter_error",
        "host_cpu_usage_pct",
        "host_cpu_cores",
        "host_memory_usage_pct",
        "host_memory_total_bytes",
        "host_data_disk_usage_pct",
        "host_data_disk_mountpoint",
        "host_data_disk_device",
        "host_data_disk_size_bytes",
        "host_disk_io_latency_ms",
        "host_disk_io_device",
        "host_disk_entries",
        "host_net_rates",
    }
    database_keys = {
        "mysql": {
            "uptime", "started_at", "threads_connected", "connections_current",
            "threads_running", "max_connections", "connection_usage_pct",
            "connections_usage_pct", "questions_total", "com_commit_total",
            "com_rollback_total", "qps", "tps", "lock_waits", "read_only",
            "super_read_only", "effective_read_only", "mgr_member_role",
            "mgr_member_state", "mgr_group_name", "mgr_members",
            "replica_io_running", "replica_sql_running", "replica_source_host",
            "replica_source_resolved_ip", "replica_source_port",
            "seconds_behind_master",
        },
        "mongodb": {
            "process", "mongo_topology", "started_at", "uptime",
            "connections_current", "connections_max", "connection_usage_pct",
            "connections_usage_pct", "lock_waits", "repl_lag_seconds",
            "replication_lag_seconds", "op_insert", "op_query", "op_update",
            "op_delete", "op_read", "op_write", "op_read_pct", "op_write_pct",
            "cache_used_pct", "connections", "mem", "repl",
        },
        "redis": {
            "uptime", "redis_mode", "cluster_enabled", "cluster_state",
            "cluster_info", "master_host", "master_port", "master_link_status",
            "connected_slaves", "replication_source", "replication_lag_seconds",
            "connected_clients", "maxclients", "connection_usage_pct",
            "connections_usage_pct",
            "used_memory", "used_memory_human", "maxmemory", "maxmemory_human",
            "memory_usage_pct", "used_memory_peak", "used_memory_peak_human",
            "keyspace_total_keys", "keyspace_db_count", "keyspace_hits",
            "keyspace_misses",
        },
        "postgresql": {
            "database", "uptime", "in_recovery", "replication_lag_seconds",
            "replication_lag_bytes", "receive_lag_bytes", "replay_lag_bytes",
            "wal_current_lsn", "wal_source_lsn", "wal_receive_lsn",
            "wal_replay_lsn", "wal_receiver_status", "wal_last_message_at",
            "replay_paused", "replica_count", "connections",
            "connections_current", "active_connections",
            "lock_waiting_connections", "max_connections",
            "connection_usage_pct", "connections_usage_pct", "xact_commit",
            "xact_rollback", "deadlocks", "database_size_bytes",
        },
        "doris": {
            "frontend_count", "frontend_alive_count", "backend_count",
            "backend_alive_count", "frontends", "backends",
        },
    }

    for db_type, db_keys in database_keys.items():
        expected_keys = common_keys | db_keys
        payload = {key: {"sample": key} for key in expected_keys}
        payload["internal_secret"] = "must-not-leak"

        metrics = mcp_status._metrics(payload, db_type)

        assert set(metrics) == expected_keys
        assert "internal_secret" not in metrics


def test_mcp_alerts_accept_mongodb_replication_lag_name():
    from app.services import mcp_status

    alerts = mcp_status._alerts(
        instance=None,
        payload={"repl_lag_seconds": 90},
        snapshot=SimpleNamespace(),
        status="running",
        age=0,
    )

    assert "replication_lag" in alerts
