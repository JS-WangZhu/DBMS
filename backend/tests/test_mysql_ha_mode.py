from unittest.mock import patch

import pytest

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


def _create_cluster(mode):
    cluster = DatabaseCluster(
        name=f"mysql-{mode}",
        db_type="mysql",
        namespace="team-ha",
        business_line="team-ha",
        ha_mode=mode,
    )
    db.session.add(cluster)
    db.session.commit()
    return cluster


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("none", "not enabled for DBMS HA management"),
        ("orc", "managed by Orchestrator"),
    ],
)
def test_ha_switch_rejects_non_dbms_modes(client, mode, message):
    cluster = _create_cluster(mode)
    response = client.post(
        f"/api/v1/clusters/{cluster.id}/ha/switch",
        json={"switch_type": "normal", "target_instance_id": 1},
        headers=_admin_headers(client),
    )

    assert response.status_code == 400
    assert message in response.get_json()["message"]


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("none", "not enabled for DBMS HA management"),
        ("orc", "managed by Orchestrator"),
    ],
)
def test_ha_switch_stream_rejects_non_dbms_modes(client, mode, message):
    cluster = _create_cluster(mode)
    response = client.post(
        f"/api/v1/clusters/{cluster.id}/ha/switch/stream",
        json={"switch_type": "normal", "target_instance_id": 1},
        headers=_admin_headers(client),
    )

    assert response.status_code == 400
    assert message in response.get_json()["message"]


def test_dbms_mode_reaches_existing_ha_execution(client):
    cluster = _create_cluster("dbms")
    expected = {"status": "success", "new_master_instance_id": 1}

    with patch(
        "app.api.routes.clusters._execute_ha_switch",
        return_value=expected,
    ) as execute:
        response = client.post(
            f"/api/v1/clusters/{cluster.id}/ha/switch",
            json={"switch_type": "normal", "target_instance_id": 1},
            headers=_admin_headers(client),
        )

    assert response.status_code == 200
    assert response.get_json()["data"] == expected
    execute.assert_called_once()


@pytest.mark.parametrize("mode", ["none", "orc"])
def test_topology_remains_readable_outside_dbms_mode(client, mode):
    cluster = _create_cluster(mode)
    expected = {
        "cluster": cluster.to_dict(),
        "ha_domain": None,
        "current_master_instance_id": None,
        "nodes": [],
    }

    with patch(
        "app.api.routes.clusters.build_cluster_topology",
        return_value=expected,
    ):
        response = client.get(
            f"/api/v1/clusters/{cluster.id}/ha/topology",
            headers=_admin_headers(client),
        )

    assert response.status_code == 200
    assert response.get_json()["data"]["nodes"] == []
