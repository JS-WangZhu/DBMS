from urllib.parse import urlencode

import requests
from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.extensions import db
from app.models.user import User


def _local_auth(username: str, password: str):
    user = User.query.filter_by(username=username).first()
    if not user or user.status != "active":
        return None
    if user.auth_source != "local":
        return None
    return user if user.check_password(password) else None


def _ldap_auth(username: str, password: str):
    server_uri = current_app.config.get("LDAP_SERVER_URI")
    base_dn = current_app.config.get("LDAP_BASE_DN")
    user_dn_tpl = current_app.config.get("LDAP_USER_DN_TEMPLATE")

    if not server_uri or not base_dn or not user_dn_tpl:
        return None

    try:
        from ldap3 import ALL, Connection, Server
    except Exception:
        return None

    user_dn = user_dn_tpl.format(username=username)

    try:
        conn = Connection(Server(server_uri, get_info=ALL), user=user_dn, password=password, auto_bind=True)
        conn.unbind()
    except Exception:
        return None

    user = User.query.filter_by(username=username).first()
    if not user:
        user = User(username=username, role="user", status="active", auth_source="ldap", ldap_dn=user_dn)
        db.session.add(user)
        db.session.commit()
    else:
        user.auth_source = "ldap"
        user.ldap_dn = user_dn
        db.session.commit()

    return user


def _is_sso_enabled():
    return bool(current_app.config.get("SSO_ENABLED"))


def _sso_required_fields_ready():
    return all(
        [
            current_app.config.get("SSO_CLIENT_ID"),
            current_app.config.get("SSO_CLIENT_SECRET"),
            current_app.config.get("SSO_AUTHORIZE_URL"),
            current_app.config.get("SSO_TOKEN_URL"),
        ]
    )


def _sso_state_serializer():
    secret = current_app.config.get("SECRET_KEY") or current_app.config.get("JWT_SECRET_KEY") or "dev-secret"
    return URLSafeTimedSerializer(secret_key=secret, salt="dbms-sso-state")


def _resolve_redirect_uri(redirect_uri: str = ""):
    value = (redirect_uri or "").strip() or (current_app.config.get("SSO_REDIRECT_URI") or "").strip()
    return value


def get_sso_meta(redirect_uri: str = ""):
    enabled = _is_sso_enabled() and _sso_required_fields_ready() and bool(_resolve_redirect_uri(redirect_uri))
    return {
        "enabled": enabled,
        "provider_name": current_app.config.get("SSO_PROVIDER_NAME") or "SSO",
    }


def build_sso_authorize_url(redirect_uri: str = ""):
    if not _is_sso_enabled():
        raise ValueError("sso is disabled")
    if not _sso_required_fields_ready():
        raise ValueError("sso config is incomplete")
    final_redirect_uri = _resolve_redirect_uri(redirect_uri)
    if not final_redirect_uri:
        raise ValueError("redirect_uri is required")
    state = _sso_state_serializer().dumps({"redirect_uri": final_redirect_uri})
    query = urlencode(
        {
            "client_id": current_app.config.get("SSO_CLIENT_ID"),
            "redirect_uri": final_redirect_uri,
            "response_type": "code",
            "scope": current_app.config.get("SSO_SCOPE") or "openid profile email",
            "state": state,
        }
    )
    authorize_url = f"{current_app.config.get('SSO_AUTHORIZE_URL')}?{query}"
    return {"authorize_url": authorize_url, "state": state, "redirect_uri": final_redirect_uri}


def _extract_username_from_userinfo(userinfo: dict):
    if not isinstance(userinfo, dict):
        return None
    username_field = (current_app.config.get("SSO_USERNAME_FIELD") or "preferred_username").strip()
    email_field = (current_app.config.get("SSO_EMAIL_FIELD") or "email").strip()
    candidates = [username_field, "preferred_username", "username", "name", email_field, "email", "sub"]
    for key in candidates:
        value = userinfo.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _upsert_sso_user(username: str, userinfo: dict):
    user = User.query.filter_by(username=username).first()
    if not user:
        user = User(username=username, role="user", status="active", auth_source="sso")
        db.session.add(user)
        db.session.commit()
        return user
    if user.status != "active":
        return None
    user.auth_source = "sso"
    if not user.password_hash:
        user.password_hash = None
    db.session.commit()
    return user


def authenticate_sso_code(code: str, state: str, redirect_uri: str = ""):
    if not code:
        raise ValueError("code is required")
    if not state:
        raise ValueError("state is required")
    if not _is_sso_enabled():
        raise ValueError("sso is disabled")
    if not _sso_required_fields_ready():
        raise ValueError("sso config is incomplete")

    try:
        state_data = _sso_state_serializer().loads(state, max_age=600)
    except SignatureExpired:
        raise ValueError("sso state expired")
    except BadSignature:
        raise ValueError("invalid sso state")

    final_redirect_uri = _resolve_redirect_uri(redirect_uri)
    state_redirect_uri = (state_data or {}).get("redirect_uri")
    if not final_redirect_uri:
        final_redirect_uri = state_redirect_uri
    if not final_redirect_uri or state_redirect_uri != final_redirect_uri:
        raise ValueError("redirect_uri mismatch")

    token_resp = requests.post(
        current_app.config.get("SSO_TOKEN_URL"),
        data={
            "grant_type": "authorization_code",
            "client_id": current_app.config.get("SSO_CLIENT_ID"),
            "client_secret": current_app.config.get("SSO_CLIENT_SECRET"),
            "code": code,
            "redirect_uri": final_redirect_uri,
        },
        timeout=10,
    )
    if token_resp.status_code >= 400:
        raise ValueError(f"sso token exchange failed: HTTP {token_resp.status_code}")
    token_data = token_resp.json() if token_resp.content else {}
    access_token = token_data.get("access_token")
    if not access_token:
        raise ValueError("sso token response missing access_token")

    userinfo = {}
    userinfo_url = (current_app.config.get("SSO_USERINFO_URL") or "").strip()
    if userinfo_url:
        userinfo_resp = requests.get(
            userinfo_url,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if userinfo_resp.status_code >= 400:
            raise ValueError(f"sso userinfo fetch failed: HTTP {userinfo_resp.status_code}")
        userinfo = userinfo_resp.json() if userinfo_resp.content else {}
    else:
        userinfo = token_data

    username = _extract_username_from_userinfo(userinfo)
    if not username:
        raise ValueError("sso userinfo missing username")

    user = _upsert_sso_user(username=username, userinfo=userinfo)
    if not user:
        raise ValueError("sso user is disabled")
    return user


def authenticate_user(username: str, password: str):
    auth_mode = current_app.config.get("AUTH_MODE", "local")

    if auth_mode == "ldap":
        user = _ldap_auth(username, password)
        if user:
            return user

    return _local_auth(username, password)
