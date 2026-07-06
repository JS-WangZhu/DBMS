from app.models.physical_discovery import VCenterConfig


def _headers(client):
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    return {"Authorization": f"Bearer {response.get_json()['data']['access_token']}"}


def _create(client, headers):
    return client.post("/api/v1/physical-discovery/vcenters", headers=headers, json={
        "name": "vc-a", "address": "vc-a.example.com", "cidrs": ["10.20.0.0/16"],
        "username": "readonly", "password": "secret",
    }).get_json()["data"]


def test_vcenter_can_be_updated_disabled_and_soft_deleted(client):
    headers = _headers(client)
    created = _create(client, headers)

    response = client.patch(
        f"/api/v1/physical-discovery/vcenters/{created['id']}",
        headers=headers,
        json={"name": "vc-renamed", "enabled": False, "cidrs": ["10.21.0.0/16"]},
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["enabled"] is False
    assert response.get_json()["data"]["cidrs"] == ["10.21.0.0/16"]

    response = client.delete(f"/api/v1/physical-discovery/vcenters/{created['id']}", headers=headers)
    assert response.status_code == 200
    assert VCenterConfig.query.get(created["id"]).deleted is True


def test_runs_endpoint_returns_paginated_shape(client):
    response = client.get("/api/v1/physical-discovery/runs", headers=_headers(client))

    assert response.status_code == 200
    assert response.get_json()["data"] == {"items": [], "total": 0, "page": 1, "page_size": 20}
