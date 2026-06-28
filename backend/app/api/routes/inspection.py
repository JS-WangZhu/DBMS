from datetime import datetime, timedelta

from flask import Blueprint, current_app, request

from app.api.routes.common import get_current_user, list_allowed_cluster_ids, require_menu_permission
from app.extensions import db, scheduler
from app.models.db_asset import DatabaseCluster
from app.models.inspection import InspectionAlert
from app.models.notify_target import BackupNotifyTarget
from app.services.audit import log_audit
from app.services.redis_cache import get_json
from app.services.inspection_service import (
    get_or_create_inspection_config,
    inspection_overview,
    refresh_inspection_config_cache,
    run_inspection_cycle,
    update_inspection_config,
)
from app.tasks.scheduler import sync_inspection_job
from app.utils.response import error_response, ok_response

bp = Blueprint("inspection", __name__, url_prefix="/inspection")


def _safe_int(value):
    try:
        if value is None or value == "":
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


@bp.get("/overview")
@require_menu_permission("inspection_manage")
def get_overview():
    db_type = (request.args.get("db_type") or "").strip() or None
    status = (request.args.get("status") or "").strip() or None
    cluster_id = _safe_int(request.args.get("cluster_id"))
    page = _safe_int(request.args.get("page")) or 1
    page_size = _safe_int(request.args.get("page_size")) or 10
    user = get_current_user()
    allowed = None
    if user and user.role != "admin":
        allowed = list_allowed_cluster_ids("query") or []
    data = inspection_overview(
        db_type=db_type,
        cluster_id=cluster_id,
        status=status,
        page=page,
        page_size=page_size,
        allowed_cluster_ids=allowed,
    )
    return ok_response(data=data)


@bp.put("/alerts/<int:alert_id>/mute")
@require_menu_permission("inspection_manage")
def mute_alert(alert_id):
    payload = request.get_json(silent=True) or {}
    try:
        duration_minutes = int(payload.get("duration_minutes"))
    except (TypeError, ValueError):
        return error_response("duration_minutes must be an integer", code=400)
    if duration_minutes < 0:
        return error_response("duration_minutes must be >= 0", code=400)

    alert = InspectionAlert.query.get_or_404(alert_id)
    user = get_current_user()
    if user and user.role != "admin":
        allowed = set(list_allowed_cluster_ids("query") or [])
        if alert.cluster_id not in allowed:
            return error_response("no permission for this inspection alert", code=403)
    now = datetime.now()
    if duration_minutes == 0:
        alert.muted_at = None
        alert.muted_until = None
        action = "inspection.alert.unmute"
    else:
        alert.muted_at = now
        alert.muted_until = now + timedelta(minutes=min(duration_minutes, 525600))
        action = "inspection.alert.mute"
    db.session.commit()
    log_audit(
        user_id=None,
        action=action,
        target_type="inspection_alert",
        target_id=str(alert.id),
        detail={
            "duration_minutes": duration_minutes,
            "muted_until": alert.muted_until.isoformat() if alert.muted_until else None,
        },
    )
    return ok_response(data=alert.to_dict())

@bp.post("/run")
@require_menu_permission("inspection_manage")
def run_now():
    result = run_inspection_cycle(trigger="manual", force=True)
    if not result.get("ok"):
        if result.get("code") == 409:
            data = {**result, "already_running": True}
            return ok_response(data=data, message="巡检正在执行中，请稍后查看结果", code=202)
        return error_response(result.get("message") or "inspection run failed", code=result.get("code") or 500, data=result)
    log_audit(user_id=None, action="inspection.run.manual", target_type="inspection", target_id="global", detail=result.get("data"))
    return ok_response(data=result.get("data"), code=202)


@bp.get("/config")
@require_menu_permission("inspection_param_config")
def get_config():
    cached = get_json("dbms:config:inspection")
    if isinstance(cached, dict):
        return ok_response(data=cached)
    cfg = get_or_create_inspection_config()
    return ok_response(data=cfg.to_dict())


@bp.put("/config")
@require_menu_permission("inspection_param_config")
def update_config():
    payload = request.get_json(silent=True) or {}
    cfg = get_or_create_inspection_config()
    err = update_inspection_config(cfg, payload)
    if err:
        return error_response(err, code=400)
    db.session.commit()
    refresh_inspection_config_cache(cfg)
    if current_app.config.get("ENABLE_SCHEDULER"):
        sync_inspection_job(scheduler=scheduler, app=current_app)
    log_audit(user_id=None, action="inspection.config.update", target_type="inspection_config", target_id=str(cfg.id), detail=payload)
    return ok_response(data=cfg.to_dict())


@bp.get("/config/options")
@require_menu_permission("inspection_param_config")
def list_config_options():
    targets = (
        BackupNotifyTarget.query
        .filter(BackupNotifyTarget.enabled.is_(True))
        .order_by(BackupNotifyTarget.id.desc())
        .all()
    )
    clusters = DatabaseCluster.query.order_by(DatabaseCluster.id.desc()).all()
    return ok_response(
        data={
            "notify_targets": [item.to_dict() for item in targets],
            "clusters": [item.to_dict() for item in clusters],
        }
    )
