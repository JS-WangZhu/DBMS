from app.extensions import db
from app.models.db_asset import DatabaseCluster


def _admin_headers(client):
    resp = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert resp.status_code == 200
    token = resp.get_json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_create_and_update_cluster_namespace(client):
    headers = _admin_headers(client)

    create_resp = client.post(
        "/api/v1/clusters",
        json={"name": "c1", "db_type": "mysql", "namespace": "team-a", "description": "demo"},
        headers=headers,
    )
    assert create_resp.status_code == 201
    cluster_id = create_resp.get_json()["data"]["id"]
    assert create_resp.get_json()["data"]["namespace"] == "team-a"

    update_resp = client.patch(f"/api/v1/clusters/{cluster_id}", json={"namespace": "team-b"}, headers=headers)
    assert update_resp.status_code == 200
    assert update_resp.get_json()["data"]["namespace"] == "team-b"

    row = DatabaseCluster.query.get(cluster_id)
    assert row is not None
    assert row.namespace == "team-b"


def test_create_cluster_requires_namespace(client):
    headers = _admin_headers(client)
    resp = client.post("/api/v1/clusters", json={"name": "c2", "db_type": "mysql"}, headers=headers)
    assert resp.status_code == 400
    assert resp.get_json()["ok"] is False

