from datetime import datetime, timedelta, timezone

from flask_jwt_extended import create_access_token
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import mysql

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.auth_session import AuthSession


def _login(client):
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200
    data = response.get_json()["data"]
    return data, {"Authorization": f"Bearer {data['access_token']}"}


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def test_login_creates_server_session_and_regular_requests_do_not_extend_it(app, client):
    data, headers = _login(client)

    assert data["session"]["idle_timeout_seconds"] == 8 * 60 * 60
    session_id = data["session"]["session_id"]
    with app.app_context():
        original_activity = db.session.get(AuthSession, session_id).last_activity_at

    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 200

    with app.app_context():
        assert db.session.get(AuthSession, session_id).last_activity_at == original_activity


def test_activity_endpoint_extends_session(app, client):
    data, headers = _login(client)
    session_id = data["session"]["session_id"]
    old_activity = _utcnow() - timedelta(hours=7)
    with app.app_context():
        session = db.session.get(AuthSession, session_id)
        session.last_activity_at = old_activity
        db.session.commit()

    response = client.post("/api/v1/auth/activity", headers=headers)

    assert response.status_code == 200
    assert response.get_json()["data"]["idle_remaining_seconds"] > 28790
    with app.app_context():
        assert db.session.get(AuthSession, session_id).last_activity_at > old_activity


def test_idle_session_is_rejected_and_audited(app, client):
    data, headers = _login(client)
    session_id = data["session"]["session_id"]
    with app.app_context():
        session = db.session.get(AuthSession, session_id)
        session.last_activity_at = _utcnow() - timedelta(hours=8, seconds=1)
        db.session.commit()

    response = client.get("/api/v1/auth/me", headers=headers)

    assert response.status_code == 401
    assert response.get_json()["data"]["reason"] == "SESSION_IDLE_TIMEOUT"
    with app.app_context():
        session = db.session.get(AuthSession, session_id)
        assert session.revoke_reason == "idle_timeout"
        assert AuditLog.query.filter_by(
            action="auth.logout.idle_timeout",
            target_type="auth_session",
            target_id=session_id,
        ).count() == 1


def test_logout_revokes_session(app, client):
    data, headers = _login(client)
    session_id = data["session"]["session_id"]

    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
    response = client.get("/api/v1/auth/me", headers=headers)

    assert response.status_code == 401
    assert response.get_json()["data"]["reason"] == "SESSION_REVOKED"
    with app.app_context():
        assert db.session.get(AuthSession, session_id).revoke_reason == "logout"


def test_tokens_without_server_session_are_rejected(app, client):
    with app.app_context():
        old_token = create_access_token(identity="1", additional_claims={"role": "admin"})

    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_token}"})

    assert response.status_code == 401
    assert response.get_json()["data"]["reason"] == "SESSION_INVALID"


def test_mysql_auth_session_user_id_matches_production_users_bigint():
    ddl = str(CreateTable(AuthSession.__table__).compile(dialect=mysql.dialect()))

    assert "user_id BIGINT NOT NULL" in ddl
    assert "FOREIGN KEY(user_id) REFERENCES users (id)" in ddl
