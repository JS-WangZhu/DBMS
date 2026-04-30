import json
import queue
import threading
from datetime import datetime
from types import SimpleNamespace

from flask import Blueprint, Response, current_app, request, stream_with_context
from sqlalchemy import Text, cast

from app.api.routes.common import active_user_required, get_current_user, list_allowed_cluster_ids, require_cluster_permission
from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.models.ha_config import HAConfig
from app.models.monitor_snapshot import snapshot_model_for_instance
from app.models.user import User
from app.services.monitor_snapshot_service import latest_snapshot_for_instance
from app.services.audit import log_audit
from app.services.collectors import collect_instance_metrics
from app.services.dns_resolver import list_host_addresses, resolve_host
from app.services.notifier import notify_ha_switch_completion
from app.services.mysql_ha_switch import build_cluster_topology, failure_switch, normal_switch, promote_current_master, repair_cluster
from app.utils.crypto import decrypt_secret
from app.utils.response import error_response, ok_response

bp = Blueprint("clusters", __name__, url_prefix="/clusters")


def _snapshot_failed(payload: dict) -> bool:
    if not isinstance(payload, dict):
        return True
    if payload.get("ok") is False:
        return True
    if payload.get("ping_ok") is False:
        return True
    return False


def _event_timestamp():
    return datetime.now().isoformat()


def _parse_switch_payload(payload: dict):
    switch_type = str(payload.get("switch_type") or "").strip().lower()
    target_instance_id = payload.get("target_instance_id")
    target_instance_ids = payload.get("target_instance_ids") or []
    lag_timeout_seconds = payload.get("lag_timeout_seconds", 60)

    if switch_type not in {"normal", "failure", "promote", "repair"}:
        raise ValueError("switch_type must be normal, failure, promote or repair")

    try:
        target_instance_id = int(target_instance_id) if target_instance_id not in (None, "") else None
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid target_instance_id") from exc

    if target_instance_ids not in (None, "") and not isinstance(target_instance_ids, list):
        raise ValueError("target_instance_ids must be a list")
    parsed_target_ids = []
    for item in target_instance_ids or []:
        try:
            parsed_target_ids.append(int(item))
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid target_instance_ids") from exc

    try:
        lag_timeout_seconds = int(lag_timeout_seconds)
    except (TypeError, ValueError):
        lag_timeout_seconds = 60

    return {
        "switch_type": switch_type,
        "target_instance_id": target_instance_id,
        "target_instance_ids": parsed_target_ids,
        "lag_timeout_seconds": max(lag_timeout_seconds, 10),
    }


def _build_sse_payload(data: dict):
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _ensure_ha_switch_enabled(cluster: DatabaseCluster):
    if not getattr(cluster, "ha_switch_enabled", False):
        raise RuntimeError("当前集群未启用高可用切换")


def _get_ha_notify_config(result: dict):
    script_result = result.get("switch_script") or {}
    config_id = script_result.get("script_config_id")
    if not config_id:
        return None
    return HAConfig.query.get(config_id)


def _safe_int(value, default_value: int):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default_value


def _parse_page_args():
    page = max(_safe_int(request.args.get("page"), 1), 1)
    page_size = min(max(_safe_int(request.args.get("page_size"), 20), 1), 200)
    return page, page_size


def _log_ha_switch_audit(
    cluster: DatabaseCluster,
    user,
    switch_type: str,
    target_instance_id,
    target_instance_ids=None,
    result=None,
    error_message=None,
):
    detail = {
        "cluster_id": cluster.id,
        "cluster_name": cluster.name,
        "business_line": cluster.business_line or cluster.namespace,
        "environment": cluster.environment,
        "switch_type": switch_type,
        "target_instance_id": target_instance_id,
        "target_instance_ids": target_instance_ids or [],
        "success": error_message is None,
        "error": error_message,
        "operator_username": user.username if user else None,
        "result": result,
    }
    log_audit(
        user_id=user.id if user else None,
        action=f"cluster.mysql.ha_switch.{switch_type}",
        target_type="cluster",
        target_id=str(cluster.id),
        detail=detail,
    )


def _build_ha_switch_history_item(row: AuditLog, user_name_map, instance_name_map):
    detail = row.detail_json or {}
    target_instance_id = detail.get("target_instance_id")
    target_instance_ids = detail.get("target_instance_ids") or []
    result = detail.get("result") or {}
    switch_script = result.get("switch_script") or {}
    return {
        "id": row.id,
        "action": row.action,
        "switch_type": detail.get("switch_type"),
        "cluster_id": detail.get("cluster_id"),
        "cluster_name": detail.get("cluster_name"),
        "business_line": detail.get("business_line"),
        "environment": detail.get("environment"),
        "target_instance_id": target_instance_id,
        "target_instance_name": instance_name_map.get(target_instance_id) or None,
        "target_instance_ids": target_instance_ids,
        "target_instance_names": [instance_name_map.get(item) or item for item in target_instance_ids],
        "operator_username": user_name_map.get(row.user_id) or detail.get("operator_username") or "未知用户",
        "success": bool(detail.get("success")),
        "error": detail.get("error"),
        "switch_script_name": switch_script.get("script_name"),
        "switch_command": switch_script.get("command") or [],
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _execute_ha_switch(
    cluster_id: int,
    user,
    switch_type: str,
    target_instance_id,
    target_instance_ids,
    lag_timeout_seconds: int,
    progress_callback=None,
):
    cluster = DatabaseCluster.query.get_or_404(cluster_id)

    if switch_type == "normal":
        if not target_instance_id:
            raise RuntimeError("target_instance_id is required for normal switch")
        result = normal_switch(
            cluster.id,
            target_instance_id=target_instance_id,
            lag_timeout_seconds=lag_timeout_seconds,
            progress_callback=progress_callback,
        )
    elif switch_type == "failure":
        result = failure_switch(
            cluster.id,
            target_instance_id=target_instance_id,
            progress_callback=progress_callback,
        )
    elif switch_type == "promote":
        result = promote_current_master(
            cluster.id,
            progress_callback=progress_callback,
        )
    else:
        result = repair_cluster(
            cluster.id,
            target_instance_ids=target_instance_ids,
            progress_callback=progress_callback,
        )

    notify_config = _get_ha_notify_config(result)
    notify_result = notify_ha_switch_completion(
        config=notify_config,
        cluster=cluster,
        switch_type=switch_type,
        result=result,
        operator_name=user.username if user else None,
    )
    result["notification"] = notify_result

    _log_ha_switch_audit(
        cluster=cluster,
        user=user,
        switch_type=switch_type,
        target_instance_id=target_instance_id or result.get("new_master_instance_id"),
        target_instance_ids=target_instance_ids or result.get("repair_target_instance_ids") or [],
        result=result,
    )
    return result


@bp.get("")
@active_user_required
def list_clusters():
    db_type = request.args.get("db_type")
    business_line = (request.args.get("business_line") or "").strip()
    environment = (request.args.get("environment") or "").strip()
    namespace = (request.args.get("namespace") or "").strip()
    action = (request.args.get("action") or "").strip().lower()

    query = DatabaseCluster.query
    if db_type:
        query = query.filter_by(db_type=db_type)
    if business_line:
        query = query.filter_by(business_line=business_line)
    elif namespace:
        query = query.filter_by(namespace=namespace)
    if environment:
        query = query.filter_by(environment=environment)
    user = get_current_user()
    if user and user.role != "admin" and action in {"query", "change"}:
        allowed_cluster_ids = list_allowed_cluster_ids(action)
        if not allowed_cluster_ids:
            return ok_response(data=[])
        query = query.filter(DatabaseCluster.id.in_(allowed_cluster_ids))

    items = query.order_by(DatabaseCluster.id.desc()).all()
    return ok_response(data=[item.to_dict() for item in items])


@bp.post("")
@active_user_required
def create_cluster():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    db_type = payload.get("db_type")
    business_line_raw = payload.get("business_line")
    environment_raw = payload.get("environment")
    namespace_raw = payload.get("namespace")
    business_line = str(business_line_raw).strip() if business_line_raw is not None else ""
    environment = str(environment_raw).strip() if environment_raw is not None else ""
    namespace = str(namespace_raw).strip() if namespace_raw is not None else ""
    description = payload.get("description")
    ha_domain = (payload.get("ha_domain") or "").strip() or None

    if not name or not db_type:
        return error_response("name and db_type are required", code=400)
    if db_type not in {"mysql", "redis", "doris", "mongodb"}:
        return error_response("invalid db_type", code=400)

    effective_business_line = business_line or namespace or ""
    cluster = DatabaseCluster(
        namespace=effective_business_line or None,
        business_line=effective_business_line or None,
        environment=environment or None,
        name=name,
        db_type=db_type,
        description=description,
        ha_domain=ha_domain,
    )
    db.session.add(cluster)
    db.session.commit()

    log_audit(user_id=None, action="cluster.create", target_type="cluster", target_id=str(cluster.id), detail=payload)
    return ok_response(data=cluster.to_dict(), code=201)


@bp.patch("/<int:cluster_id>")
@active_user_required
def update_cluster(cluster_id):
    payload = request.get_json(silent=True) or {}

    cluster = DatabaseCluster.query.get_or_404(cluster_id)

    if "business_line" in payload or "namespace" in payload:
        business_line = (payload.get("business_line") or payload.get("namespace") or "").strip()
        cluster.business_line = business_line or None
        cluster.namespace = business_line or None
    if "environment" in payload:
        environment = (payload.get("environment") or "").strip()
        cluster.environment = environment or None

    if "name" in payload:
        cluster.name = payload["name"]
    if "description" in payload:
        cluster.description = payload["description"]
    if "ha_domain" in payload:
        cluster.ha_domain = (payload.get("ha_domain") or "").strip() or None
    if "ha_switch_enabled" in payload:
        cluster.ha_switch_enabled = bool(payload.get("ha_switch_enabled"))

    db.session.commit()
    log_audit(user_id=None, action="cluster.update", target_type="cluster", target_id=str(cluster.id), detail=payload)

    return ok_response(data=cluster.to_dict())


@bp.delete("/<int:cluster_id>")
@active_user_required
def delete_cluster(cluster_id):
    cluster = DatabaseCluster.query.get_or_404(cluster_id)
    bound_instances = DatabaseInstance.query.filter_by(cluster_id=cluster.id).count()
    if bound_instances > 0:
        return error_response("cluster has bound instances, please delete/move instances first", code=400)

    detail = {
        "name": cluster.name,
        "business_line": cluster.business_line or cluster.namespace,
        "environment": cluster.environment,
        "db_type": cluster.db_type,
    }
    db.session.delete(cluster)
    db.session.commit()
    log_audit(user_id=None, action="cluster.delete", target_type="cluster", target_id=str(cluster.id), detail=detail)
    return ok_response(message="deleted")


@bp.post("/<int:cluster_id>/health/collect")
@active_user_required
def collect_cluster_health(cluster_id):
    """触发单集群立即健康检测并写入快照"""
    cluster = DatabaseCluster.query.get_or_404(cluster_id)
    instances = DatabaseInstance.query.filter_by(cluster_id=cluster.id, enabled=True).all()

    if not instances:
        return error_response("cluster has no enabled instances", code=400)

    results = []
    payload_map = {}
    for instance in instances:
        try:
            password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
            data = collect_instance_metrics(instance=instance, password=password) or {}
            payload = dict(data)
            payload.setdefault("ok", False)
            payload.setdefault("collected_at", datetime.now().isoformat())
            failed = _snapshot_failed(payload)
            instance.running_status = "error" if failed else "running"

            snapshot_model = snapshot_model_for_instance(instance)
            snapshot = snapshot_model(
                instance_id=instance.id,
                metric_type="status",
                payload_json=payload,
                collected_at=datetime.now(),
            )
            db.session.add(snapshot)
            payload_map[instance.id] = payload
            results.append(
                {
                    "instance_id": instance.id,
                    "instance_name": instance.name,
                    "status": "error" if failed else "ok",
                    "error": payload.get("error") if failed else None,
                }
            )
        except Exception as e:
            instance.running_status = "error"
            snapshot_model = snapshot_model_for_instance(instance)
            snapshot = snapshot_model(
                instance_id=instance.id,
                metric_type="status",
                payload_json={"ok": False, "error": str(e), "collected_at": datetime.now().isoformat()},
                collected_at=datetime.now(),
            )
            db.session.add(snapshot)
            payload_map[instance.id] = snapshot.payload_json
            results.append({"instance_id": instance.id, "instance_name": instance.name, "status": "error", "error": str(e)})

    if cluster.db_type == "mysql" and (cluster.ha_domain or "").strip():
        resolved_ip = resolve_host(cluster.ha_domain) or cluster.ha_domain
        matched_instance = None
        matched_writable = False
        for instance in instances:
            host = (instance.resolved_ip or instance.host_input or "").strip()
            if host != resolved_ip:
                continue
            payload = payload_map.get(instance.id) or {}
            matched_instance = instance
            matched_writable = bool(
                payload.get("ping_ok") is True and
                payload.get("replication_role") == "master" and
                payload.get("effective_read_only") is False
            )
            break

        cluster.ha_status_json = {
            "ha_domain": cluster.ha_domain,
            "resolved_ip": resolved_ip,
            "ok": bool(matched_instance and matched_writable),
            "matched_instance_id": matched_instance.id if matched_instance else None,
            "matched_instance_name": matched_instance.name if matched_instance else None,
            "matched_writable": matched_writable,
            "checked_at": datetime.now().isoformat(),
            "reason": None if (matched_instance and matched_writable) else ("resolved ip not found in cluster" if not matched_instance else "target instance is not writable master"),
        }

    db.session.commit()
    return ok_response(data={"cluster_id": cluster_id, "cluster_name": cluster.name, "results": results})


@bp.get("/<int:cluster_id>/health/latest")
@active_user_required
def cluster_latest_health(cluster_id):
    """获取集群所有实例的最新健康状态（从数据库读取）"""
    cluster = DatabaseCluster.query.get_or_404(cluster_id)
    instances = DatabaseInstance.query.filter_by(cluster_id=cluster.id, enabled=True).all()

    results = []
    for instance in instances:
        snapshot = latest_snapshot_for_instance(instance_id=instance.id, db_type=instance.db_type, metric_type="status")
        if snapshot:
            payload = snapshot.payload_json or {}
            failed = _snapshot_failed(payload)
            results.append({
                "instance_id": instance.id,
                "instance_name": instance.name,
                "running_status": "error" if failed else "running",
                "collected_at": snapshot.collected_at.isoformat() if snapshot.collected_at else None,
                "payload_json": payload,
            })
        else:
            results.append({
                "instance_id": instance.id,
                "instance_name": instance.name,
                "running_status": "unknown",
                "collected_at": None,
                "payload_json": None,
            })

    return ok_response(data={"cluster_id": cluster_id, "cluster_name": cluster.name, "instances": results})


@bp.post("/<int:cluster_id>/ha/check")
@active_user_required
def check_cluster_ha(cluster_id):
    cluster = DatabaseCluster.query.get_or_404(cluster_id)
    if cluster.db_type != "mysql":
        return error_response("ha check only supports mysql cluster", code=400)
    if not cluster.ha_domain:
        return error_response("ha_domain is empty", code=400)

    resolved_ip = resolve_host(cluster.ha_domain) or cluster.ha_domain
    instances = DatabaseInstance.query.filter_by(cluster_id=cluster.id, enabled=True).all()
    payload_map = {}
    for instance in instances:
        snapshot = latest_snapshot_for_instance(instance_id=instance.id, db_type=instance.db_type, metric_type="status")
        payload_map[instance.id] = snapshot.payload_json if snapshot else {}

    matched_instance = None
    matched_writable = False
    for instance in instances:
        host = (instance.resolved_ip or instance.host_input or "").strip()
        payload = payload_map.get(instance.id) or {}
        if host == resolved_ip:
            matched_instance = instance
            matched_writable = bool(
                payload.get("ping_ok") is True and
                payload.get("replication_role") == "master" and
                payload.get("effective_read_only") is False
            )
            break

    status = {
        "ha_domain": cluster.ha_domain,
        "resolved_ip": resolved_ip,
        "ok": bool(matched_instance and matched_writable),
        "matched_instance_id": matched_instance.id if matched_instance else None,
        "matched_instance_name": matched_instance.name if matched_instance else None,
        "matched_writable": matched_writable,
        "checked_at": datetime.now().isoformat(),
        "reason": None,
    }
    if not matched_instance:
        status["reason"] = "resolved ip not found in cluster"
    elif not matched_writable:
        status["reason"] = "target instance is not writable master"

    cluster.ha_status_json = status
    db.session.commit()
    return ok_response(data=status)


@bp.get("/<int:cluster_id>/ha/topology")
@active_user_required
def cluster_ha_topology(cluster_id):
    cluster = DatabaseCluster.query.get_or_404(cluster_id)
    if cluster.db_type != "mysql":
        return error_response("ha topology only supports mysql cluster", code=400)
    if not cluster.ha_switch_enabled:
        return error_response("当前集群未启用高可用切换", code=400)
    if not require_cluster_permission(cluster.id, "query"):
        return error_response("permission denied", code=403)
    try:
        data = build_cluster_topology(cluster.id)
        if cluster.ha_domain:
            cluster.ha_status_json = {
                "ha_domain": cluster.ha_domain,
                "resolved_ip": resolve_host(cluster.ha_domain) or cluster.ha_domain,
                "resolved_servers": list_host_addresses(cluster.ha_domain),
                "matched_instance_id": data.get("current_master_instance_id"),
                "matched_instance_name": data.get("current_master_instance_name"),
                "matched_writable": bool(data.get("current_master_instance_id")),
                "checked_at": datetime.now().isoformat(),
                "ok": bool(data.get("current_master_instance_id")),
                "reason": None if data.get("current_master_instance_id") else "current writable master not found",
            }
            db.session.commit()
        return ok_response(data=data)
    except ValueError as exc:
        return error_response(str(exc), code=400)
    except Exception as exc:
        return error_response(str(exc), code=500)


@bp.get("/<int:cluster_id>/ha/history")
@active_user_required
def cluster_ha_switch_history(cluster_id):
    cluster = DatabaseCluster.query.get_or_404(cluster_id)
    if cluster.db_type != "mysql":
        return error_response("ha switch only supports mysql cluster", code=400)
    if not require_cluster_permission(cluster.id, "query"):
        return error_response("permission denied", code=403)

    page, page_size = _parse_page_args()
    keyword = (request.args.get("keyword") or "").strip()
    query = AuditLog.query.filter(
        AuditLog.action.like("cluster.mysql.ha_switch.%"),
        AuditLog.target_type == "cluster",
        AuditLog.target_id == str(cluster.id),
    )
    if keyword:
        query = query.filter(cast(AuditLog.detail_json, Text).ilike(f"%{keyword}%"))

    total = query.count()
    rows = (
        query.order_by(AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    user_ids = sorted({row.user_id for row in rows if row.user_id})
    users = User.query.filter(User.id.in_(user_ids)).all() if user_ids else []
    user_name_map = {item.id: item.username for item in users}
    instance_ids = set()
    for row in rows:
        detail = row.detail_json or {}
        if detail.get("target_instance_id"):
            instance_ids.add(detail.get("target_instance_id"))
        for item in detail.get("target_instance_ids") or []:
            if item:
                instance_ids.add(item)
    instances = DatabaseInstance.query.filter(DatabaseInstance.id.in_(instance_ids)).all() if instance_ids else []
    instance_name_map = {item.id: item.name for item in instances}
    return ok_response(
        data={
            "items": [_build_ha_switch_history_item(row, user_name_map, instance_name_map) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@bp.post("/<int:cluster_id>/ha/switch")
@active_user_required
def cluster_ha_switch(cluster_id):
    cluster = DatabaseCluster.query.get_or_404(cluster_id)
    if cluster.db_type != "mysql":
        return error_response("ha switch only supports mysql cluster", code=400)
    try:
        _ensure_ha_switch_enabled(cluster)
    except RuntimeError as exc:
        return error_response(str(exc), code=400)
    if not require_cluster_permission(cluster.id, "change"):
        return error_response("permission denied", code=403)

    payload = request.get_json(silent=True) or {}
    try:
        parsed = _parse_switch_payload(payload)
    except ValueError as exc:
        return error_response(str(exc), code=400)

    try:
        user = get_current_user()
        result = _execute_ha_switch(
            cluster_id=cluster.id,
            user=user,
            switch_type=parsed["switch_type"],
            target_instance_id=parsed["target_instance_id"],
            target_instance_ids=parsed["target_instance_ids"],
            lag_timeout_seconds=parsed["lag_timeout_seconds"],
        )
        return ok_response(data=result, message="高可用操作执行成功")
    except RuntimeError as exc:
        _log_ha_switch_audit(
            cluster=cluster,
            user=get_current_user(),
            switch_type=parsed["switch_type"],
            target_instance_id=parsed["target_instance_id"],
            target_instance_ids=parsed["target_instance_ids"],
            error_message=str(exc),
        )
        return error_response(str(exc), code=400)
    except Exception as exc:
        _log_ha_switch_audit(
            cluster=cluster,
            user=get_current_user(),
            switch_type=parsed["switch_type"],
            target_instance_id=parsed["target_instance_id"],
            target_instance_ids=parsed["target_instance_ids"],
            error_message=str(exc),
        )
        return error_response(str(exc), code=500)


@bp.post("/<int:cluster_id>/ha/switch/stream")
@active_user_required
def cluster_ha_switch_stream(cluster_id):
    cluster = DatabaseCluster.query.get_or_404(cluster_id)
    if cluster.db_type != "mysql":
        return error_response("ha switch only supports mysql cluster", code=400)
    try:
        _ensure_ha_switch_enabled(cluster)
    except RuntimeError as exc:
        return error_response(str(exc), code=400)
    if not require_cluster_permission(cluster.id, "change"):
        return error_response("permission denied", code=403)

    payload = request.get_json(silent=True) or {}
    try:
        parsed = _parse_switch_payload(payload)
    except ValueError as exc:
        return error_response(str(exc), code=400)

    user = get_current_user()
    user_info = {
        "id": user.id if user else None,
        "username": user.username if user else None,
    }
    event_queue = queue.Queue()

    def push_event(event_type: str, message: str = None, data=None):
        event = {"type": event_type, "timestamp": _event_timestamp()}
        if message is not None:
            event["message"] = message
        if data is not None:
            event["data"] = data
        event_queue.put(event)

    def worker(flask_app):
        with flask_app.app_context():
            try:
                push_event("started", message="开始执行高可用操作")
                result = _execute_ha_switch(
                    cluster_id=cluster.id,
                    user=SimpleNamespace(**user_info),
                    switch_type=parsed["switch_type"],
                    target_instance_id=parsed["target_instance_id"],
                    target_instance_ids=parsed["target_instance_ids"],
                    lag_timeout_seconds=parsed["lag_timeout_seconds"],
                    progress_callback=lambda step: push_event("step", data=step),
                )
                push_event("completed", message="高可用操作执行成功", data=result)
            except RuntimeError as exc:
                _log_ha_switch_audit(
                    cluster=cluster,
                    user=SimpleNamespace(**user_info),
                    switch_type=parsed["switch_type"],
                    target_instance_id=parsed["target_instance_id"],
                    target_instance_ids=parsed["target_instance_ids"],
                    error_message=str(exc),
                )
                push_event("error", message=str(exc))
            except Exception as exc:
                _log_ha_switch_audit(
                    cluster=cluster,
                    user=SimpleNamespace(**user_info),
                    switch_type=parsed["switch_type"],
                    target_instance_id=parsed["target_instance_id"],
                    target_instance_ids=parsed["target_instance_ids"],
                    error_message=str(exc),
                )
                push_event("error", message=str(exc))
            finally:
                db.session.remove()
                push_event("done")

    thread = threading.Thread(target=worker, args=(current_app._get_current_object(),), daemon=True)
    thread.start()

    def generate():
        while True:
            event = event_queue.get()
            yield _build_sse_payload(event)
            if event.get("type") == "done":
                break

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
