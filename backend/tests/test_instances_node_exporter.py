from app.models.db_asset import DatabaseInstance


def _admin_headers(client):
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    token = resp.get_json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_instance_has_default_node_exporter_config(client):
    headers = _admin_headers(client)
    resp = client.post(
        "/api/v1/mysql/instances",
        json={
            "name": "mysql-node-1",
            "host_input": "127.0.0.1",
            "port": 3306,
            "username": "root",
            "password": "demo",
        },
        headers=headers,
    )
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    node_exporter = (data.get("extra_json") or {}).get("node_exporter") or {}
    assert node_exporter.get("enabled") is True
    assert node_exporter.get("mode") == "same_host"
    assert node_exporter.get("port") == 9100


def test_update_instance_node_exporter_custom_address(client):
    headers = _admin_headers(client)
    create_resp = client.post(
        "/api/v1/mysql/instances",
        json={
            "name": "mysql-node-2",
            "host_input": "127.0.0.1",
            "port": 3307,
            "username": "root",
            "password": "demo",
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    instance_id = create_resp.get_json()["data"]["id"]

    patch_resp = client.patch(
        f"/api/v1/instances/{instance_id}",
        json={
            "extra_json": {
                "custom_meta": {"owner": "dba"},
                "node_exporter": {"mode": "custom", "address": "10.0.0.10:9100"},
            }
        },
        headers=headers,
    )
    assert patch_resp.status_code == 200
    payload = patch_resp.get_json()["data"]
    node_exporter = payload["extra_json"]["node_exporter"]
    assert node_exporter["mode"] == "custom"
    assert node_exporter["address"] == "10.0.0.10:9100"
    assert node_exporter["enabled"] is True
    assert payload["extra_json"]["custom_meta"]["owner"] == "dba"

    row = DatabaseInstance.query.get(instance_id)
    assert row is not None
    assert row.extra_json["node_exporter"]["mode"] == "custom"
    assert row.extra_json["node_exporter"]["address"] == "10.0.0.10:9100"

