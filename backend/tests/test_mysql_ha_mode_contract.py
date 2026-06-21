from app.extensions import db
from app.models.db_asset import DatabaseCluster


def _admin_headers(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert response.status_code == 200
    token = response.get_json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_mysql_cluster_defaults_to_no_ha_management(client):
    headers = _admin_headers(client)
    response = client.post(
        "/api/v1/clusters",
        json={"name": "ha-default", "db_type": "mysql", "namespace": "team-ha"},
        headers=headers,
    )

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["ha_mode"] == "none"
    assert "ha_switch_enabled" not in data
    assert DatabaseCluster.query.get(data["id"]).ha_mode == "none"


def test_mysql_cluster_accepts_valid_ha_modes(client):
    headers = _admin_headers(client)
    create_response = client.post(
        "/api/v1/clusters",
        json={
            "name": "ha-orc",
            "db_type": "mysql",
            "namespace": "team-ha",
            "ha_mode": "orc",
        },
        headers=headers,
    )

    assert create_response.status_code == 201
    cluster_id = create_response.get_json()["data"]["id"]
    assert create_response.get_json()["data"]["ha_mode"] == "orc"

    update_response = client.patch(
        f"/api/v1/clusters/{cluster_id}",
        json={"ha_mode": "dbms"},
        headers=headers,
    )

    assert update_response.status_code == 200
    assert update_response.get_json()["data"]["ha_mode"] == "dbms"
    assert DatabaseCluster.query.get(cluster_id).ha_mode == "dbms"


def test_cluster_rejects_invalid_ha_mode(client):
    headers = _admin_headers(client)
    create_response = client.post(
        "/api/v1/clusters",
        json={
            "name": "ha-invalid",
            "db_type": "mysql",
            "namespace": "team-ha",
            "ha_mode": "external",
        },
        headers=headers,
    )
    assert create_response.status_code == 400

    valid_response = client.post(
        "/api/v1/clusters",
        json={"name": "ha-valid", "db_type": "mysql", "namespace": "team-ha"},
        headers=headers,
    )
    cluster_id = valid_response.get_json()["data"]["id"]
    update_response = client.patch(
        f"/api/v1/clusters/{cluster_id}",
        json={"ha_mode": "external"},
        headers=headers,
    )
    assert update_response.status_code == 400


def test_non_mysql_cluster_forces_ha_mode_none(client):
    headers = _admin_headers(client)
    response = client.post(
        "/api/v1/clusters",
        json={
            "name": "mongo-ha-mode",
            "db_type": "mongodb",
            "namespace": "team-ha",
            "ha_mode": "dbms",
        },
        headers=headers,
    )

    assert response.status_code == 201
    data = response.get_json()["data"]
    assert data["ha_mode"] == "none"
    assert DatabaseCluster.query.get(data["id"]).ha_mode == "none"


def test_mcp_cluster_data_uses_ha_mode(app):
    from app.services.mcp_status import _cluster_data

    cluster = DatabaseCluster(
        name="mcp-ha",
        db_type="mysql",
        namespace="team-ha",
        ha_mode="orc",
    )
    db.session.add(cluster)
    db.session.commit()

    data = _cluster_data(cluster)

    assert data["ha_mode"] == "orc"
    assert "ha_switch_enabled" not in data
