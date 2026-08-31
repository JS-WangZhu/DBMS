from app.extensions import db
from app.models.db_asset import DatabaseCluster
from app.models.user import User
from app.models.user_permission import (
    DataSourceGroup,
    DataSourceGroupClusterPermission,
    RoleGroup,
    RoleGroupMenuPermission,
    UserClusterPermission,
    UserDataSourceGroup,
    UserMenuPermission,
    UserRoleGroup,
)


def _login(client, username, password):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['data']['access_token']}"}


def test_user_permission_editor_keeps_direct_and_inherited_menu_permissions_separate(app, client):
    with app.app_context():
        user = User(username="menu-scope-user", role="user", status="active", auth_source="local")
        user.set_password("password123")
        role_group = RoleGroup(name="mysql-readers")
        db.session.add_all([user, role_group])
        db.session.flush()
        db.session.add_all(
            [
                UserMenuPermission(user_id=user.id, menu_key="dashboard"),
                UserRoleGroup(user_id=user.id, role_group_id=role_group.id),
                RoleGroupMenuPermission(role_group_id=role_group.id, menu_key="mysql_instances"),
            ]
        )
        db.session.commit()
        user_id = user.id

    admin_headers = _login(client, "admin", "admin123")
    response = client.get(f"/api/v1/users/permissions/{user_id}", headers=admin_headers)

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["menu_keys"] == ["dashboard"]
    assert payload["inherited_menu_keys"] == ["mysql_instances"]
    assert set(payload["effective_menu_keys"]) == {"dashboard", "mysql_instances"}


def test_current_user_menu_permissions_include_role_group_without_copying_to_direct(app, client):
    with app.app_context():
        user = User(username="effective-menu-user", role="user", status="active", auth_source="local")
        user.set_password("password123")
        role_group = RoleGroup(name="redis-readers")
        db.session.add_all([user, role_group])
        db.session.flush()
        db.session.add_all(
            [
                UserRoleGroup(user_id=user.id, role_group_id=role_group.id),
                RoleGroupMenuPermission(role_group_id=role_group.id, menu_key="redis_instances"),
            ]
        )
        db.session.commit()
        user_id = user.id

    user_headers = _login(client, "effective-menu-user", "password123")
    mine = client.get("/api/v1/users/permissions/me", headers=user_headers)
    assert mine.status_code == 200
    assert mine.get_json()["data"]["menu_keys"] == ["redis_instances"]
    assert mine.get_json()["data"]["direct_menu_keys"] == []

    admin_headers = _login(client, "admin", "admin123")
    # The shared Flask test context keeps g.current_user between requests.
    # Production request contexts are isolated.
    from flask import g

    g.pop("current_user", None)
    saved = client.put(
        f"/api/v1/users/permissions/{user_id}",
        headers=admin_headers,
        json={"menu_keys": ["dashboard"]},
    )
    assert saved.status_code == 200

    with app.app_context():
        direct_keys = [row.menu_key for row in UserMenuPermission.query.filter_by(user_id=user_id).all()]
    assert direct_keys == ["dashboard"]


def test_instance_data_permission_alone_does_not_grant_service_menu(app, client):
    with app.app_context():
        user = User(username="instance-data-only", role="user", status="active", auth_source="local")
        user.set_password("password123")
        cluster = DatabaseCluster(name="data-only-cluster", db_type="mysql")
        db.session.add_all([user, cluster])
        db.session.flush()
        db.session.add(
            UserClusterPermission(user_id=user.id, cluster_id=cluster.id, can_view_instance=True)
        )
        db.session.commit()

    response = client.get(
        "/api/v1/users/permissions/me",
        headers=_login(client, "instance-data-only", "password123"),
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["menu_keys"] == []


def test_session_probe_menu_is_inherited_from_data_source_group(app, client):
    with app.app_context():
        user = User(username="probe-data-source-group", role="user", status="active", auth_source="local")
        user.set_password("password123")
        group = DataSourceGroup(name="mongodb-probe-readers")
        cluster = DatabaseCluster(name="mongodb-probe-group-cluster", db_type="mongodb")
        db.session.add_all([user, group, cluster])
        db.session.flush()
        db.session.add_all(
            [
                UserDataSourceGroup(user_id=user.id, group_id=group.id),
                DataSourceGroupClusterPermission(group_id=group.id, cluster_id=cluster.id, can_query=True),
            ]
        )
        db.session.commit()

    response = client.get(
        "/api/v1/users/permissions/me",
        headers=_login(client, "probe-data-source-group", "password123"),
    )

    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["menu_keys"] == ["mongodb_session_probe"]
    assert payload["direct_menu_keys"] == []
