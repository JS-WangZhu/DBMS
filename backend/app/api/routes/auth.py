from flask import Blueprint, request
from flask_jwt_extended import create_access_token

from app.api.routes.common import active_user_required, get_current_user
from app.extensions import db
from app.services.audit import log_audit
from app.services.auth import (
    authenticate_sso_code,
    authenticate_sso_token,
    authenticate_user,
    build_sso_authorize_url,
    get_sso_meta,
)
from app.utils.response import error_response, ok_response

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""

    if not username or not password:
        return error_response("username and password are required", code=400)

    user = authenticate_user(username=username, password=password)
    if not user:
        return error_response("invalid credentials", code=401)

    token = create_access_token(identity=str(user.id), additional_claims={"role": user.role})
    log_audit(user_id=user.id, action="auth.login", detail={"auth_source": user.auth_source})

    return ok_response(data={"access_token": token, "user": user.to_dict()})


@bp.get("/me")
@active_user_required
def me():
    user = get_current_user()
    return ok_response(data=user.to_dict())


@bp.get("/sso/meta")
def sso_meta():
    redirect_uri = (request.args.get("redirect_uri") or "").strip()
    return ok_response(data=get_sso_meta(redirect_uri=redirect_uri))


@bp.get("/sso/url")
def sso_url():
    redirect_uri = (request.args.get("redirect_uri") or "").strip()
    try:
        data = build_sso_authorize_url(redirect_uri=redirect_uri)
    except ValueError as exc:
        return error_response(str(exc), code=400)
    return ok_response(data=data)


@bp.get("/sso/callback")
def sso_callback():
    code = (request.args.get("code") or "").strip()
    state = (request.args.get("state") or "").strip()
    token_value = (request.args.get("token") or request.args.get("access_token") or "").strip()
    redirect_uri = (request.args.get("redirect_uri") or "").strip()
    try:
        if token_value:
            user = authenticate_sso_token(token=token_value, redirect_uri=redirect_uri)
        else:
            user = authenticate_sso_code(code=code, state=state, redirect_uri=redirect_uri)
    except ValueError as exc:
        return error_response(str(exc), code=401)
    token = create_access_token(identity=str(user.id), additional_claims={"role": user.role})
    log_audit(user_id=user.id, action="auth.login.sso", detail={"auth_source": user.auth_source})
    return ok_response(data={"access_token": token, "user": user.to_dict()})


@bp.patch("/password")
@active_user_required
def change_password():
    payload = request.get_json(silent=True) or {}
    old_password = payload.get("old_password") or ""
    new_password = payload.get("new_password") or ""

    if not old_password or not new_password:
        return error_response("old_password and new_password are required", code=400)
    if len(new_password) < 8:
        return error_response("new_password must be at least 8 chars", code=400)

    user = get_current_user()
    if not user.check_password(old_password):
        return error_response("old password is incorrect", code=400)

    user.set_password(new_password)
    db.session.commit()
    log_audit(user_id=user.id, action="auth.password.change", target_type="user", target_id=str(user.id))
    return ok_response(message="password updated")
