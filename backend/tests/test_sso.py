from urllib.parse import parse_qs, urlparse

from app.extensions import db
from app.models.sso_config import SsoConfig
from app.models.user import User
from app.models.user_permission import UserRoleGroup


def test_sso_meta_enabled_without_client_credentials(app):
    with app.app_context():
        row = SsoConfig.get_current()
        row.enabled = True
        row.provider_name = "Acme SSO"
        row.authorize_url = "https://sso.example.com/login"
        row.token_url = "https://sso.example.com/token/verify"
        db.session.commit()

    client = app.test_client()
    resp = client.get("/api/v1/auth/sso/meta?redirect_uri=http://localhost/sso/callback")

    assert resp.status_code == 200
    assert resp.get_json()["data"] == {"enabled": True, "provider_name": "Acme SSO"}


def test_sso_authorize_url_uses_only_callback_for_enterprise_sso(app):
    with app.app_context():
        row = SsoConfig.get_current()
        row.enabled = True
        row.authorize_url = "https://sso.example.com/login"
        row.token_url = "https://sso.example.com/token/verify"
        db.session.commit()

    client = app.test_client()
    resp = client.get("/api/v1/auth/sso/url?redirect_uri=http://localhost/sso/callback")

    assert resp.status_code == 200
    authorize_url = resp.get_json()["data"]["authorize_url"]
    parsed = urlparse(authorize_url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "sso.example.com"
    assert query["redirect_uri"] == ["http://localhost/sso/callback"]
    assert "client_id" not in query
    assert "client_secret" not in query


def test_sso_authorize_url_replaces_redirect_placeholder(app):
    with app.app_context():
        row = SsoConfig.get_current()
        row.enabled = True
        row.authorize_url = "https://sso.example.com/login?callback={redirect_uri}"
        row.token_url = "https://sso.example.com/token/verify"
        db.session.commit()

    client = app.test_client()
    resp = client.get("/api/v1/auth/sso/url?redirect_uri=http://localhost/sso/callback")

    assert resp.status_code == 200
    authorize_url = resp.get_json()["data"]["authorize_url"]
    query = parse_qs(urlparse(authorize_url).query)
    assert query["callback"] == ["http://localhost/sso/callback"]
    assert "redirect_uri" not in query


def test_sso_token_callback_creates_plain_user_without_role_groups(app, monkeypatch):
    with app.app_context():
        row = SsoConfig.get_current()
        row.enabled = True
        row.provider_name = "Acme SSO"
        row.authorize_url = "https://sso.example.com/login"
        row.token_url = "https://sso.example.com/token/verify"
        row.redirect_uri = "http://localhost/sso/callback"
        db.session.commit()

    class Response:
        status_code = 200
        content = b"{}"

        def json(self):
            return {
                "sub": "u-1001",
                "preferred_username": "sso.user",
                "email": "sso.user@example.com",
            }

    captured = {}

    def fake_post(url, data, timeout):
        captured.update({"url": url, "data": data, "timeout": timeout})
        return Response()

    monkeypatch.setattr("app.services.auth.requests.post", fake_post)

    client = app.test_client()
    resp = client.get(
        "/api/v1/auth/sso/callback?token=enterprise-token&redirect_uri=http://localhost/sso/callback"
    )

    assert resp.status_code == 200
    payload = resp.get_json()["data"]
    assert payload["access_token"]
    assert payload["user"]["username"] == "sso.user"
    assert payload["user"]["role"] == "user"
    assert captured["url"] == "https://sso.example.com/token/verify"
    assert captured["data"] == {
        "token": "enterprise-token",
        "redirect_uri": "http://localhost/sso/callback",
    }

    with app.app_context():
        user = User.query.filter_by(username="sso.user").one()
        assert user.auth_source == "sso"
        assert user.sso_provider == "Acme SSO"
        assert UserRoleGroup.query.filter_by(user_id=user.id).count() == 0


def test_sso_token_callback_uses_configured_token_placeholders(app, monkeypatch):
    with app.app_context():
        row = SsoConfig.get_current()
        row.enabled = True
        row.provider_name = "Acme SSO"
        row.authorize_url = "https://sso.example.com/login?callback={redirect_uri}"
        row.token_url = "https://sso.example.com/token/verify?ticket={token}&return_to={redirect_uri}"
        row.redirect_uri = "http://localhost/sso/callback?sso_ticket={token}"
        db.session.commit()

    class Response:
        status_code = 200
        content = b"{}"

        def json(self):
            return {
                "sub": "u-1002",
                "preferred_username": "placeholder.user",
                "email": "placeholder.user@example.com",
            }

    captured = {}

    def fake_post(url, data, timeout):
        captured.update({"url": url, "data": data, "timeout": timeout})
        return Response()

    monkeypatch.setattr("app.services.auth.requests.post", fake_post)

    client = app.test_client()
    resp = client.get("/api/v1/auth/sso/callback?sso_ticket=custom-token")

    assert resp.status_code == 200
    assert resp.get_json()["data"]["user"]["username"] == "placeholder.user"
    parsed = urlparse(captured["url"])
    query = parse_qs(parsed.query)
    assert captured["data"] == {}
    assert query["ticket"] == ["custom-token"]
    assert query["return_to"] == ["http://localhost/sso/callback?sso_ticket={token}"]
