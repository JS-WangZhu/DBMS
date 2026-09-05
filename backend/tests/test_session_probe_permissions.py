from datetime import datetime, timedelta

from app.extensions import db
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.models.user import User
from app.models.user_permission import UserClusterPermission
from app.services.instance_service import invalidate_instance_list_cache


def _login(client, username):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": "password123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['data']['access_token']}"}


def _seed_probe_user(db_type, username):
    user = User(username=username, role="user", status="active", auth_source="local")
    user.set_password("password123")
    allowed = DatabaseCluster(name=f"{db_type}-probe-allowed", db_type=db_type)
    denied = DatabaseCluster(name=f"{db_type}-probe-denied", db_type=db_type)
    db.session.add_all([user, allowed, denied])
    db.session.flush()
    allowed_instance = DatabaseInstance(
        name=f"{db_type}-probe-instance",
        db_type=db_type,
        host_input="127.0.0.1",
        port=3306 if db_type == "mysql" else 27017,
        cluster_id=allowed.id,
        enabled=True,
        access_mode="server",
    )
    denied_instance = DatabaseInstance(
        name=f"{db_type}-denied-instance",
        db_type=db_type,
        host_input="127.0.0.2",
        port=3306 if db_type == "mysql" else 27017,
        cluster_id=denied.id,
        enabled=True,
        access_mode="server",
    )
    permission = UserClusterPermission(user_id=user.id, cluster_id=allowed.id, can_query=True)
    db.session.add_all(
        [
            allowed_instance,
            denied_instance,
            permission,
        ]
    )
    db.session.commit()
    invalidate_instance_list_cache()
    return user.id, allowed.id, allowed_instance.id, denied_instance.id, permission.id


def _started_payload(token):
    return {"token": token, "expires_at": (datetime.now() + timedelta(minutes=5)).isoformat()}


def test_mysql_session_probe_requires_query_and_change_permissions(app, client, monkeypatch):
    from app.api.routes import mysql as mysql_routes

    with app.app_context():
        user_id, cluster_id, instance_id, denied_instance_id, permission_id = _seed_probe_user(
            "mysql", "mysql-probe-user"
        )
    headers = _login(client, "mysql-probe-user")

    permissions = client.get("/api/v1/users/permissions/me", headers=headers)
    assert "mysql_session_probe" in permissions.get_json()["data"]["menu_keys"]
    assert "mongodb_session_probe" not in permissions.get_json()["data"]["menu_keys"]
    assert permissions.get_json()["data"]["direct_menu_keys"] == []

    clusters = client.get("/api/v1/clusters?db_type=mysql&action=query", headers=headers)
    instances = client.get("/api/v1/instances?db_type=mysql&action=query", headers=headers)
    assert [item["id"] for item in clusters.get_json()["data"]] == [cluster_id]
    assert [item["id"] for item in instances.get_json()["data"]] == [instance_id]

    denied = client.post(
        "/api/v1/mysql/session-probes", json={"instance_id": denied_instance_id}, headers=headers
    )
    assert denied.status_code == 403

    monkeypatch.setattr(mysql_routes, "start_probe_session", lambda **_kwargs: _started_payload("mysql-token"))
    monkeypatch.setattr(mysql_routes, "get_probe_instance_id", lambda **_kwargs: instance_id)
    monkeypatch.setattr(mysql_routes, "fetch_processlist", lambda **_kwargs: {"sessions": []})
    monkeypatch.setattr(mysql_routes, "kill_process", lambda **_kwargs: {"killed": True})

    started = client.post("/api/v1/mysql/session-probes", json={"instance_id": instance_id}, headers=headers)
    assert started.status_code == 201
    assert started.get_json()["data"]["can_kill"] is False
    assert client.get("/api/v1/mysql/session-probes/mysql-token/processlist", headers=headers).status_code == 200
    assert client.post(
        "/api/v1/mysql/session-probes/mysql-token/kill", json={"process_id": 12}, headers=headers
    ).status_code == 403

    with app.app_context():
        permission = db.session.get(UserClusterPermission, permission_id)
        permission.can_query = False
        permission.can_change = True
        db.session.commit()

    assert client.get("/api/v1/mysql/session-probes/mysql-token/processlist", headers=headers).status_code == 403
    assert client.post(
        "/api/v1/mysql/session-probes/mysql-token/kill", json={"process_id": 12}, headers=headers
    ).status_code == 200


def test_mongodb_session_probe_requires_query_and_change_permissions(app, client, monkeypatch):
    from app.api.routes import mongodb as mongodb_routes

    with app.app_context():
        _user_id, _cluster_id, instance_id, denied_instance_id, permission_id = _seed_probe_user(
            "mongodb", "mongodb-probe-user"
        )
    headers = _login(client, "mongodb-probe-user")

    permissions = client.get("/api/v1/users/permissions/me", headers=headers)
    assert "mongodb_session_probe" in permissions.get_json()["data"]["menu_keys"]
    assert "mysql_session_probe" not in permissions.get_json()["data"]["menu_keys"]
    assert permissions.get_json()["data"]["direct_menu_keys"] == []

    denied = client.post(
        "/api/v1/mongodb/session-probes", json={"instance_id": denied_instance_id}, headers=headers
    )
    assert denied.status_code == 403

    monkeypatch.setattr(mongodb_routes, "start_probe_session", lambda **_kwargs: _started_payload("mongo-token"))
    monkeypatch.setattr(mongodb_routes, "get_probe_instance_id", lambda **_kwargs: instance_id)
    monkeypatch.setattr(mongodb_routes, "fetch_operations", lambda **_kwargs: {"sessions": []})
    monkeypatch.setattr(mongodb_routes, "kill_operation", lambda **_kwargs: {"killed": True})

    started = client.post("/api/v1/mongodb/session-probes", json={"instance_id": instance_id}, headers=headers)
    assert started.status_code == 201
    assert started.get_json()["data"]["can_kill"] is False
    assert client.get("/api/v1/mongodb/session-probes/mongo-token/operations", headers=headers).status_code == 200
    assert client.post(
        "/api/v1/mongodb/session-probes/mongo-token/kill", json={"operation_id": "op-1"}, headers=headers
    ).status_code == 403

    with app.app_context():
        permission = db.session.get(UserClusterPermission, permission_id)
        permission.can_change = True
        db.session.commit()

    assert client.post(
        "/api/v1/mongodb/session-probes/mongo-token/kill", json={"operation_id": "op-1"}, headers=headers
    ).status_code == 200


def test_postgresql_session_probe_requires_query_and_change_permissions(app, client, monkeypatch):
    from app.api.routes import postgresql as postgresql_routes

    with app.app_context():
        _user_id, _cluster_id, instance_id, denied_instance_id, permission_id = _seed_probe_user(
            "postgresql", "postgresql-probe-user"
        )
    headers = _login(client, "postgresql-probe-user")

    permissions = client.get("/api/v1/users/permissions/me", headers=headers)
    assert "postgresql_session_probe" in permissions.get_json()["data"]["menu_keys"]
    denied = client.post(
        "/api/v1/postgresql/session-probes", json={"instance_id": denied_instance_id}, headers=headers
    )
    assert denied.status_code == 403

    monkeypatch.setattr(postgresql_routes, "start_probe_session", lambda **_kwargs: _started_payload("postgresql-token"))
    monkeypatch.setattr(postgresql_routes, "get_probe_instance_id", lambda **_kwargs: instance_id)
    monkeypatch.setattr(postgresql_routes, "fetch_sessions", lambda **_kwargs: {"sessions": []})
    monkeypatch.setattr(postgresql_routes, "terminate_backend", lambda **_kwargs: {"terminated": True})

    started = client.post("/api/v1/postgresql/session-probes", json={"instance_id": instance_id}, headers=headers)
    assert started.status_code == 201
    assert started.get_json()["data"]["can_kill"] is False
    assert client.get("/api/v1/postgresql/session-probes/postgresql-token/sessions", headers=headers).status_code == 200
    assert client.post(
        "/api/v1/postgresql/session-probes/postgresql-token/kill", json={"process_id": 12}, headers=headers
    ).status_code == 403

    with app.app_context():
        permission = db.session.get(UserClusterPermission, permission_id)
        permission.can_change = True
        db.session.commit()

    assert client.post(
        "/api/v1/postgresql/session-probes/postgresql-token/kill", json={"process_id": 12}, headers=headers
    ).status_code == 200
