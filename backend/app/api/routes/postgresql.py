from flask import Blueprint, request

from app.api.routes.common import admin_required, get_current_user, list_allowed_cluster_ids, require_cluster_permission, require_menu_permission
from app.models.db_asset import DatabaseInstance
from app.services.audit import log_audit
from app.services.instance_service import create_instance, list_instances_paginated
from app.services.monitor_snapshot_service import latest_snapshot_for_instance
from app.services.postgresql_session_probe import (
    SessionProbeError,
    close_probe_session,
    fetch_sessions,
    get_probe_instance_id,
    start_probe_session,
    terminate_backend,
)
from app.utils.crypto import decrypt_secret
from app.utils.response import error_response, ok_response


bp = Blueprint("postgresql", __name__, url_prefix="/postgresql")


def _session_probe_error(exc):
    message = str(exc)
    if "does not belong" in message:
        return error_response(message, code=403)
    if "not found or expired" in message or message.endswith("expired"):
        return error_response(message, code=410)
    if "connect failed" in message or "fetch failed" in message or "terminate postgresql" in message:
        return error_response(message, code=502)
    return error_response(message, code=400)


def _require_probe_cluster_permission(token, action):
    user = get_current_user()
    try:
        instance_id = get_probe_instance_id(token=token, user_id=user.id)
    except SessionProbeError as exc:
        return None, _session_probe_error(exc)
    instance = DatabaseInstance.query.filter_by(id=instance_id, db_type="postgresql").first()
    if not instance:
        return None, error_response("postgresql instance not found", code=404)
    if not require_cluster_permission(instance.cluster_id, action):
        return None, error_response("cluster permission denied", code=403)
    return instance, None


@bp.get("/instances")
@require_menu_permission("postgresql_instances")
def postgresql_list_instances():
    items, total, page, page_size = list_instances_paginated(
        db_type="postgresql",
        page=request.args.get("page", 1),
        page_size=request.args.get("page_size", 10),
        keyword=request.args.get("keyword"),
        cluster_id=request.args.get("cluster_id"),
        namespace=request.args.get("namespace"),
        business_line=request.args.get("business_line"),
        environment=request.args.get("environment"),
        allowed_cluster_ids=list_allowed_cluster_ids("view_instance"),
    )
    return ok_response(data={"items": [item.to_dict() for item in items], "total": total, "page": page, "page_size": page_size})


@bp.post("/instances")
@admin_required
def postgresql_create_instance():
    payload = request.get_json(silent=True) or {}
    instance, err = create_instance(payload, db_type="postgresql")
    if err:
        return error_response(err, code=400)
    log_audit(user_id=None, action="postgresql.instance.create", target_type="instance", target_id=str(instance.id), detail=payload)
    return ok_response(data=instance.to_dict(), code=201)


@bp.get("/instances/<int:instance_id>/status")
@require_menu_permission("postgresql_instances")
def postgresql_status(instance_id):
    instance = DatabaseInstance.query.filter_by(id=instance_id, db_type="postgresql").first()
    if not instance:
        return error_response("postgresql instance not found", code=404)
    if not require_cluster_permission(instance.cluster_id, "view_instance"):
        return error_response("cluster permission denied", code=403)
    snapshot = latest_snapshot_for_instance(instance_id=instance.id, db_type=instance.db_type, metric_type="status")
    return ok_response(data=snapshot.payload_json if snapshot else {"instance_id": instance.id})


@bp.post("/session-probes")
@require_menu_permission("postgresql_session_probe")
def start_postgresql_session_probe():
    payload = request.get_json(silent=True) or {}
    try:
        instance_id = int(payload.get("instance_id"))
    except (TypeError, ValueError):
        return error_response("instance_id is required", code=400)
    instance = DatabaseInstance.query.filter_by(id=instance_id, db_type="postgresql", enabled=True).first()
    if not instance:
        return error_response("postgresql instance not found", code=404)
    if not require_cluster_permission(instance.cluster_id, "query"):
        return error_response("cluster permission denied", code=403)
    password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else ""
    user = get_current_user()
    try:
        data = start_probe_session(instance=instance, password=password, user_id=user.id)
    except SessionProbeError as exc:
        return _session_probe_error(exc)
    log_audit(user_id=user.id, action="postgresql.session_probe.start", target_type="instance", target_id=str(instance.id), detail={"expires_at": data.get("expires_at")})
    data["can_kill"] = require_cluster_permission(instance.cluster_id, "change")
    return ok_response(data=data, code=201)


@bp.get("/session-probes/<string:token>/sessions")
@require_menu_permission("postgresql_session_probe")
def get_postgresql_sessions(token):
    _, permission_error = _require_probe_cluster_permission(token, "query")
    if permission_error:
        return permission_error
    try:
        data = fetch_sessions(token=token, user_id=get_current_user().id)
    except SessionProbeError as exc:
        return _session_probe_error(exc)
    return ok_response(data=data)


@bp.post("/session-probes/<string:token>/kill")
@require_menu_permission("postgresql_session_probe")
def kill_postgresql_session(token):
    _, permission_error = _require_probe_cluster_permission(token, "change")
    if permission_error:
        return permission_error
    payload = request.get_json(silent=True) or {}
    try:
        process_id = int(payload.get("process_id"))
        data = terminate_backend(token=token, user_id=get_current_user().id, process_id=process_id)
    except (TypeError, ValueError):
        return error_response("process_id is required", code=400)
    except SessionProbeError as exc:
        return _session_probe_error(exc)
    log_audit(user_id=get_current_user().id, action="postgresql.session_probe.kill", target_type="postgresql_process", target_id=str(process_id), detail={"probe_token_prefix": token[:8]})
    return ok_response(data=data)


@bp.post("/session-probes/<string:token>/stop")
@require_menu_permission("postgresql_session_probe")
def stop_postgresql_session_probe(token):
    try:
        closed = close_probe_session(token=token, user_id=get_current_user().id)
    except SessionProbeError as exc:
        return _session_probe_error(exc)
    return ok_response(data={"closed": closed})
