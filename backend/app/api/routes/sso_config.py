from flask import Blueprint, request

from app.api.routes.common import require_menu_permission
from app.extensions import db
from app.models.sso_config import SsoConfig
from app.utils.response import ok_response


bp = Blueprint("sso_config", __name__, url_prefix="/sso-config")


EDITABLE_FIELDS = [
    "enabled",
    "provider_name",
    "client_id",
    "authorize_url",
    "token_url",
    "userinfo_url",
    "scope",
    "redirect_uri",
    "username_field",
    "email_field",
]


def _ensure_table_and_get():
    try:
        return SsoConfig.get_current()
    except Exception as exc:
        if "no such table" in str(exc).lower() or "doesn't exist" in str(exc).lower():
            db.create_all()
            return SsoConfig.get_current()
        raise


@bp.get("")
@require_menu_permission("sso_config")
def get_sso_config():
    row = _ensure_table_and_get()
    return ok_response(data=row.to_dict())


@bp.put("")
@require_menu_permission("sso_config")
def update_sso_config():
    row = _ensure_table_and_get()
    payload = request.get_json(silent=True) or {}

    for field in EDITABLE_FIELDS:
        if field in payload:
            value = payload.get(field)
            if field == "enabled":
                setattr(row, field, bool(value))
            else:
                setattr(row, field, (value or "").strip() if isinstance(value, str) else (value or ""))

    # client_secret: only update when provided and not the masked placeholder
    if "client_secret" in payload:
        secret = payload.get("client_secret")
        if secret and "******" not in str(secret):
            row.client_secret = str(secret)

    db.session.commit()
    return ok_response(data=row.to_dict())
