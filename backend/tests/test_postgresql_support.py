from types import SimpleNamespace

from app.models.monitor_snapshot import MonitorSnapshotPostgreSQL, snapshot_model_for_db
from app.services.collectors import COLLECTOR_MAP
from app.services.inspection_service import DEFAULT_THRESHOLDS, _extract_issues

def _admin_headers(client):
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200
    token = response.get_json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_postgresql_cluster_and_instance_management(client):
    headers = _admin_headers(client)
    cluster_response = client.post(
        "/api/v1/clusters",
        json={"name": "pg-cluster", "db_type": "postgresql", "namespace": "database"},
        headers=headers,
    )
    assert cluster_response.status_code == 201
    cluster_id = cluster_response.get_json()["data"]["id"]

    instance_response = client.post(
        "/api/v1/postgresql/instances",
        json={
            "name": "pg-primary",
            "host_input": "127.0.0.1",
            "port": 5432,
            "username": "postgres",
            "cluster_id": cluster_id,
            "extra_json": {"database": "postgres", "sslmode": "prefer"},
        },
        headers=headers,
    )
    assert instance_response.status_code == 201
    body = instance_response.get_json()["data"]
    assert body["db_type"] == "postgresql"
    assert body["port"] == 5432

    list_response = client.get("/api/v1/postgresql/instances", headers=headers)
    assert list_response.status_code == 200
    items = list_response.get_json()["data"]["items"]
    assert [item["name"] for item in items] == ["pg-primary"]



def test_postgresql_snapshot_and_collector_are_registered():
    assert snapshot_model_for_db("postgresql") is MonitorSnapshotPostgreSQL
    assert "postgresql" in COLLECTOR_MAP


def test_postgresql_basic_inspection_metrics():
    instance = SimpleNamespace(db_type="postgresql")
    payload = {
        "ok": True,
        "ping_ok": True,
        "connection_usage_pct": 95,
        "replication_role": "standby",
        "replication_lag_seconds": 90,
        "replay_paused": True,
        "lock_waiting_connections": 2,
    }

    issues = _extract_issues(instance, payload, dict(DEFAULT_THRESHOLDS))
    issue_keys = {item["issue_key"] for item in issues}

    assert issue_keys == {
        "postgresql_connection_high",
        "postgresql_replication_lag",
        "postgresql_replay_paused",
        "postgresql_lock_wait",
    }


def test_postgresql_healthy_payload_has_no_database_issue():
    instance = SimpleNamespace(db_type="postgresql")
    payload = {
        "ok": True,
        "ping_ok": True,
        "connection_usage_pct": 20,
        "replication_role": "primary",
        "replication_lag_seconds": None,
        "replay_paused": False,
        "lock_waiting_connections": 0,
    }

    assert _extract_issues(instance, payload, dict(DEFAULT_THRESHOLDS)) == []


def test_postgresql_idle_standby_does_not_report_time_lag():
    instance = SimpleNamespace(db_type="postgresql")
    payload = {
        "replication_role": "standby",
        "replication_lag_seconds": 4281.151,
        "replication_lag_bytes": 0,
        "wal_receiver_status": "streaming",
        "replay_paused": False,
        "lock_waiting_connections": 0,
    }
    issues = _extract_issues(instance, payload, dict(DEFAULT_THRESHOLDS))
    assert "postgresql_replication_lag" not in {item["issue_key"] for item in issues}


def test_postgresql_wal_backlog_and_receiver_failure_are_reported():
    instance = SimpleNamespace(db_type="postgresql")
    backlog = {
        "replication_role": "standby",
        "replication_lag_seconds": 90,
        "replication_lag_bytes": 8192,
        "wal_receiver_status": "streaming",
    }
    issues = _extract_issues(instance, backlog, dict(DEFAULT_THRESHOLDS))
    assert "postgresql_replication_lag" in {item["issue_key"] for item in issues}
    assert "8192 bytes" in str(next(item for item in issues if item["issue_key"] == "postgresql_replication_lag"))

    disconnected = {
        "replication_role": "standby",
        "replication_lag_seconds": None,
        "replication_lag_bytes": None,
        "wal_receiver_status": None,
    }
    issues = _extract_issues(instance, disconnected, dict(DEFAULT_THRESHOLDS))
    assert "postgresql_replication_receiver" in {item["issue_key"] for item in issues}
