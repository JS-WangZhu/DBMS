from flask import g

from app.extensions import db
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.models.sql_release import SqlRelease
from app.models.user import User
from app.models.user_permission import UserClusterPermission, UserMenuPermission
from app.services.data_access import (
    validate_mongo_query,
    validate_mysql_query,
    validate_redis_query,
)


def _login(client, username, password):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['data']['access_token']}"}


def _release_assets(app):
    with app.app_context():
        user = User(username="release-skip-user", role="user", status="active", auth_source="local")
        user.set_password("password123")
        cluster = DatabaseCluster(name="release-skip", db_type="mysql", business_line="billing", environment="test")
        db.session.add_all([user, cluster])
        db.session.flush()
        instance = DatabaseInstance(
            name="release-skip-primary", db_type="mysql", host_input="127.0.0.1", port=3306,
            username="root", cluster_id=cluster.id,
        )
        db.session.add(instance)
        db.session.flush()
        db.session.add_all([
            UserMenuPermission(user_id=user.id, menu_key="sql_release_apply"),
            UserClusterPermission(user_id=user.id, cluster_id=cluster.id, can_change=True),
        ])
        db.session.commit()
        return user.id, cluster.id, instance.id


def test_query_blacklist_overrides_whitelist_and_ignores_string_literals(app, monkeypatch):
    import app.services.data_access as data_access

    monkeypatch.setattr(data_access, "_get_query_ops", lambda db_type: {"with"} if db_type == "mysql" else set())
    monkeypatch.setattr(data_access, "_get_query_blacklist", lambda db_type: {"update"} if db_type == "mysql" else set())
    ok, reason = validate_mysql_query("WITH rows AS (SELECT 1) UPDATE orders SET status='paid'")
    assert ok is False
    assert "WITH UPDATE" in reason

    monkeypatch.setattr(data_access, "_get_query_ops", lambda db_type: {"select"} if db_type == "mysql" else set())
    assert validate_mysql_query("SELECT 'update' AS operation_name") == (True, None)
    ok, reason = validate_mysql_query("SELECT * FROM orders FOR UPDATE")
    assert ok is False
    assert "UPDATE" in reason


def test_mongodb_and_redis_blacklists_override_query_allowlist(app, monkeypatch):
    import app.services.data_access as data_access

    monkeypatch.setattr(data_access, "_get_query_ops", lambda db_type: {
        "mongodb": {"run_command", "update"},
        "redis": {"get", "set"},
    }.get(db_type, set()))
    monkeypatch.setattr(data_access, "_get_query_blacklist", lambda db_type: {
        "mongodb": {"update"},
        "redis": {"set"},
    }.get(db_type, set()))

    ok, reason = validate_mongo_query({"op": "run_command", "command": {"update": "orders"}})
    assert ok is False
    assert "blacklisted" in reason
    ok, reason = validate_redis_query({"command": "SET"})
    assert ok is False
    assert "blacklisted" in reason


def test_global_ai_review_switch_skips_dispatch_for_new_release(app, client, monkeypatch):
    _, cluster_id, _ = _release_assets(app)
    admin_headers = _login(client, "admin", "admin123")
    config_response = client.put(
        "/api/v1/sql-release-config",
        headers=admin_headers,
        json={"ai_review_enabled": False},
    )
    assert config_response.status_code == 200
    assert config_response.get_json()["data"]["ai_review_enabled"] is False

    g.pop("current_user", None)
    import app.api.routes.sql_releases as routes
    dispatched = []
    monkeypatch.setattr(routes, "dispatch_sql_release_review", lambda *_args: dispatched.append(True))
    response = client.post(
        "/api/v1/sql-releases",
        headers=_login(client, "release-skip-user", "password123"),
        json={"cluster_id": cluster_id, "database": "billing", "sql": "UPDATE orders SET status='paid' WHERE id=1;"},
    )
    assert response.status_code == 201, response.get_json()
    payload = response.get_json()["data"]
    assert payload["status"] == "pending"
    assert payload["review_skipped"] is True
    assert payload["reviews"][0]["status"] == "skipped"
    assert dispatched == []


def test_failed_ai_review_can_be_skipped_by_applicant(app, client):
    user_id, cluster_id, instance_id = _release_assets(app)
    with app.app_context():
        release = SqlRelease(
            title="AI failed", applicant_id=user_id, cluster_id=cluster_id, instance_id=instance_id,
            db_type="mysql", database_name="billing", sql_text="UPDATE orders SET status='paid' WHERE id=1;",
            status="review_failed", ai_passed=False, force_submitted=False,
            ai_summary="AI 初审失败", review_json=[{
                "line": 1, "sql": "UPDATE orders SET status='paid' WHERE id=1", "passed": False,
                "status": "failed", "reason": "provider error", "suggestion": "",
            }],
        )
        db.session.add(release)
        db.session.commit()
        release_id = release.id

    response = client.post(
        f"/api/v1/sql-releases/{release_id}/skip-review",
        headers=_login(client, "release-skip-user", "password123"),
    )
    assert response.status_code == 200, response.get_json()
    payload = response.get_json()["data"]
    assert payload["status"] == "pending"
    assert payload["review_skipped"] is True
    assert payload["reviews"][0]["passed"] is None
    assert payload["can_skip_review"] is False
