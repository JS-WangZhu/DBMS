import uuid
from datetime import datetime, timedelta, timezone

from flask import current_app, g, request

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.auth_session import AuthSession
from app.utils.response import error_response


SESSION_IDLE_TIMEOUT = "SESSION_IDLE_TIMEOUT"
SESSION_REVOKED = "SESSION_REVOKED"
SESSION_INVALID = "SESSION_INVALID"


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def idle_timeout_seconds() -> int:
    return max(int(current_app.config.get("AUTH_IDLE_TIMEOUT_SECONDS", 28800)), 60)


def _session_payload(session: AuthSession, now=None) -> dict:
    now = now or _utcnow()
    expires_at = session.last_activity_at + timedelta(seconds=idle_timeout_seconds())
    remaining = max(0, int((expires_at - now).total_seconds()))
    return {
        "session_id": session.id,
        "last_activity_at": session.last_activity_at.isoformat(),
        "idle_expires_at": expires_at.isoformat(),
        "idle_remaining_seconds": remaining,
        "idle_timeout_seconds": idle_timeout_seconds(),
    }


def create_auth_session(user_id: int) -> AuthSession:
    forwarded_for = (request.headers.get("X-Forwarded-For") or "").split(",", 1)[0].strip()
    session = AuthSession(
        id=str(uuid.uuid4()),
        user_id=user_id,
        last_activity_at=_utcnow(),
        ip_address=(forwarded_for or request.remote_addr or "")[:64] or None,
        user_agent=(request.user_agent.string or "")[:255] or None,
    )
    db.session.add(session)
    db.session.commit()
    return session


def touch_auth_session(session: AuthSession) -> dict:
    now = _utcnow()
    session.last_activity_at = now
    db.session.commit()
    return _session_payload(session, now=now)


def revoke_auth_session(session: AuthSession, reason: str, commit=True) -> bool:
    if session.revoked_at:
        return False
    session.revoked_at = _utcnow()
    session.revoke_reason = reason
    if commit:
        db.session.commit()
    return True


def revoke_user_sessions(user_id: int, reason: str, commit=True) -> int:
    now = _utcnow()
    count = AuthSession.query.filter_by(user_id=user_id, revoked_at=None).update(
        {"revoked_at": now, "revoke_reason": reason},
        synchronize_session=False,
    )
    if commit:
        db.session.commit()
    return count


def current_auth_session() -> AuthSession | None:
    return getattr(g, "auth_session", None)


def configure_jwt_session_callbacks(jwt):
    @jwt.token_in_blocklist_loader
    def session_is_revoked(_jwt_header, jwt_payload):
        sid = str(jwt_payload.get("sid") or "").strip()
        if not sid:
            g.auth_session_failure = SESSION_INVALID
            return True

        session = db.session.get(AuthSession, sid)
        if not session:
            g.auth_session_failure = SESSION_INVALID
            return True
        if session.revoked_at:
            g.auth_session_failure = SESSION_REVOKED
            g.auth_session_revoke_reason = session.revoke_reason
            return True

        now = _utcnow()
        if now - session.last_activity_at >= timedelta(seconds=idle_timeout_seconds()):
            session.revoked_at = now
            session.revoke_reason = "idle_timeout"
            db.session.add(
                AuditLog(
                    user_id=session.user_id,
                    action="auth.logout.idle_timeout",
                    target_type="auth_session",
                    target_id=session.id,
                    detail_json={"idle_timeout_seconds": idle_timeout_seconds()},
                )
            )
            db.session.commit()
            g.auth_session_failure = SESSION_IDLE_TIMEOUT
            return True

        g.auth_session = session
        return False

    @jwt.revoked_token_loader
    def revoked_token_response(_jwt_header, _jwt_payload):
        reason = getattr(g, "auth_session_failure", SESSION_REVOKED)
        messages = {
            SESSION_IDLE_TIMEOUT: "登录会话已超过8小时未操作，请重新登录",
            SESSION_INVALID: "登录会话无效，请重新登录",
            SESSION_REVOKED: "登录会话已失效，请重新登录",
        }
        return error_response(messages.get(reason, messages[SESSION_REVOKED]), code=401, data={"reason": reason})

    @jwt.expired_token_loader
    def expired_token_response(_jwt_header, _jwt_payload):
        return error_response("登录凭证已过期，请重新登录", code=401, data={"reason": "TOKEN_EXPIRED"})
