from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from datetime import datetime

import requests
from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.extensions import db
from app.models.user import User


_SSO_DB_FIELDS = (
    "enabled",
    "provider_name",
    "client_id",
    "client_secret",
    "authorize_url",
    "token_url",
    "userinfo_url",
    "scope",
    "redirect_uri",
    "username_field",
    "email_field",
)


def _load_sso_db_config():
    """Load SSO config from the database (single-row table).

    Returns a dict with only fields that have a non-empty override value.
    Safely returns {} if the table doesn't exist yet.
    """
    try:
        from app.models.sso_config import SsoConfig

        row = SsoConfig.query.order_by(SsoConfig.id.asc()).first()
        if row is None:
            return {}
        data = {}
        for field in _SSO_DB_FIELDS:
            value = getattr(row, field, None)
            if field == "enabled":
                data[field] = bool(value)
            elif value is not None and str(value).strip() != "":
                data[field] = value
        return data
    except Exception:
        return {}


def _sso_cfg(key: str, default=None):
    """Get a single SSO config value with DB precedence, then env via app config.

    key is the short name (e.g. 'client_id'); env is SSO_{KEY_UPPER}.
    """
    db_cfg = _load_sso_db_config()
    env_key = f"SSO_{key.upper()}"
    env_value = current_app.config.get(env_key)
    if key == "enabled":
        if "enabled" in db_cfg:
            return bool(db_cfg["enabled"])
        return bool(env_value) if env_value is not None else bool(default)
    if key in db_cfg and db_cfg[key] not in (None, ""):
        return db_cfg[key]
    if env_value not in (None, ""):
        return env_value
    return default


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
    return bool(_sso_cfg("enabled", False))


def _sso_required_fields_ready():
    return all(
        [
            _sso_cfg("authorize_url"),
            _sso_cfg("token_url"),
        ]
    )


def _sso_oauth_fields_ready():
    return bool(_sso_cfg("client_id") and _sso_cfg("client_secret"))


def _sso_state_serializer():
    secret = current_app.config.get("SECRET_KEY") or current_app.config.get("JWT_SECRET_KEY") or "dev-secret"
    return URLSafeTimedSerializer(secret_key=secret, salt="dbms-sso-state")


def _resolve_redirect_uri(redirect_uri: str = ""):
    configured = str(_sso_cfg("redirect_uri", "") or "").strip()
    if configured and "{token}" in configured:
        return configured
    value = (redirect_uri or "").strip() or configured
    return value


def _render_sso_template(template: str, values: dict):
    rendered = str(template or "")
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", quote(str(value or ""), safe=""))
    return rendered


def extract_sso_callback_token(args):
    token = (args.get("token") or args.get("access_token") or "").strip()
    if token:
        return token

    configured_redirect_uri = str(_sso_cfg("redirect_uri", "") or "").strip()
    if not configured_redirect_uri:
        return ""
    for key, value in parse_qsl(urlsplit(configured_redirect_uri).query, keep_blank_values=True):
        if "{token}" in value or "{access_token}" in value:
            return (args.get(key) or "").strip()
    return ""


def get_sso_meta(redirect_uri: str = ""):
    enabled = _is_sso_enabled() and _sso_required_fields_ready() and bool(_resolve_redirect_uri(redirect_uri))
    return {
        "enabled": enabled,
        "provider_name": _sso_cfg("provider_name", "SSO") or "SSO",
    }


def build_sso_authorize_url(redirect_uri: str = ""):
    if not _is_sso_enabled():
        raise ValueError("sso is disabled")
    if not _sso_required_fields_ready():
        raise ValueError("sso config is incomplete")
    final_redirect_uri = _resolve_redirect_uri(redirect_uri)
    if not final_redirect_uri:
        raise ValueError("redirect_uri is required")
    params = {}
    state = ""
    if _sso_oauth_fields_ready():
        state = _sso_state_serializer().dumps({"redirect_uri": final_redirect_uri})
        params.update(
            {
                "client_id": _sso_cfg("client_id"),
                "response_type": "code",
                "scope": _sso_cfg("scope", "openid profile email") or "openid profile email",
                "state": state,
            }
        )
    authorize_base = str(_sso_cfg("authorize_url") or "")
    if "{redirect_uri}" in authorize_base:
        authorize_base = _render_sso_template(authorize_base, {"redirect_uri": final_redirect_uri})
    else:
        params["redirect_uri"] = final_redirect_uri
    parts = urlsplit(authorize_base)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(params)
    authorize_url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
    return {"authorize_url": authorize_url, "state": state, "redirect_uri": final_redirect_uri}


def _extract_sso_identity(userinfo: dict):
    """从 userinfo 中提取 SSO 身份关键信息。

    返回 dict: {subject, username, email, display_name}
    其中 subject 作为导向 SSO Provider 的唯一绑定 ID，优先 sub。
    """
    info = userinfo if isinstance(userinfo, dict) else {}
    username_field = str(_sso_cfg("username_field", "preferred_username") or "preferred_username").strip()
    email_field = str(_sso_cfg("email_field", "email") or "email").strip()

    def _pick(keys):
        for k in keys:
            if not k:
                continue
            v = info.get(k)
            if v is None:
                continue
            text = str(v).strip()
            if text:
                return text
        return None

    subject = _pick(["sub", "id", "user_id", "uid", username_field])
    username = _pick([username_field, "preferred_username", "username", "name", email_field, "email", "sub"])
    email = _pick([email_field, "email"])
    display_name = _pick(["name", "display_name", "nickname", username_field])

    return {
        "subject": subject,
        "username": username,
        "email": email,
        "display_name": display_name,
    }


def _extract_username_from_userinfo(userinfo: dict):
    return _extract_sso_identity(userinfo).get("username")


def _normalize_sso_userinfo(payload: dict):
    info = payload if isinstance(payload, dict) else {}
    for key in ("data", "user", "userinfo", "user_info"):
        nested = info.get(key)
        if isinstance(nested, dict):
            return nested
    return info


def _upsert_sso_user(identity: dict):
    """根据 SSO 身份创建或绑定系统用户。

    匹配顺序：
      1. sso_subject 精确命中 (已绑定) -> 返回该用户，并刷新最新 profile
      2. 用户名命中且未绑定 (local/ldap 旧账号) -> 将 sso_subject 写入，完成绑定
      3. 新建用户，auth_source='sso'
    """
    subject = (identity or {}).get("subject")
    username = (identity or {}).get("username")
    email = (identity or {}).get("email")
    display_name = (identity or {}).get("display_name")
    provider_name = str(_sso_cfg("provider_name", "SSO") or "SSO")

    if not username:
        return None

    user = None
    if subject:
        user = User.query.filter_by(sso_subject=str(subject)).first()

    if user is None:
        user = User.query.filter_by(username=username).first()
        if user is not None and user.sso_subject and subject and user.sso_subject != str(subject):
            # 用户名冲突：已绑定其他 subject，不允许改绑
            return None

    if user is None:
        user = User(
            username=username,
            role="user",
            status="active",
            auth_source="sso",
        )
        if subject:
            user.sso_subject = str(subject)
        user.sso_provider = provider_name
        if email:
            user.email = email
        if display_name:
            user.display_name = display_name
        user.last_login_at = datetime.utcnow()
        db.session.add(user)
        db.session.commit()
        return user

    if user.status != "active":
        return None

    # 存在旧账号，完成绑定 / 刷新 profile
    if subject and not user.sso_subject:
        user.sso_subject = str(subject)
    if not user.sso_provider:
        user.sso_provider = provider_name
    # auth_source 仅在原为 local 且无密码或原为 sso 时标记为 sso；保留 ldap 等其他来源
    if user.auth_source in ("local", "sso") or user.auth_source is None:
        user.auth_source = "sso"
    if email:
        user.email = email
    if display_name:
        user.display_name = display_name
    user.last_login_at = datetime.utcnow()
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
    if not _sso_oauth_fields_ready():
        raise ValueError("sso oauth config is incomplete")

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
        _sso_cfg("token_url"),
        data={
            "grant_type": "authorization_code",
            "client_id": _sso_cfg("client_id"),
            "client_secret": _sso_cfg("client_secret"),
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
    userinfo_url = str(_sso_cfg("userinfo_url", "") or "").strip()
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

    userinfo = _normalize_sso_userinfo(userinfo)
    username = _extract_username_from_userinfo(userinfo)
    if not username:
        raise ValueError("sso userinfo missing username")

    identity = _extract_sso_identity(userinfo)
    user = _upsert_sso_user(identity)
    if not user:
        raise ValueError("sso user is disabled or username conflict")
    return user


def authenticate_sso_token(token: str, redirect_uri: str = ""):
    if not token:
        raise ValueError("token is required")
    if not _is_sso_enabled():
        raise ValueError("sso is disabled")
    if not _sso_required_fields_ready():
        raise ValueError("sso config is incomplete")

    final_redirect_uri = _resolve_redirect_uri(redirect_uri)
    if not final_redirect_uri:
        raise ValueError("redirect_uri is required")

    token_url = str(_sso_cfg("token_url") or "")
    if "{token}" in token_url or "{redirect_uri}" in token_url:
        token_url = _render_sso_template(token_url, {"token": token, "redirect_uri": final_redirect_uri})
        token_payload = {}
    else:
        token_payload = {"token": token, "redirect_uri": final_redirect_uri}

    token_resp = requests.post(token_url, data=token_payload, timeout=10)
    if token_resp.status_code >= 400:
        raise ValueError(f"sso token verify failed: HTTP {token_resp.status_code}")
    token_data = token_resp.json() if token_resp.content else {}

    userinfo_url = str(_sso_cfg("userinfo_url", "") or "").strip()
    if userinfo_url:
        access_token = token_data.get("access_token") or token
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

    userinfo = _normalize_sso_userinfo(userinfo)
    username = _extract_username_from_userinfo(userinfo)
    if not username:
        raise ValueError("sso userinfo missing username")

    identity = _extract_sso_identity(userinfo)
    user = _upsert_sso_user(identity)
    if not user:
        raise ValueError("sso user is disabled or username conflict")
    return user


def authenticate_user(username: str, password: str):
    auth_mode = current_app.config.get("AUTH_MODE", "local")

    if auth_mode == "ldap":
        user = _ldap_auth(username, password)
        if user:
            return user

    return _local_auth(username, password)
