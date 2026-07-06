def _admin_headers(client):
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    token = response.get_json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_global_config_defaults_and_updates(client):
    headers = _admin_headers(client)
    response = client.get("/api/v1/physical-discovery/config", headers=headers)

    assert response.status_code == 200
    assert response.get_json()["data"]["enabled"] is False

    response = client.put(
        "/api/v1/physical-discovery/config",
        json={"enabled": True, "poll_interval_minutes": 15, "connect_timeout_seconds": 8, "batch_size": 200},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["poll_interval_minutes"] == 15


def test_vcenter_create_masks_password_and_rejects_overlapping_cidr(client):
    headers = _admin_headers(client)
    payload = {
        "name": "vc-a",
        "address": "vc-a.example.com",
        "port": 443,
        "cidrs": ["10.20.1.8/16"],
        "username": "readonly",
        "password": "secret",
        "verify_ssl": True,
    }
    response = client.post("/api/v1/physical-discovery/vcenters", json=payload, headers=headers)

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["cidrs"] == ["10.20.0.0/16"]
    assert data["password_configured"] is True
    assert "password" not in data

    payload.update({"name": "vc-b", "address": "vc-b.example.com", "cidrs": ["10.20.8.0/24"]})
    response = client.post("/api/v1/physical-discovery/vcenters", json=payload, headers=headers)
    assert response.status_code == 400
    assert "overlap" in response.get_json()["message"]
