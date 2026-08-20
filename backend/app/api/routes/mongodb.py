from flask import Blueprint, request

from app.api.routes.common import active_user_required, admin_required, get_current_user, list_allowed_cluster_ids, require_cluster_permission, require_menu_permission
from app.models.db_asset import DatabaseInstance
from app.services.monitor_snapshot_service import latest_snapshot_for_instance
from app.services.audit import log_audit
from app.services.instance_service import create_instance, list_instances_paginated
from app.services.mongodb_session_probe import (
    SessionProbeError,
    close_probe_session,
    fetch_operations,
    get_probe_instance_id,
    kill_operation,
    start_probe_session,
)
from app.utils.crypto import decrypt_secret
from app.utils.response import error_response, ok_response

bp = Blueprint("mongodb", __name__, url_prefix="/mongodb")


def _session_probe_error(exc):
    message = str(exc)
    if "does not belong" in message:
        return error_response(message, code=403)
    if "not found or expired" in message or message.endswith("expired"):
        return error_response(message, code=410)
    if "connect failed" in message or "fetch failed" in message or "kill mongodb" in message:
        return error_response(message, code=502)
    return error_response(message, code=400)


def _require_probe_cluster_permission(token, action):
    user = get_current_user()
    try:
        instance_id = get_probe_instance_id(token=token, user_id=user.id)
    except SessionProbeError as exc:
        return None, _session_probe_error(exc)
    instance = DatabaseInstance.query.filter_by(id=instance_id, db_type="mongodb").first()
    if not instance:
        return None, error_response("mongodb instance not found", code=404)
    if not require_cluster_permission(instance.cluster_id, action):
        return None, error_response("cluster permission denied", code=403)
    return instance, None


@bp.get("/instances")
@require_menu_permission("mongodb_instances")
def mongodb_list_instances():
    page = request.args.get("page", 1)
    page_size = request.args.get('page_size', 10)
    keyword = request.args.get("keyword")
    cluster_id = request.args.get("cluster_id")
    namespace = request.args.get("namespace")
    business_line = request.args.get("business_line")
    environment = request.args.get("environment")
    items, total, page, page_size = list_instances_paginated(
        db_type="mongodb",
        page=page,
        page_size=page_size,
        keyword=keyword,
        cluster_id=cluster_id,
        namespace=namespace,
        business_line=business_line,
        environment=environment,
        allowed_cluster_ids=list_allowed_cluster_ids("view_instance"),
    )
    return ok_response(
        data={
            "items": [item.to_dict() for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@bp.post("/instances")
@admin_required
def mongodb_create_instance():
    payload = request.get_json(silent=True) or {}
    instance, err = create_instance(payload, db_type="mongodb")
    if err:
        return error_response(err, code=400)

    log_audit(user_id=None, action="mongodb.instance.create", target_type="instance", target_id=str(instance.id), detail=payload)
    return ok_response(data=instance.to_dict(), code=201)


@bp.get("/instances/<int:instance_id>/replica-status")
@require_menu_permission("mongodb_instances")
def mongodb_replica_status(instance_id):
    instance = DatabaseInstance.query.filter_by(id=instance_id, db_type="mongodb").first()
    if not instance:
        return error_response("mongodb instance not found", code=404)
    if not require_cluster_permission(instance.cluster_id, "view_instance"):
        return error_response("cluster permission denied", code=403)

    snapshot = latest_snapshot_for_instance(instance_id=instance.id, db_type=instance.db_type, metric_type="status")
    payload = snapshot.payload_json if snapshot else {}
    if not isinstance(payload, dict):
        payload = {}
    repl = payload.get("repl", {})
    if not isinstance(repl, dict):
        repl = {}
    return ok_response(data={"instance_id": instance.id, "repl": repl})


@bp.post("/session-probes")
@require_menu_permission("mongodb_session_probe")
def start_mongodb_session_probe():
    payload = request.get_json(silent=True) or {}
    try:
        instance_id = int(payload.get("instance_id"))
    except (TypeError, ValueError):
        return error_response("instance_id is required", code=400)
    instance = DatabaseInstance.query.filter_by(id=instance_id, db_type="mongodb", enabled=True).first()
    if not instance:
        return error_response("mongodb instance not found", code=404)
    if not require_cluster_permission(instance.cluster_id, "query"):
        return error_response("cluster permission denied", code=403)
    user = get_current_user()
    password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else ""
    try:
        data = start_probe_session(instance=instance, password=password, user_id=user.id)
    except SessionProbeError as exc:
        return _session_probe_error(exc)
    log_audit(user_id=user.id, action="mongodb.session_probe.start", target_type="instance", target_id=str(instance.id), detail={"expires_at": data.get("expires_at")})
    data["can_kill"] = require_cluster_permission(instance.cluster_id, "change")
    return ok_response(data=data, code=201)


@bp.get("/session-probes/<string:token>/operations")
@require_menu_permission("mongodb_session_probe")
def get_mongodb_operations(token):
    _, permission_error = _require_probe_cluster_permission(token, "query")
    if permission_error:
        return permission_error
    try:
        data = fetch_operations(token=token, user_id=get_current_user().id)
    except SessionProbeError as exc:
        return _session_probe_error(exc)
    return ok_response(data=data)


@bp.post("/session-probes/<string:token>/kill")
@require_menu_permission("mongodb_session_probe")
def kill_mongodb_operation(token):
    _, permission_error = _require_probe_cluster_permission(token, "change")
    if permission_error:
        return permission_error
    payload = request.get_json(silent=True) or {}
    operation_id = payload.get("operation_id")
    if operation_id is None or not str(operation_id).strip():
        return error_response("operation_id is required", code=400)
    try:
        data = kill_operation(token=token, user_id=get_current_user().id, operation_id=operation_id)
    except SessionProbeError as exc:
        return _session_probe_error(exc)
    log_audit(user_id=get_current_user().id, action="mongodb.session_probe.kill", target_type="mongodb_operation", target_id=str(operation_id), detail={"probe_token_prefix": token[:8]})
    return ok_response(data=data)


@bp.post("/session-probes/<string:token>/stop")
@require_menu_permission("mongodb_session_probe")
def stop_mongodb_session_probe(token):
    try:
        closed = close_probe_session(token=token, user_id=get_current_user().id)
    except SessionProbeError as exc:
        return _session_probe_error(exc)
    return ok_response(data={"closed": closed})
