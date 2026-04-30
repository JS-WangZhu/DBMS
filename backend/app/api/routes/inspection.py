from flask import Blueprint, current_app, request

from app.api.routes.common import get_current_user, list_allowed_cluster_ids, require_menu_permission
from app.extensions import db, scheduler
from app.models.db_asset import DatabaseCluster
from app.models.notify_target import BackupNotifyTarget
from app.services.audit import log_audit
from app.services.inspection_service import (
    get_or_create_inspection_config,
    inspection_overview,
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
    user = get_current_user()
    if user and user.role != "admin":
        allowed = list_allowed_cluster_ids("query") or []
        if cluster_id and cluster_id not in allowed:
            return ok_response(data={"items": [], "summary": {"total": 0, "abnormal": 0, "normal": 0}})
        if not cluster_id and not allowed:
            return ok_response(data={"items": [], "summary": {"total": 0, "abnormal": 0, "normal": 0}})
    data = inspection_overview(db_type=db_type, cluster_id=cluster_id, status=status)
    if user and user.role != "admin":
        allowed = set(list_allowed_cluster_ids("query") or [])
        if allowed:
            data["items"] = [item for item in data["items"] if item.get("cluster_id") in allowed]
            total = len(data["items"])
            abnormal = sum(1 for item in data["items"] if item.get("inspection_status") == "abnormal")
            data["summary"] = {"total": total, "abnormal": abnormal, "normal": total - abnormal}
        else:
            data = {"items": [], "summary": {"total": 0, "abnormal": 0, "normal": 0}}
    return ok_response(data=data)


@bp.post("/run")
@require_menu_permission("inspection_manage")
def run_now():
    result = run_inspection_cycle(trigger="manual", force=True)
    if not result.get("ok"):
        return error_response(result.get("message") or "inspection run failed", code=result.get("code") or 500, data=result)
    log_audit(user_id=None, action="inspection.run.manual", target_type="inspection", target_id="global", detail=result.get("data"))
    return ok_response(data=result.get("data"), code=202)


@bp.get("/config")
@require_menu_permission("inspection_param_config")
def get_config():
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
