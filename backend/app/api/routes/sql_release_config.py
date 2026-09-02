from flask import Blueprint, request

from app.api.routes.common import get_current_user, require_menu_permission
from app.extensions import db
from app.services.audit import log_audit
from app.services.sql_release_config import get_or_create_sql_release_config
from app.utils.response import error_response, ok_response


bp = Blueprint("sql_release_config", __name__, url_prefix="/sql-release-config")


@bp.get("")
@require_menu_permission("sql_release_config")
def get_config():
    return ok_response(data=get_or_create_sql_release_config().to_dict())


@bp.put("")
@require_menu_permission("sql_release_config")
def update_config():
    payload = request.get_json(silent=True) or {}
    config = get_or_create_sql_release_config()
    if "ai_review_enabled" in payload:
        if not isinstance(payload.get("ai_review_enabled"), bool):
            return error_response("ai_review_enabled must be boolean", code=400)
        config.ai_review_enabled = payload["ai_review_enabled"]
    db.session.commit()
    log_audit(
        user_id=get_current_user().id,
        action="sql_release.config.update",
        target_type="sql_release_config",
        target_id=str(config.id),
        detail={"ai_review_enabled": bool(config.ai_review_enabled)},
    )
    return ok_response(data=config.to_dict(), message="数据发布配置已更新")
