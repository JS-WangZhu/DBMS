from flask import Blueprint, current_app, request

from app.api.routes.common import active_user_required, admin_required, require_menu_permission
from app.extensions import db, scheduler
from app.models.db_asset import DatabaseInstance
from app.models.monitor_snapshot import snapshot_model_for_instance
from app.services.audit import log_audit
from app.services.dns_resolver import resolve_and_update_instance
from app.services.instance_status_config import get_or_create_instance_status_config, refresh_instance_status_config_cache, update_instance_status_config
from app.services.redis_cache import get_json
from app.services.instance_service import (
    create_instance as create_instance_by_type,
    invalidate_instance_list_cache,
    list_instances as list_instances_by_type,
    update_instance as update_instance_entity,
)
from app.tasks.scheduler import sync_cache_warm_job, sync_monitor_collect_job
from app.utils.response import error_response, ok_response

bp = Blueprint("instances", __name__, url_prefix="/instances")


@bp.get("")
@active_user_required
def list_instances():
    db_type = request.args.get("db_type")
    enabled = request.args.get("enabled")

    parsed_enabled = None if enabled is None else (enabled.lower() == "true")
    items = list_instances_by_type(db_type=db_type, enabled=parsed_enabled)
    return ok_response(data=[item if isinstance(item, dict) else item.to_dict() for item in items])


@bp.get("/status-config")
@active_user_required
def get_status_config():
    cached = get_json("dbms:config:instance_status")
    if isinstance(cached, dict):
        return ok_response(data=cached)
    cfg = get_or_create_instance_status_config()
    return ok_response(data=cfg.to_dict())


@bp.put("/status-config")
@require_menu_permission("instance_status_config")
def update_status_config():
    payload = request.get_json(silent=True) or {}
    cfg = get_or_create_instance_status_config()
    err = update_instance_status_config(cfg, payload)
    if err:
        return error_response(err, code=400)
    db.session.commit()
    refresh_instance_status_config_cache(cfg)
    if current_app.config.get("ENABLE_SCHEDULER"):
        sync_monitor_collect_job(scheduler=scheduler, app=current_app)
        sync_cache_warm_job(scheduler=scheduler, app=current_app)
    log_audit(user_id=None, action="instance.status_config.update", target_type="instance_status_config", target_id=str(cfg.id), detail=payload)
    return ok_response(data=cfg.to_dict())


@bp.post("")
@admin_required
def create_instance():
    payload = request.get_json(silent=True) or {}

    db_type = payload.get("db_type")
    if not db_type:
        return error_response("db_type is required", code=400)
    if db_type not in {"mysql", "redis", "doris", "mongodb"}:
        return error_response("invalid db_type", code=400)

    instance, err = create_instance_by_type(payload, db_type=db_type)
    if err:
        return error_response(err, code=400)

    invalidate_instance_list_cache()
    log_audit(user_id=None, action="instance.create", target_type="instance", target_id=str(instance.id), detail=payload)
    return ok_response(data=instance.to_dict(), code=201)


@bp.patch("/<int:instance_id>")
@admin_required
def update_instance(instance_id):
    payload = request.get_json(silent=True) or {}
    instance = DatabaseInstance.query.get_or_404(instance_id)

    try:
        update_instance_entity(instance, payload)
    except ValueError as exc:
        return error_response(str(exc), code=400)
    invalidate_instance_list_cache()
    log_audit(user_id=None, action="instance.update", target_type="instance", target_id=str(instance.id), detail=payload)

    return ok_response(data=instance.to_dict())


@bp.delete("/<int:instance_id>")
@admin_required
def delete_instance(instance_id):
    instance = DatabaseInstance.query.get_or_404(instance_id)
    detail = {"name": instance.name, "db_type": instance.db_type, "host_input": instance.host_input, "port": instance.port}
    try:
        snapshot_model = snapshot_model_for_instance(instance)
        snapshot_model.query.filter_by(instance_id=instance.id).delete(synchronize_session=False)
        db.session.delete(instance)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return error_response(f"delete instance failed: {exc}", code=500)

    invalidate_instance_list_cache()
    log_audit(user_id=None, action="instance.delete", target_type="instance", target_id=str(instance.id), detail=detail)
    return ok_response(message="deleted")


@bp.post("/<int:instance_id>/resolve")
@active_user_required
def resolve_instance(instance_id):
    instance = DatabaseInstance.query.get_or_404(instance_id)
    changed, old_ip, new_ip = resolve_and_update_instance(instance)
    db.session.commit()
    invalidate_instance_list_cache()

    log_audit(
        user_id=None,
        action="dns.resolve.manual",
        target_type="instance",
        target_id=str(instance.id),
        detail={"changed": changed, "old_ip": old_ip, "new_ip": new_ip},
    )

    return ok_response(data={"changed": changed, "old_ip": old_ip, "new_ip": new_ip, "instance": instance.to_dict()})
