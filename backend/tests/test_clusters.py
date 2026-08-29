from app.extensions import db
from app.models.db_asset import DatabaseCluster
from app.models.user import User


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


def test_cluster_stats_are_global_for_regular_user_without_cluster_permissions(app, client):
    regular_user = User(username="dashboard-reader", role="user", status="active", auth_source="local")
    regular_user.set_password("password123")
    db.session.add_all(
        [
            regular_user,
            DatabaseCluster(name="mysql-a", db_type="mysql", business_line="支付", environment="prod"),
            DatabaseCluster(name="mongo-a", db_type="mongodb", business_line="支付", environment="prod"),
            DatabaseCluster(name="redis-a", db_type="redis", business_line="订单", environment="test"),
        ]
    )
    db.session.commit()

    login = client.post(
        "/api/v1/auth/login",
        json={"username": "dashboard-reader", "password": "password123"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.get_json()['data']['access_token']}"}

    response = client.get("/api/v1/clusters/stats", headers=headers)

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["by_business"] == [
        {"name": "支付", "value": 2},
        {"name": "订单", "value": 1},
    ]
    assert {item["name"]: item["value"] for item in payload["by_db_type"]} == {
        "mysql": 1,
        "mongodb": 1,
        "redis": 1,
    }
