from datetime import datetime

from app.extensions import db
from app.models.physical_discovery import PhysicalDiscoveryRun, VCenterConfig


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


def test_manual_run_returns_background_run_id_immediately(client, monkeypatch):
    from app.api.routes import physical_discovery_ops

    headers = _headers(client)
    created = _create(client, headers)
    calls = []
    monkeypatch.setattr(
        physical_discovery_ops,
        "start_discovery_async",
        lambda **kwargs: calls.append(kwargs["vcenter_id"]) or 42,
    )

    response = client.post(
        f"/api/v1/physical-discovery/vcenters/{created['id']}/run",
        headers=headers,
    )

    assert response.status_code == 202
    assert response.get_json()["data"] == {"run_id": 42}
    assert calls == [created["id"]]


def test_single_run_endpoint_exposes_live_counts(client):
    headers = _headers(client)
    with client.application.app_context():
        row = PhysicalDiscoveryRun(
            vcenter_name="vc-live",
            trigger_type="manual",
            status="running",
            started_at=datetime.utcnow(),
            total_count=5,
            success_count=2,
            failed_count=1,
        )
        db.session.add(row)
        db.session.commit()
        run_id = row.id

    response = client.get(f"/api/v1/physical-discovery/runs/{run_id}", headers=headers)

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "running"
    assert response.get_json()["data"]["success_count"] == 2
