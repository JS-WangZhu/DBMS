from app.extensions import db
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.models.user import User
from app.models.user_permission import (
    DataSourceGroup,
    DataSourceGroupClusterPermission,
    UserClusterPermission,
    UserDataSourceGroup,
    UserMenuPermission,
)
from app.services.instance_service import invalidate_instance_list_cache


def _login(client, username, password="password123"):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['data']['access_token']}"}


def _seed_user_and_instances():
    user = User(username="instance-reader", role="user", status="active", auth_source="local")
    user.set_password("password123")
    allowed = DatabaseCluster(name="allowed", db_type="mysql")
    denied = DatabaseCluster(name="denied", db_type="mysql")
    db.session.add_all([user, allowed, denied])
    db.session.flush()
    allowed_instance = DatabaseInstance(
        name="allowed-instance", db_type="mysql", host_input="10.0.0.1", port=3306, cluster_id=allowed.id
    )
    denied_instance = DatabaseInstance(
        name="denied-instance", db_type="mysql", host_input="10.0.0.2", port=3306, cluster_id=denied.id
    )
    db.session.add_all(
        [
            allowed_instance,
            denied_instance,
            UserMenuPermission(user_id=user.id, menu_key="mysql_instances"),
            UserClusterPermission(user_id=user.id, cluster_id=allowed.id, can_view_instance=True),
            UserClusterPermission(user_id=user.id, cluster_id=denied.id, can_query=True),
        ]
    )
    db.session.commit()
    invalidate_instance_list_cache()
    return allowed.id, denied.id, allowed_instance.id, denied_instance.id


def test_instance_reader_only_sees_clusters_and_instances_with_view_permission(app, client):
    with app.app_context():
        allowed_cluster_id, denied_cluster_id, allowed_instance_id, denied_instance_id = _seed_user_and_instances()

    headers = _login(client, "instance-reader")
    clusters = client.get("/api/v1/clusters?db_type=mysql&action=view_instance", headers=headers)
    instances = client.get("/api/v1/mysql/instances?page_size=200", headers=headers)
    cluster_manage_instances = client.get(
        "/api/v1/instances?db_type=mysql&action=view_instance",
        headers=headers,
    )
    health = client.post(
        "/api/v1/monitoring/instances/health",
        headers=headers,
        json={"db_type": "mysql", "instance_ids": [allowed_instance_id, denied_instance_id]},
    )

    assert clusters.status_code == 200
    assert [row["id"] for row in clusters.get_json()["data"]] == [allowed_cluster_id]
    assert instances.status_code == 200
    assert [row["id"] for row in instances.get_json()["data"]["items"]] == [allowed_instance_id]
    assert cluster_manage_instances.status_code == 200
    assert [row["id"] for row in cluster_manage_instances.get_json()["data"]] == [allowed_instance_id]
    assert health.status_code == 200
    assert {int(value) for value in health.get_json()["data"]} == {allowed_instance_id}

    denied_detail = client.get(f"/api/v1/mysql/instances/{denied_instance_id}/detail", headers=headers)
    assert denied_detail.status_code == 403
    assert denied_cluster_id != allowed_cluster_id


def test_instance_menu_without_cluster_view_permission_cannot_list_any_instances(app, client):
    with app.app_context():
        _seed_user_and_instances()
        for permission in UserClusterPermission.query.all():
            permission.can_view_instance = False
        db.session.commit()

    response = client.get("/api/v1/mysql/instances", headers=_login(client, "instance-reader"))

    assert response.status_code == 200
    assert response.get_json()["data"]["items"] == []


def test_instance_view_permission_from_data_source_group_is_effective(app, client):
    with app.app_context():
        user = User(username="group-reader", role="user", status="active", auth_source="local")
        user.set_password("password123")
        cluster = DatabaseCluster(name="group-allowed", db_type="redis")
        group = DataSourceGroup(name="instance-readers")
        db.session.add_all([user, cluster, group])
        db.session.flush()
        instance = DatabaseInstance(
            name="redis-reader", db_type="redis", host_input="10.0.1.1", port=6379, cluster_id=cluster.id
        )
        db.session.add_all(
            [
                instance,
                UserMenuPermission(user_id=user.id, menu_key="redis_instances"),
                UserDataSourceGroup(user_id=user.id, group_id=group.id),
                DataSourceGroupClusterPermission(
                    group_id=group.id, cluster_id=cluster.id, can_view_instance=True
                ),
            ]
        )
        db.session.commit()
        instance_id = instance.id

    response = client.get("/api/v1/redis/instances", headers=_login(client, "group-reader"))

    assert response.status_code == 200
    assert [row["id"] for row in response.get_json()["data"]["items"]] == [instance_id]


def test_instance_reader_cannot_trigger_instance_mutations(app, client):
    with app.app_context():
        allowed_cluster_id, _denied_cluster_id, _allowed_instance_id, _denied_instance_id = _seed_user_and_instances()
    headers = _login(client, "instance-reader")

    create = client.post(
        "/api/v1/mysql/instances",
        headers=headers,
        json={"name": "forbidden", "host_input": "10.0.0.3", "port": 3306, "cluster_id": allowed_cluster_id},
    )
    collect = client.post(f"/api/v1/clusters/{allowed_cluster_id}/health/collect", headers=headers)

    assert create.status_code == 403
    assert collect.status_code == 403


def test_data_source_permission_api_persists_instance_view_permission(app, client):
    with app.app_context():
        user = User(username="permission-target", role="user", status="active", auth_source="local")
        user.set_password("password123")
        cluster = DatabaseCluster(name="permission-cluster", db_type="postgresql")
        db.session.add_all([user, cluster])
        db.session.commit()
        user_id, cluster_id = user.id, cluster.id

    admin_headers = _login(client, "admin", "admin123")
    saved = client.put(
        f"/api/v1/data-source-permissions/users/{user_id}",
        headers=admin_headers,
        json={
            "group_ids": [],
            "direct_permissions": [{"cluster_id": cluster_id, "can_view_instance": True}],
        },
    )
    loaded = client.get(f"/api/v1/data-source-permissions/users/{user_id}", headers=admin_headers)

    assert saved.status_code == 200
    assert loaded.status_code == 200
    assert loaded.get_json()["data"]["direct_permissions"] == [
        {
            "cluster_id": cluster_id,
            "can_query": False,
            "can_change": False,
            "can_execute": False,
            "can_view_instance": True,
        }
    ]
