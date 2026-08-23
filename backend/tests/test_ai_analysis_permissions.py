from app.extensions import db
from app.models.ai_config import AIModelConfig
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.models.user import User
from app.models.user_permission import UserClusterPermission, UserMenuPermission


def _login(client, username, password):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['data']['access_token']}"}


def test_query_user_can_stream_ai_analysis_with_cluster_query_permission(app, client, monkeypatch):
    with app.app_context():
        user = User(username="ai-query-user", role="user", status="active", auth_source="local")
        user.set_password("password123")
        cluster = DatabaseCluster(
            name="ai-query-cluster", db_type="mysql", business_line="billing", environment="test"
        )
        db.session.add_all([user, cluster])
        db.session.flush()
        instance = DatabaseInstance(
            name="ai-query-primary", db_type="mysql", host_input="127.0.0.1", port=3306,
            username="root", cluster_id=cluster.id,
        )
        db.session.add_all([
            instance,
            AIModelConfig(
                name="ai-query-model", api_url="https://ai.example/v1/chat/completions",
                api_key="test-key", model_name="test-model", is_default=True, enabled=True,
            ),
            UserMenuPermission(user_id=user.id, menu_key="data_query"),
            UserClusterPermission(user_id=user.id, cluster_id=cluster.id, can_query=True),
        ])
        db.session.commit()
        cluster_id, instance_id = cluster.id, instance.id

    import app.api.routes.ai_routes as routes

    monkeypatch.setattr(routes, "pick_instance", lambda *_args, **_kwargs: DatabaseInstance.query.get(instance_id))
    monkeypatch.setattr(routes, "get_mysql_metadata", lambda *_args: {"tables": []})
    monkeypatch.setattr(routes, "analyze_sql_with_ai_stream", lambda *_args: iter(["analysis ok"]))

    response = client.post(
        "/api/v1/ai/analyze/stream",
        headers=_login(client, "ai-query-user", "password123"),
        json={
            "db_type": "mysql", "business_line": "billing", "environment": "test",
            "cluster_id": cluster_id, "database": "billing", "statement": "SELECT 1",
        },
    )

    assert response.status_code == 200
    assert "analysis ok" in response.get_data(as_text=True)


def test_query_user_ai_analysis_still_requires_cluster_query_permission(app, client):
    with app.app_context():
        user = User(username="ai-no-cluster-user", role="user", status="active", auth_source="local")
        user.set_password("password123")
        cluster = DatabaseCluster(name="ai-denied-cluster", db_type="mysql")
        db.session.add_all([user, cluster])
        db.session.flush()
        db.session.add(UserMenuPermission(user_id=user.id, menu_key="data_query"))
        db.session.commit()
        cluster_id = cluster.id

    response = client.post(
        "/api/v1/ai/analyze/stream",
        headers=_login(client, "ai-no-cluster-user", "password123"),
        json={
            "db_type": "mysql", "cluster_id": cluster_id,
            "database": "billing", "statement": "SELECT 1",
        },
    )

    assert response.status_code == 403
    assert response.get_json()["message"] == "no permission for this cluster"


def test_model_config_test_endpoint_uses_saved_thinking_setting(app, client, monkeypatch):
    with app.app_context():
        config = AIModelConfig(
            name="thinking-model", api_url="https://ai.example/v1", api_key="test-key",
            model_name="reasoning-model", is_default=True, enabled=True, thinking_enabled=True,
        )
        db.session.add(config)
        db.session.commit()
        config_id = config.id

    import app.api.routes.ai_routes as routes
    captured = {}

    def fake_test(config):
        captured["thinking_enabled"] = config.thinking_enabled
        return {"model": config.model_name, "reply": "OK"}

    monkeypatch.setattr(routes, "test_ai_model_config", fake_test)
    response = client.post(
        f"/api/v1/ai/configs/{config_id}/test",
        headers=_login(client, "admin", "admin123"),
    )

    assert response.status_code == 200
    assert captured == {"thinking_enabled": True}
    assert response.get_json()["data"]["reply"] == "OK"
