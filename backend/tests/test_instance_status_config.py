from app.models.instance_status_config import InstanceStatusConfig


def _admin_headers(client):
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    token = resp.get_json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_instance_status_config_has_defaults(client):
    headers = _admin_headers(client)
    resp = client.get("/api/v1/instances/status-config", headers=headers)

    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["metric_refresh_timeout_seconds"] == 8
    assert data["probe_poll_interval_seconds"] == 30

    row = InstanceStatusConfig.query.first()
    assert row is not None
    assert row.metric_refresh_timeout_seconds == 8
    assert row.probe_poll_interval_seconds == 30


def test_update_instance_status_config_clamps_minimums(client):
    headers = _admin_headers(client)
    resp = client.put(
        "/api/v1/instances/status-config",
        json={
            "metric_refresh_timeout_seconds": 0,
            "probe_poll_interval_seconds": 3,
        },
        headers=headers,
    )

    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["metric_refresh_timeout_seconds"] == 1
    assert data["probe_poll_interval_seconds"] == 10
