from datetime import datetime, timedelta

from app.extensions import db
from app.models.db_asset import DatabaseInstance
from app.models.monitor_snapshot import MonitorSnapshotMongoDB, MonitorSnapshotMySQL


def _admin_headers(client):
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['data']['access_token']}"}


def test_mysql_performance_returns_chronological_status_series(client):
    headers = _admin_headers(client)
    instance = DatabaseInstance(
        name="mysql-performance",
        db_type="mysql",
        host_input="mysql.local",
        resolved_ip="10.0.0.8",
        port=3306,
        username="monitor",
    )
    db.session.add(instance)
    db.session.flush()
    now = datetime.now()
    db.session.add_all([
        MonitorSnapshotMySQL(
            instance_id=instance.id,
            metric_type="status",
            collected_at=now - timedelta(minutes=2),
            payload_json={
                "host_cpu_usage_pct": 25.5,
                "host_memory_usage_pct": 60.0,
                "host_data_disk_usage_pct": 70.0,
                "host_net_rates": [{"device": "eth0", "rx_bps": 100, "tx_bps": 40}],
                "threads_connected": 12,
                "threads_running": 3,
                "lock_waits": 1,
            },
        ),
        MonitorSnapshotMySQL(
            instance_id=instance.id,
            metric_type="status",
            collected_at=now - timedelta(minutes=1),
            payload_json={
                "host_cpu_usage_pct": 30.0,
                "host_net_rates": [
                    {"device": "eth0", "rx_bps": 200, "tx_bps": 80},
                    {"device": "eth1", "rx_bps": 50, "tx_bps": 20},
                ],
                "threads_connected": 15,
                "threads_running": 4,
                "lock_waits": 2,
            },
        ),
    ])
    db.session.commit()

    response = client.get(
        f"/api/v1/monitoring/instance/{instance.id}/performance?hours=1",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["instance"] == {
        "id": instance.id,
        "name": "mysql-performance",
        "host": "10.0.0.8",
        "port": 3306,
    }
    assert len(data["points"]) == 2
    assert data["points"][0]["cpu_usage_pct"] == 25.5
    assert data["points"][1]["network_rx_bps"] == 250.0
    assert data["points"][1]["network_tx_bps"] == 100.0
    assert data["points"][1]["sessions"] == 15
    assert data["points"][1]["connections_current"] == 15
    assert data["points"][1]["wiredtiger_cache_used_pct"] is None
    assert data["points"][1]["lock_waits"] == 2
    assert data["points"][0]["collected_at"] < data["points"][1]["collected_at"]


def test_mysql_performance_rejects_invalid_hours(client):
    headers = _admin_headers(client)
    instance = DatabaseInstance(name="mysql-hours", db_type="mysql", host_input="127.0.0.1", port=3306)
    db.session.add(instance)
    db.session.commit()

    response = client.get(
        f"/api/v1/monitoring/instance/{instance.id}/performance?hours=bad",
        headers=headers,
    )

    assert response.status_code == 400



def test_mongodb_performance_returns_resources_cache_and_connections(client):
    headers = _admin_headers(client)
    instance = DatabaseInstance(
        name="mongodb-performance",
        db_type="mongodb",
        host_input="mongodb.local",
        resolved_ip="10.0.0.18",
        port=27017,
        username="monitor",
    )
    db.session.add(instance)
    db.session.flush()
    now = datetime.now()
    db.session.add(
        MonitorSnapshotMongoDB(
            instance_id=instance.id,
            metric_type="status",
            collected_at=now,
            payload_json={
                "host_cpu_usage_pct": 18.5,
                "host_memory_usage_pct": 52.0,
                "host_data_disk_usage_pct": 61.0,
                "host_net_rates": [{"device": "eth0", "rx_bps": 320, "tx_bps": 180}],
                "cache_used_pct": 43.25,
                "connections_current": 27,
            },
        )
    )
    db.session.commit()

    response = client.get(
        f"/api/v1/monitoring/instance/{instance.id}/performance?hours=6",
        headers=headers,
    )

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["instance"]["name"] == "mongodb-performance"
    assert data["hours"] == 6
    assert len(data["points"]) == 1
    point = data["points"][0]
    assert point["cpu_usage_pct"] == 18.5
    assert point["memory_usage_pct"] == 52.0
    assert point["disk_usage_pct"] == 61.0
    assert point["network_rx_bps"] == 320.0
    assert point["network_tx_bps"] == 180.0
    assert point["wiredtiger_cache_used_pct"] == 43.25
    assert point["connections_current"] == 27
    assert point["sessions"] is None
