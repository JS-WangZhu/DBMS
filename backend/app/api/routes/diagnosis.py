import threading

from flask import Blueprint, current_app, request
from sqlalchemy import or_

from app.api.routes.common import (
    admin_required,
    get_current_user,
    list_allowed_cluster_ids,
    require_cluster_permission,
    require_menu_permission,
)
from app.extensions import db, scheduler
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.models.diagnosis import ParameterCollectionSnapshot
from app.services.audit import log_audit
from app.services.diagnosis import (
    get_or_create_parameter_collection_config,
    is_parameter_collection_running,
    prune_parameter_versions,
    run_parameter_collection,
    update_parameter_collection_config,
)
from app.tasks.scheduler import _trigger_from_expr, sync_parameter_collection_job
from app.utils.response import error_response, ok_response


bp = Blueprint("diagnosis", __name__, url_prefix="/diagnosis")


def _parse_pagination():
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = max(1, min(100, int(request.args.get("page_size", 20))))
    except (TypeError, ValueError):
        page_size = 20
    return page, page_size


@bp.get("/parameter-check/config")
@require_menu_permission("diagnosis_parameter_check")
def get_parameter_config():
    config = get_or_create_parameter_collection_config()
    data = config.to_dict()
    data["running"] = is_parameter_collection_running()
    job = scheduler.get_job("diagnosis_parameter_collection") if scheduler.running else None
    data["next_run_at"] = job.next_run_time.isoformat() if job and job.next_run_time else None
    return ok_response(data=data)


@bp.put("/parameter-check/config")
@admin_required
def update_parameter_config():
    payload = request.get_json(silent=True) or {}
    config = get_or_create_parameter_collection_config()
    err = update_parameter_collection_config(config, payload)
    if err:
        return error_response(err, code=400)
    try:
        _trigger_from_expr(config.cron_expr)
    except Exception:
        db.session.rollback()
        return error_response("invalid cron_expr", code=400)
    prune_parameter_versions(config.retention_versions)
    db.session.commit()
    if current_app.config.get("ENABLE_SCHEDULER"):
        sync_parameter_collection_job(scheduler, current_app)
    user = get_current_user()
    log_audit(user_id=user.id if user else None, action="diagnosis.parameter_config.update", target_type="parameter_collection_config", target_id=str(config.id), detail=payload)
    return ok_response(data=config.to_dict())


def _run_async(app):
    with app.app_context():
        run_parameter_collection()


@bp.post("/parameter-check/collect")
@admin_required
def collect_parameters_now():
    if is_parameter_collection_running():
        return error_response("parameter collection is already running", code=409)
    app = current_app._get_current_object()
    threading.Thread(target=_run_async, args=(app,), name="parameter-collection-manual", daemon=True).start()
    user = get_current_user()
    log_audit(user_id=user.id if user else None, action="diagnosis.parameter_collection.run", target_type="parameter_collection", target_id="manual", detail={})
    return ok_response(message="parameter collection started", code=202)


@bp.get("/parameter-check/instances")
@require_menu_permission("diagnosis_parameter_check")
def list_parameter_instances():
    page, page_size = _parse_pagination()
    query = DatabaseInstance.query
    user = get_current_user()
    if user.role != "admin":
        allowed = list_allowed_cluster_ids("view_instance") or []
        query = query.filter(DatabaseInstance.cluster_id.in_(allowed))
    db_type = str(request.args.get("db_type") or "").strip().lower()
    keyword = str(request.args.get("keyword") or "").strip()
    business_line = str(request.args.get("business_line") or "").strip()
    environment = str(request.args.get("environment") or "").strip()
    raw_cluster_id = request.args.get("cluster_id")
    try:
        cluster_id = int(raw_cluster_id or 0)
    except (TypeError, ValueError):
        return error_response("invalid cluster_id", code=400)
    if raw_cluster_id not in (None, "") and cluster_id <= 0:
        return error_response("invalid cluster_id", code=400)
    if db_type:
        query = query.filter(DatabaseInstance.db_type == db_type)
    if business_line or environment:
        query = query.join(DatabaseCluster, DatabaseInstance.cluster_id == DatabaseCluster.id)
    if business_line:
        query = query.filter(or_(
            DatabaseCluster.business_line == business_line,
            DatabaseCluster.namespace == business_line,
        ))
    if environment:
        query = query.filter(DatabaseCluster.environment == environment)
    if cluster_id > 0:
        query = query.filter(DatabaseInstance.cluster_id == cluster_id)
    if keyword:
        escaped = keyword.replace("%", "\\%").replace("_", "\\_")
        query = query.filter(DatabaseInstance.name.ilike(f"%{escaped}%", escape="\\"))
    total = query.count()
    instances = query.order_by(DatabaseInstance.id.asc()).offset((page - 1) * page_size).limit(page_size).all()
    items = []
    for instance in instances:
        latest = (
            ParameterCollectionSnapshot.query.filter_by(instance_id=instance.id)
            .order_by(ParameterCollectionSnapshot.collected_at.desc(), ParameterCollectionSnapshot.id.desc())
            .first()
        )
        items.append({
            "instance_id": instance.id,
            "instance_name": instance.name,
            "db_type": instance.db_type,
            "host": instance.resolved_ip or instance.host_input,
            "port": instance.port,
            "cluster_id": instance.cluster_id,
            "cluster_name": instance.cluster.name if instance.cluster else None,
            "business_line": (instance.cluster.business_line or instance.cluster.namespace) if instance.cluster else None,
            "environment": instance.cluster.environment if instance.cluster else None,
            "access_mode": instance.access_mode or "server",
            "latest": latest.to_dict(include_parameters=False) if latest else None,
        })
    return ok_response(data={"items": items, "total": total, "page": page, "page_size": page_size})


@bp.get("/parameter-check/instances/<int:instance_id>/versions")
@require_menu_permission("diagnosis_parameter_check")
def list_parameter_versions(instance_id):
    instance = DatabaseInstance.query.get(instance_id)
    if not instance:
        return error_response("instance not found", code=404)
    user = get_current_user()
    if user.role != "admin" and (not instance.cluster_id or not require_cluster_permission(instance.cluster_id, "view_instance")):
        return error_response("cluster permission denied", code=403)
    config = get_or_create_parameter_collection_config()
    versions = (
        ParameterCollectionSnapshot.query.filter_by(instance_id=instance.id)
        .order_by(ParameterCollectionSnapshot.collected_at.desc(), ParameterCollectionSnapshot.id.desc())
        .limit(max(1, int(config.retention_versions or 3)))
        .all()
    )
    return ok_response(data={"instance": instance.to_dict(), "versions": [item.to_dict() for item in versions]})


@bp.get("/slow-query/capabilities")
@require_menu_permission("diagnosis_slow_query")
def slow_query_capabilities():
    return ok_response(data={
        "available": False,
        "source": "ClickHouse",
        "message": "慢日志解析程序与 ClickHouse 查询接口尚未接入",
        "planned_features": ["慢 SQL 检索", "指纹聚合", "趋势分析", "治理状态跟踪"],
    })
