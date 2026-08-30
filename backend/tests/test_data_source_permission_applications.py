from datetime import datetime, timedelta

from flask import g
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from app.extensions import db
from app.models.db_asset import DatabaseCluster
from app.models.user import User
from app.models.user_permission import (
    DataSourcePermissionApplication,
    DataSourcePermissionApplicationItem,
    UserClusterPermission,
    UserMenuPermission,
)
from app.api.routes.common import get_effective_cluster_permissions
from app.api.routes.data_source_permission_applications import _parse_requested_expires_at
from app.services.permission_expiry import revoke_expired_data_source_permissions


def _login(client, username, password):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": "Bearer " + response.get_json()["data"]["access_token"]}


def test_requested_expiry_interprets_wall_clock_time_as_beijing_time():
    assert _parse_requested_expires_at("2030-06-01 18:30:00") == datetime(2030, 6, 1, 10, 30)


def test_permission_application_only_exposes_production_and_grants_query_change(app, client):
    with app.app_context():
        user = User(username="permission-applicant", role="user", status="active", auth_source="local")
        user.set_password("password123")
        prod = DatabaseCluster(name="orders-prod", db_type="mysql", business_line="orders", environment="prod")
        test = DatabaseCluster(name="orders-test", db_type="mysql", business_line="orders", environment="test")
        db.session.add_all([user, prod, test])
        db.session.flush()
        db.session.add(UserMenuPermission(user_id=user.id, menu_key="data_permission_apply"))
        db.session.commit()
        user_id, prod_id, test_id = user.id, prod.id, test.id

    user_headers = _login(client, "permission-applicant", "password123")
    sources = client.get("/api/v1/data-source-permission-applications/sources", headers=user_headers)
    assert sources.status_code == 200
    assert [item["id"] for item in sources.get_json()["data"]["clusters"]] == [prod_id]

    non_prod = client.post(
        "/api/v1/data-source-permission-applications",
        headers=user_headers,
        json={"reason": "业务排查", "items": [{"cluster_id": test_id, "can_query": True}]},
    )
    assert non_prod.status_code == 400

    created = client.post(
        "/api/v1/data-source-permission-applications",
        headers=user_headers,
        json={
            "reason": "生产订单排查与维护",
            "requested_expires_at": (datetime.utcnow() + timedelta(days=7)).date().isoformat(),
            "items": [{"cluster_id": prod_id, "can_query": True, "can_change": True, "can_execute": True}],
        },
    )
    assert created.status_code == 201
    application = created.get_json()["data"]
    assert application["status"] == "pending"
    assert application["requested_expires_at"]
    assert application["items"][0]["can_query"] is True
    assert application["items"][0]["can_change"] is True
    assert "can_execute" not in application["items"]

    mine = client.get("/api/v1/data-source-permission-applications", headers=user_headers)
    assert mine.status_code == 200
    assert mine.get_json()["data"]["total"] == 1

    g.pop("current_user", None)
    admin_headers = _login(client, "admin", "admin123")
    approved = client.patch(
        "/api/v1/data-source-permission-applications/" + str(application["id"]) + "/review",
        headers=admin_headers,
        json={"decision": "approved", "comment": "同意"},
    )
    assert approved.status_code == 200
    with app.app_context():
        permission = UserClusterPermission.query.filter_by(user_id=user_id, cluster_id=prod_id).one()
        assert permission.can_query is True
        assert permission.can_change is True
        assert permission.can_execute is False
        assert permission.expires_at == datetime.fromisoformat(application["requested_expires_at"]).replace(tzinfo=None)

    repeated = client.patch(
        "/api/v1/data-source-permission-applications/" + str(application["id"]) + "/review",
        headers=admin_headers,
        json={"decision": "approved"},
    )
    assert repeated.status_code == 409


def test_expired_direct_permission_is_not_effective_and_is_reclaimed(app):
    with app.app_context():
        user = User(username="expired-permission-user", role="user", status="active", auth_source="local")
        cluster = DatabaseCluster(name="expired-cluster", db_type="mysql")
        db.session.add_all([user, cluster])
        db.session.flush()
        db.session.add(UserClusterPermission(
            user_id=user.id, cluster_id=cluster.id, can_query=True,
            expires_at=datetime.utcnow() - timedelta(minutes=1),
        ))
        db.session.commit()
        assert get_effective_cluster_permissions(user.id) == {}
        assert revoke_expired_data_source_permissions() == 1
        assert UserClusterPermission.query.filter_by(user_id=user.id, cluster_id=cluster.id).first() is None


def test_permission_application_requires_menu(app, client):
    with app.app_context():
        user = User(username="no-application-menu", role="user", status="active", auth_source="local")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()

    headers = _login(client, "no-application-menu", "password123")
    assert client.get("/api/v1/data-source-permission-applications", headers=headers).status_code == 403

    g.pop("current_user", None)
    admin_headers = _login(client, "admin", "admin123")
    missing_comment = client.patch(
        "/api/v1/data-source-permission-applications/999/review",
        headers=admin_headers,
        json={"decision": "rejected"},
    )
    assert missing_comment.status_code == 404


def test_permission_application_mysql_foreign_keys_match_production_ids():
    application_ddl = str(CreateTable(DataSourcePermissionApplication.__table__).compile(dialect=mysql.dialect()))
    item_ddl = str(CreateTable(DataSourcePermissionApplicationItem.__table__).compile(dialect=mysql.dialect()))

    assert "applicant_id BIGINT NOT NULL" in application_ddl
    assert "reviewer_id BIGINT" in application_ddl
    assert "cluster_id BIGINT NOT NULL" in item_ddl
