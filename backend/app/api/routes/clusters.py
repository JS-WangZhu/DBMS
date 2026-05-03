import json
import queue
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from flask import Blueprint, Response, current_app, request, stream_with_context
from sqlalchemy import Text, cast, func

from app.api.routes.common import active_user_required, admin_required, get_current_user, list_allowed_cluster_ids, require_cluster_permission
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
from app.services.topology_history import list_topology_history
from app.utils.crypto import decrypt_secret
from app.utils.response import error_response, ok_response

bp = Blueprint("clusters", __name__, url_prefix="/clusters")

# 统一使用北京时间（UTC+8）输出给前端，避免服务器本地时区导致偏差。
_BEIJING_TZ = timezone(timedelta(hours=8))


def _beijing_now_iso():
    """返回带北京时区后缀的当前时间 ISO 字符串。
    直接取服务器本地挂钟（假定部署环境本地时间即北京时间），附加 +08:00 后缀，
    避免 Unix epoch 被错配为北京时间时再 astimezone 多加一次 8 小时。
    """
    return datetime.now().replace(microsecond=0, tzinfo=_BEIJING_TZ).isoformat()


def _beijing_iso(dt):
    """将 DB 中 naive datetime 或任意 datetime 统一输出为带 +08:00 后缀的 ISO 字符串。
    naive 值视为已经是北京时间（服务器本地时间 == 北京时间），直接挂 tz；
    aware 值则 astimezone 到 +08:00。返回 None 对应 None。
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_BEIJING_TZ).isoformat()
    return dt.astimezone(_BEIJING_TZ).isoformat()


def _snapshot_failed(payload: dict) -> bool:
    if not isinstance(payload, dict):
        return True
    if payload.get("ok") is False:
        return True
    if payload.get("ping_ok") is False:
        return True
    return False


def _event_timestamp():
    return _beijing_now_iso()


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


@bp.get("/stats")
@active_user_required
def cluster_stats():
    """获取集群统计数据：按业务统计和按数据库类型统计"""
    user = get_current_user()
    query = DatabaseCluster.query

    # 非管理员只能看到有权限的集群
    if user and user.role != "admin":
        allowed_cluster_ids = list_allowed_cluster_ids("query")
        if not allowed_cluster_ids:
            return ok_response(data={
                "by_business": [],
                "by_db_type": []
            })
        query = query.filter(DatabaseCluster.id.in_(allowed_cluster_ids))

    # 按业务(business_line/namespace)统计集群个数
    # 使用子查询方式避免 only_full_group_by 问题
    clusters = query.all()
    business_count = {}
    for cluster in clusters:
        business = cluster.business_line or cluster.namespace or "未分类"
        business_count[business] = business_count.get(business, 0) + 1
    by_business = [
        {"name": name, "value": count}
        for name, count in sorted(business_count.items(), key=lambda x: -x[1])
    ]

    # 按数据库类型(db_type)统计集群个数
    by_db_type_raw = (
        db.session.query(
            DatabaseCluster.db_type,
            func.count(DatabaseCluster.id).label("count")
        )
        .group_by(DatabaseCluster.db_type)
        .order_by(func.count(DatabaseCluster.id).desc())
        .all()
    )
    by_db_type = [{"name": row.db_type, "value": row.count} for row in by_db_type_raw]

    return ok_response(data={
        "by_business": by_business,
        "by_db_type": by_db_type
    })


@bp.post("")
@admin_required
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
@admin_required
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
@admin_required
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
                "collected_at": _beijing_iso(snapshot.collected_at),
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


# ===== MongoDB / Redis 集群连接探测与拓扑历史 =====

def _probe_mongo_instance(instance):
    """同步探测单个 MongoDB 实例，返回结构化结果。"""
    from pymongo import MongoClient

    host = instance.resolved_ip or instance.host_input
    node = {
        "instance_id": instance.id,
        "instance_name": instance.name,
        "host": host,
        "port": instance.port,
        "reachable": False,
        "role": "unknown",
        "state": None,
        "set_name": None,
        "is_arbiter": False,
        "error": None,
        "members": [],
    }

    extra = instance.extra_json if isinstance(instance.extra_json, dict) else {}
    auth_source = (extra.get("auth_source") or extra.get("auth_db") or "").strip() or None
    auth_sources = []
    if auth_source:
        auth_sources.append(auth_source)
    for fallback in ("admin", "local"):
        if fallback not in auth_sources:
            auth_sources.append(fallback)

    try:
        password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
    except Exception as exc:
        node["error"] = f"decrypt password failed: {exc}"
        return node

    client_opts = dict(
        serverSelectionTimeoutMS=2000,
        connectTimeoutMS=2000,
        socketTimeoutMS=2000,
        ssl=False,
        appname="dbms-probe",
    )

    client = None
    last_error = None
    try:
        if instance.username and password:
            for source in auth_sources:
                try:
                    client = MongoClient(
                        host, instance.port,
                        username=instance.username, password=password, authSource=source,
                        **client_opts,
                    )
                    client.admin.command("ping")
                    break
                except Exception as exc:
                    last_error = exc
                    client = None
            if client is None:
                # 回退到无认证探测 (Arbiter 常见情况)
                try:
                    no_auth_client = MongoClient(host, instance.port, **client_opts)
                    no_auth_client.admin.command("ping")
                    hello = {}
                    try:
                        hello = no_auth_client.admin.command("hello")
                    except Exception:
                        try:
                            hello = no_auth_client.admin.command("isMaster")
                        except Exception:
                            hello = {}
                    node["reachable"] = True
                    if hello.get("arbiterOnly") is True:
                        node["role"] = "ARBITER"
                        node["is_arbiter"] = True
                    elif hello.get("isWritablePrimary") is True or hello.get("ismaster") is True:
                        node["role"] = "PRIMARY"
                    elif hello.get("secondary") is True:
                        node["role"] = "SECONDARY"
                    node["set_name"] = hello.get("setName")
                    no_auth_client.close()
                    return node
                except Exception:
                    raise last_error or Exception("mongo auth failed")
        else:
            client = MongoClient(host, instance.port, **client_opts)
            client.admin.command("ping")

        node["reachable"] = True
        target_name = f"{host}:{instance.port}"
        try:
            repl = client.admin.command("replSetGetStatus")
            node["set_name"] = repl.get("set")
            members = repl.get("members") or []
            members_out = []
            for member in members:
                if not isinstance(member, dict):
                    continue
                m_name = str(member.get("name") or "").strip()
                state_str = str(member.get("stateStr") or "").upper()
                members_out.append({
                    "name": m_name,
                    "state": member.get("state"),
                    "state_str": state_str,
                    "health": member.get("health"),
                    "self": bool(member.get("self")),
                })
                if member.get("self") is True or m_name == target_name:
                    node["role"] = state_str or node["role"]
                    node["state"] = member.get("state")
            node["members"] = members_out
        except Exception:
            # 非副本集或权限不足：用 hello 兑含角色
            try:
                hello = client.admin.command("hello")
            except Exception:
                try:
                    hello = client.admin.command("isMaster")
                except Exception:
                    hello = {}
            if hello.get("arbiterOnly") is True:
                node["role"] = "ARBITER"
                node["is_arbiter"] = True
            elif hello.get("isWritablePrimary") is True or hello.get("ismaster") is True:
                node["role"] = "PRIMARY"
            elif hello.get("secondary") is True:
                node["role"] = "SECONDARY"
            node["set_name"] = hello.get("setName") or node["set_name"]
    except Exception as exc:
        node["reachable"] = False
        node["error"] = str(exc)
    finally:
        try:
            if client is not None:
                client.close()
        except Exception:
            pass

    return node


def _probe_redis_instance(instance):
    """同步探测单个 Redis 实例。"""
    import redis

    host = instance.resolved_ip or instance.host_input
    node = {
        "instance_id": instance.id,
        "instance_name": instance.name,
        "host": host,
        "port": instance.port,
        "reachable": False,
        "role": "unknown",
        "master_host": None,
        "master_port": None,
        "master_link_status": None,
        "replication_source": None,
        "connected_slaves": None,
        "cluster_enabled": None,
        "cluster_state": None,
        "error": None,
    }

    try:
        password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
    except Exception as exc:
        node["error"] = f"decrypt password failed: {exc}"
        return node

    try:
        client = redis.Redis(
            host=host,
            port=instance.port,
            password=password,
            socket_connect_timeout=3,
            socket_timeout=3,
            decode_responses=True,
        )
        client.ping()
        node["reachable"] = True
        info = client.info()
        role = str(info.get("role") or "").strip().lower()
        if role == "replica":
            role = "slave"
        node["role"] = role or "unknown"
        node["master_host"] = info.get("master_host")
        node["master_port"] = info.get("master_port")
        node["master_link_status"] = info.get("master_link_status")
        if node["master_host"]:
            node["replication_source"] = (
                f"{node['master_host']}:{node['master_port']}" if node.get("master_port") else str(node["master_host"]) 
            )
        node["connected_slaves"] = info.get("connected_slaves")
        node["cluster_enabled"] = info.get("cluster_enabled")
        try:
            cinfo = client.execute_command("CLUSTER INFO")
            if isinstance(cinfo, dict):
                node["cluster_state"] = cinfo.get("cluster_state")
        except Exception:
            pass
    except Exception as exc:
        node["reachable"] = False
        node["error"] = str(exc)
    return node


def _summarize_mongo_nodes(nodes):
    primary = sum(1 for n in nodes if (n.get("role") or "").upper() == "PRIMARY")
    secondary = sum(1 for n in nodes if (n.get("role") or "").upper() == "SECONDARY")
    arbiter = sum(1 for n in nodes if (n.get("role") or "").upper() == "ARBITER")
    reachable = sum(1 for n in nodes if n.get("reachable"))
    set_name = next((n.get("set_name") for n in nodes if n.get("set_name")), None)
    return {
        "set_name": set_name,
        "primary_count": primary,
        "secondary_count": secondary,
        "arbiter_count": arbiter,
        "reachable_count": reachable,
        "unreachable_count": max(0, len(nodes) - reachable),
        "total": len(nodes),
    }


def _summarize_redis_nodes(nodes):
    master = sum(1 for n in nodes if n.get("role") == "master")
    slave = sum(1 for n in nodes if n.get("role") in {"slave", "replica"})
    reachable = sum(1 for n in nodes if n.get("reachable"))
    cluster_state = next((n.get("cluster_state") for n in nodes if n.get("cluster_state")), None)
    return {
        "master_count": master,
        "slave_count": slave,
        "reachable_count": reachable,
        "unreachable_count": max(0, len(nodes) - reachable),
        "total": len(nodes),
        "cluster_state": cluster_state,
    }


@bp.post("/<int:cluster_id>/connectivity/probe")
@active_user_required
def cluster_connectivity_probe(cluster_id):
    """对 MongoDB / Redis 集群做集群级可连接性探测，不写快照、不影响定时采集。"""
    cluster = DatabaseCluster.query.get_or_404(cluster_id)
    if cluster.db_type not in ("mongodb", "redis"):
        return error_response("connectivity probe only supports mongodb/redis cluster", code=400)
    if not require_cluster_permission(cluster.id, "query"):
        return error_response("permission denied", code=403)

    instances = (
        DatabaseInstance.query
        .filter_by(cluster_id=cluster.id, enabled=True)
        .order_by(DatabaseInstance.id.asc())
        .all()
    )
    if not instances:
        return error_response("cluster has no enabled instances", code=400)

    nodes = []
    if cluster.db_type == "mongodb":
        for ins in instances:
            try:
                nodes.append(_probe_mongo_instance(ins))
            except Exception as exc:
                nodes.append({
                    "instance_id": ins.id,
                    "instance_name": ins.name,
                    "host": ins.resolved_ip or ins.host_input,
                    "port": ins.port,
                    "reachable": False,
                    "role": "unknown",
                    "error": str(exc),
                })
        summary = _summarize_mongo_nodes(nodes)
    else:
        for ins in instances:
            try:
                nodes.append(_probe_redis_instance(ins))
            except Exception as exc:
                nodes.append({
                    "instance_id": ins.id,
                    "instance_name": ins.name,
                    "host": ins.resolved_ip or ins.host_input,
                    "port": ins.port,
                    "reachable": False,
                    "role": "unknown",
                    "error": str(exc),
                })
        summary = _summarize_redis_nodes(nodes)

    return ok_response(data={
        "cluster_id": cluster.id,
        "cluster_name": cluster.name,
        "db_type": cluster.db_type,
        "probed_at": _beijing_now_iso(),
        "summary": summary,
        "nodes": nodes,
    })


@bp.get("/<int:cluster_id>/connectivity/latest")
@active_user_required
def cluster_connectivity_latest(cluster_id):
    """从最新快照提炼集群连接性概览，不重新连接远端。"""
    cluster = DatabaseCluster.query.get_or_404(cluster_id)
    if cluster.db_type not in ("mongodb", "redis"):
        return error_response("connectivity latest only supports mongodb/redis cluster", code=400)
    if not require_cluster_permission(cluster.id, "query"):
        return error_response("permission denied", code=403)

    instances = (
        DatabaseInstance.query
        .filter_by(cluster_id=cluster.id, enabled=True)
        .order_by(DatabaseInstance.id.asc())
        .all()
    )

    nodes = []
    latest_collected_at = None
    for ins in instances:
        snapshot = latest_snapshot_for_instance(instance_id=ins.id, db_type=ins.db_type, metric_type="status")
        payload = snapshot.payload_json if snapshot and isinstance(snapshot.payload_json, dict) else {}
        collected_at = _beijing_iso(snapshot.collected_at) if snapshot else None
        if collected_at and (latest_collected_at is None or collected_at > latest_collected_at):
            latest_collected_at = collected_at
        if cluster.db_type == "mongodb":
            role = str(payload.get("mongo_role") or "unknown").upper()
            repl = payload.get("repl") if isinstance(payload.get("repl"), dict) else {}
            nodes.append({
                "instance_id": ins.id,
                "instance_name": ins.name,
                "host": ins.resolved_ip or ins.host_input,
                "port": ins.port,
                "reachable": bool(payload.get("ping_ok") is True),
                "role": role,
                "set_name": repl.get("set"),
                "collected_at": collected_at,
                "error": payload.get("error"),
            })
        else:
            role = str(payload.get("role") or "unknown").lower()
            cinfo = payload.get("cluster_info") if isinstance(payload.get("cluster_info"), dict) else {}
            nodes.append({
                "instance_id": ins.id,
                "instance_name": ins.name,
                "host": ins.resolved_ip or ins.host_input,
                "port": ins.port,
                "reachable": bool(payload.get("ping_ok") is True),
                "role": role,
                "master_host": payload.get("master_host"),
                "master_port": payload.get("master_port"),
                "replication_source": payload.get("replication_source"),
                "master_link_status": payload.get("master_link_status"),
                "cluster_state": cinfo.get("cluster_state"),
                "collected_at": collected_at,
                "error": payload.get("error"),
            })

    summary = _summarize_mongo_nodes(nodes) if cluster.db_type == "mongodb" else _summarize_redis_nodes(nodes)
    return ok_response(data={
        "cluster_id": cluster.id,
        "cluster_name": cluster.name,
        "db_type": cluster.db_type,
        "collected_at": latest_collected_at,
        "summary": summary,
        "nodes": nodes,
    })


@bp.get("/<int:cluster_id>/topology/history")
@active_user_required
def cluster_topology_history(cluster_id):
    """分页查询集群拓扑变更历史。"""
    cluster = DatabaseCluster.query.get_or_404(cluster_id)
    if cluster.db_type not in ("mongodb", "redis", "mysql"):
        return error_response("topology history only supports mongodb/redis/mysql cluster", code=400)
    if not require_cluster_permission(cluster.id, "query"):
        return error_response("permission denied", code=403)

    page, page_size = _parse_page_args()
    try:
        data = list_topology_history(
            cluster_id=cluster.id,
            page=page,
            page_size=page_size,
        )
    except Exception as exc:
        current_app.logger.exception("list_topology_history failed: %s", exc)
        return error_response(f"load topology history failed: {exc}", code=500)
    data["cluster_id"] = cluster.id
    data["cluster_name"] = cluster.name
    data["db_type"] = cluster.db_type
    return ok_response(data=data)
