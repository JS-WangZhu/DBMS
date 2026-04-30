from datetime import datetime, timedelta
from uuid import uuid4

from flask import Blueprint, request
from sqlalchemy import Text, cast

from app.api.routes.common import (
    active_user_required,
    api_key_required,
    get_current_user,
    list_allowed_cluster_ids,
    require_cluster_permission,
    require_menu_permission,
)
from app.models.audit_log import AuditLog
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.models.user import User
from app.services.audit import log_audit
from app.services.data_access import (
    cancel_execution,
    execute_mongo,
    execute_mongo_query_raw,
    execute_mongo_raw,
    execute_mysql,
    execute_redis,
    finish_execution,
    list_mysql_databases,
    list_mongo_databases,
    normalize_payload,
    pick_instance,
    register_execution,
    set_execution_cancel_callback,
    validate_mongo_change,
    validate_mongo_query,
    validate_mysql_change,
    validate_mysql_query,
    validate_redis_change,
    validate_redis_query,
)
from app.utils.response import error_response, ok_response

bp = Blueprint("data_access", __name__, url_prefix="/data-access")


def _to_cn_time(dt):
    if not dt:
        return None
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _parse_page_args():
    page = max(_safe_int(request.args.get("page"), 1), 1)
    page_size = _safe_int(request.args.get("page_size"), 20)
    page_size = min(max(page_size, 1), 200)
    return page, page_size


def _parse_history_filter_args():
    keyword = (request.args.get("keyword") or "").strip()
    start_date = (request.args.get("start_date") or "").strip()
    end_date = (request.args.get("end_date") or "").strip()
    start_dt = None
    end_exclusive_dt = None
    def _parse_dt(text):
        if not text:
            return None, False
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                value = datetime.strptime(text, fmt)
                return value, fmt == "%Y-%m-%d"
            except ValueError:
                continue
        return None, False

    if start_date:
        parsed_start, _ = _parse_dt(start_date)
        if parsed_start:
            start_dt = parsed_start
    if end_date:
        parsed_end, is_date_only = _parse_dt(end_date)
        if parsed_end:
            if is_date_only:
                end_exclusive_dt = parsed_end + timedelta(days=1)
            else:
                end_exclusive_dt = parsed_end + timedelta(seconds=1)
    return keyword, start_dt, end_exclusive_dt


def _build_history_item(row: AuditLog, user_name_map, instance_name_map, cluster_name_map):
    detail = row.detail_json or {}
    instance_id = detail.get("instance_id")
    cluster_id = detail.get("cluster_id")
    return {
        "id": row.id,
        "action": row.action,
        "user_id": row.user_id,
        "username": user_name_map.get(row.user_id) or detail.get("operator_username") or "未知用户",
        "db_type": detail.get("db_type"),
        "business_line": detail.get("business_line"),
        "environment": detail.get("environment"),
        "cluster_id": cluster_id,
        "cluster_name": cluster_name_map.get(cluster_id),
        "instance_id": instance_id,
        "instance_name": instance_name_map.get(instance_id) or "未知实例",
        "timeout_seconds": detail.get("timeout_seconds"),
        "success": detail.get("success"),
        "error": detail.get("error"),
        "statement": detail.get("statement"),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "created_at_cn": _to_cn_time(row.created_at),
    }


def _paginate_history(action_values):
    page, page_size = _parse_page_args()
    keyword, start_dt, end_exclusive_dt = _parse_history_filter_args()
    current_user = get_current_user()
    query = AuditLog.query.filter(AuditLog.action.in_(action_values))
    if current_user and current_user.role != "admin":
        query = query.filter_by(user_id=current_user.id)
    if keyword:
        query = query.filter(cast(AuditLog.detail_json, Text).ilike(f"%{keyword}%"))
    if start_dt:
        query = query.filter(AuditLog.created_at >= start_dt)
    if end_exclusive_dt:
        query = query.filter(AuditLog.created_at < end_exclusive_dt)
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
    instance_ids = sorted(
        {
            (row.detail_json or {}).get("instance_id")
            for row in rows
            if (row.detail_json or {}).get("instance_id")
        }
    )
    instances = DatabaseInstance.query.filter(DatabaseInstance.id.in_(instance_ids)).all() if instance_ids else []
    instance_name_map = {item.id: item.name for item in instances}
    cluster_ids = sorted(
        {
            (row.detail_json or {}).get("cluster_id")
            for row in rows
            if (row.detail_json or {}).get("cluster_id")
        }
    )
    clusters = DatabaseCluster.query.filter(DatabaseCluster.id.in_(cluster_ids)).all() if cluster_ids else []
    cluster_name_map = {item.id: item.name for item in clusters}
    return {
        "items": [_build_history_item(row, user_name_map, instance_name_map, cluster_name_map) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "keyword": keyword,
        "start_date": request.args.get("start_date"),
        "end_date": request.args.get("end_date"),
    }


def _safe_int(value, default_value: int):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default_value


def _build_audit_detail(payload, db_type, cluster_id, instance_id, timeout_seconds, success, error_message=None, current_user=None):
    statement = ""
    if db_type == "mysql":
        statement = str(payload.get("statement") or payload.get("sql") or "")
    elif db_type == "mongodb":
        statement = str(payload.get("statement") or payload.get("mongo_command") or payload.get("query") or "")
    else:
        statement = str(payload.get("statement") or payload.get("query") or "")
    statement = statement[:1000]
    return {
        "db_type": db_type,
        "business_line": payload.get("business_line"),
        "environment": payload.get("environment"),
        "cluster_id": cluster_id,
        "instance_id": instance_id,
        "timeout_seconds": timeout_seconds,
        "success": success,
        "error": error_message,
        "statement": statement,
        "operator_username": current_user.username if current_user else None,
    }


def _resolve_cluster_instance(payload):
    cluster_id = payload.get("cluster_id")
    instance_id = payload.get("instance_id")
    if instance_id:
        instance = DatabaseInstance.query.get(instance_id)
        if not instance:
            return None, None, "instance not found"
        cluster_id = instance.cluster_id
    else:
        instance = None
    if not cluster_id:
        return None, None, "cluster_id or instance_id is required"
    cluster = DatabaseCluster.query.get(cluster_id)
    if not cluster:
        return None, None, "cluster not found"
    if instance and instance.cluster_id != cluster.id:
        return None, None, "instance does not belong to cluster"
    return cluster, instance, None


def _validate_scope(payload, cluster: DatabaseCluster):
    line = (payload.get("business_line") or payload.get("product") or "").strip()
    env = (payload.get("environment") or "").strip()
    if line and (cluster.business_line or cluster.namespace) != line:
        return "business_line mismatch"
    if env and (cluster.environment or "") != env:
        return "environment mismatch"
    return None


def _tokenize_command_line(raw: str):
    import re
    source = str(raw or "").strip()
    if not source:
        return []
    parts = re.findall(r'"[^"\\]*(?:\\.[^"\\]*)*"|\'[^\'\\]*(?:\\.[^\'\\]*)*\'|\S+', source)
    normalized = []
    for part in parts:
        if (part.startswith('"') and part.endswith('"')) or (part.startswith("'") and part.endswith("'")):
            normalized.append(part[1:-1].replace('\\"', '"').replace("\\'", "'"))
        else:
            normalized.append(part)
    return normalized


def _normalize_change_payload(payload):
    normalized = dict(payload or {})
    db_type = str(normalized.get("db_type") or "").strip().lower()
    if (not normalized.get("business_line")) and normalized.get("product"):
        normalized["business_line"] = normalized.get("product")
    statement = str(normalized.get("statement") or "").strip()
    database = str(normalized.get("database") or "").strip()
    if db_type == "mysql":
        if statement and not str(normalized.get("sql") or "").strip():
            normalized["sql"] = statement
    elif db_type == "mongodb":
        if database and not str(normalized.get("mongo_database") or "").strip():
            normalized["mongo_database"] = database
        if statement and not str(normalized.get("mongo_command") or "").strip():
            normalized["mongo_command"] = statement
    elif db_type == "redis":
        if statement and not normalized.get("query"):
            tokens = _tokenize_command_line(statement)
            if tokens:
                normalized["query"] = {"command": tokens[0].upper(), "args": tokens[1:]}
    return normalized


def _cluster_seed_nodes(db_type: str, cluster_id: int):
    if not cluster_id:
        return []
    instances = (
        DatabaseInstance.query.filter_by(cluster_id=cluster_id, db_type=db_type, enabled=True)
        .order_by(DatabaseInstance.id.asc())
        .all()
    )
    nodes = []
    for item in instances:
        host = item.resolved_ip or item.host_input
        if not host:
            continue
        nodes.append(f"{host}:{item.port}")
    return sorted(set(nodes))


def _resolve_database_name(payload, db_type: str):
    if db_type == "mysql":
        return (payload.get("database") or "").strip() or None
    if db_type == "mongodb":
        return (payload.get("mongo_database") or payload.get("database") or "").strip() or "admin"
    return (payload.get("database") or "").strip() or None


def _execute(db_type: str, instance, payload, timeout_seconds, for_change: bool, execution_id=None):
    if db_type == "mysql":
        sql = payload.get("sql") or ""
        database = (payload.get("database") or "").strip() or None
        if for_change:
            ok, err = validate_mysql_change(sql)
        else:
            ok, err = validate_mysql_query(sql)
        if not ok:
            return False, err, None
        return True, None, execute_mysql(instance, sql, timeout_seconds, for_change, database=database, execution_id=execution_id)
    if db_type == "mongodb":
        seed_nodes = _cluster_seed_nodes("mongodb", instance.cluster_id)
        mongo_command = payload.get("mongo_command")
        mongo_database = (payload.get("mongo_database") or "").strip() or "admin"
        if mongo_command:
            if for_change:
                return True, None, execute_mongo_raw(instance, mongo_command, mongo_database, timeout_seconds, seed_nodes=seed_nodes)
            else:
                return True, None, execute_mongo_query_raw(instance, mongo_command, mongo_database, timeout_seconds, seed_nodes=seed_nodes)
        raw = normalize_payload(payload.get("query"))
        if for_change:
            ok, err = validate_mongo_change(raw)
        else:
            ok, err = validate_mongo_query(raw)
        if not ok:
            return False, err, None
        return True, None, execute_mongo(instance, raw, timeout_seconds, for_change, seed_nodes=seed_nodes)
    if db_type == "redis":
        seed_nodes = _cluster_seed_nodes("redis", instance.cluster_id)
        raw = normalize_payload(payload.get("query"))
        if for_change:
            ok, err = validate_redis_change(raw)
        else:
            ok, err = validate_redis_query(raw)
        if not ok:
            return False, err, None
        return True, None, execute_redis(instance, raw, timeout_seconds, seed_nodes=seed_nodes)
    return False, "unsupported db_type", None


@bp.get("/mongodb/databases")
@require_menu_permission("data_query")
def list_databases_for_mongodb():
    cluster_id = _safe_int(request.args.get("cluster_id"), 0)
    if cluster_id <= 0:
        return error_response("cluster_id is required", code=400)
    cluster = DatabaseCluster.query.get(cluster_id)
    if not cluster:
        return error_response("cluster not found", code=400)
    if not require_cluster_permission(cluster.id, "query"):
        return error_response("permission denied", code=403)
    chosen = pick_instance("mongodb", cluster.id, None, for_change=False)
    if not chosen:
        return error_response("no available instance", code=400)
    try:
        names = list_mongo_databases(chosen)
    except Exception as exc:
        return error_response(str(exc), code=400)
    return ok_response(data={"cluster_id": cluster.id, "instance_id": chosen.id, "databases": names})


@bp.get("/mysql/databases")
@require_menu_permission("data_query")
def list_databases_for_mysql():
    cluster_id = _safe_int(request.args.get("cluster_id"), 0)
    if cluster_id <= 0:
        return error_response("cluster_id is required", code=400)
    cluster = DatabaseCluster.query.get(cluster_id)
    if not cluster:
        return error_response("cluster not found", code=400)
    if not require_cluster_permission(cluster.id, "query"):
        return error_response("permission denied", code=403)
    chosen = pick_instance("mysql", cluster.id, None, for_change=False)
    if not chosen:
        return error_response("no available instance", code=400)
    try:
        names = list_mysql_databases(chosen)
    except Exception as exc:
        return error_response(str(exc), code=400)
    return ok_response(data={"cluster_id": cluster.id, "instance_id": chosen.id, "databases": names})


@bp.post("/query")
@require_menu_permission("data_query")
def query_data():
    payload = request.get_json(silent=True) or {}
    db_type = payload.get("db_type")
    if db_type not in {"mysql", "mongodb", "redis"}:
        return error_response("db_type invalid", code=400)
    cluster, instance, err = _resolve_cluster_instance(payload)
    if err:
        return error_response(err, code=400)
    scope_err = _validate_scope(payload, cluster)
    if scope_err:
        return error_response(scope_err, code=400)
    if not require_cluster_permission(cluster.id, "query"):
        return error_response("permission denied", code=403)

    timeout_seconds = _safe_int(payload.get("timeout_seconds"), 600)
    timeout_seconds = max(1, min(timeout_seconds, 600))
    chosen = pick_instance(db_type, cluster.id, None, for_change=False)
    if not chosen:
        chosen = instance
    if not chosen:
        return error_response("no available instance", code=400)

    current_user = get_current_user()
    execution_id = str(payload.get("execution_id") or "").strip() or uuid4().hex
    register_execution(execution_id, current_user.id if current_user else None, db_type)
    if db_type != "mysql":
        set_execution_cancel_callback(execution_id, None)
    try:
        ok, err, result = _execute(db_type, chosen, payload, timeout_seconds, for_change=False, execution_id=execution_id)
    finally:
        finish_execution(execution_id)
    if not ok:
        log_audit(
            user_id=current_user.id if current_user else None,
            action="data_access.query",
            target_type="cluster",
            target_id=str(cluster.id),
            detail=_build_audit_detail(payload, db_type, cluster.id, chosen.id, timeout_seconds, success=False, error_message=err, current_user=current_user),
        )
        return error_response(err, code=400)
    log_audit(
        user_id=current_user.id if current_user else None,
        action="data_access.query",
        target_type="cluster",
        target_id=str(cluster.id),
        detail=_build_audit_detail(payload, db_type, cluster.id, chosen.id, timeout_seconds, success=True, current_user=current_user),
    )
    return ok_response(
        data={
            "cluster_id": cluster.id,
            "instance_id": chosen.id,
            "result": result,
            "timeout_seconds": timeout_seconds,
            "execution_id": execution_id,
            "connection_info": {
                "cluster": cluster.to_dict(),
                "instance": chosen.to_dict(),
                "database": _resolve_database_name(payload, db_type),
            },
        }
    )


@bp.post("/change")
@require_menu_permission("data_change")
def change_data():
    payload = _normalize_change_payload(request.get_json(silent=True) or {})
    db_type = payload.get("db_type")
    if db_type not in {"mysql", "mongodb", "redis"}:
        return error_response("db_type invalid", code=400)
    cluster, instance, err = _resolve_cluster_instance(payload)
    if err:
        return error_response(err, code=400)
    scope_err = _validate_scope(payload, cluster)
    if scope_err:
        return error_response(scope_err, code=400)
    if not require_cluster_permission(cluster.id, "change"):
        return error_response("permission denied", code=403)

    timeout_seconds = _safe_int(payload.get("timeout_seconds"), 86400)
    if timeout_seconds < 0:
        timeout_seconds = 0
    chosen = pick_instance(db_type, cluster.id, None, for_change=True)
    if not chosen:
        chosen = instance
    if not chosen:
        return error_response("no available instance", code=400)

    current_user = get_current_user()
    execution_id = str(payload.get("execution_id") or "").strip() or uuid4().hex
    register_execution(execution_id, current_user.id if current_user else None, db_type)
    if db_type != "mysql":
        set_execution_cancel_callback(execution_id, None)
    try:
        try:
            ok, err, result = _execute(db_type, chosen, payload, timeout_seconds, for_change=True, execution_id=execution_id)
        except Exception as exc:
            err = str(exc) or "change execute failed"
            log_audit(
                user_id=current_user.id if current_user else None,
                action="data_access.change",
                target_type="cluster",
                target_id=str(cluster.id),
                detail=_build_audit_detail(payload, db_type, cluster.id, chosen.id, timeout_seconds, success=False, error_message=err, current_user=current_user),
            )
            return error_response(err, code=500)
    finally:
        finish_execution(execution_id)
    if not ok:
        log_audit(
            user_id=current_user.id if current_user else None,
            action="data_access.change",
            target_type="cluster",
            target_id=str(cluster.id),
            detail=_build_audit_detail(payload, db_type, cluster.id, chosen.id, timeout_seconds, success=False, error_message=err, current_user=current_user),
        )
        return error_response(err, code=400)
    log_audit(
        user_id=current_user.id if current_user else None,
        action="data_access.change",
        target_type="cluster",
        target_id=str(cluster.id),
        detail=_build_audit_detail(payload, db_type, cluster.id, chosen.id, timeout_seconds, success=True, current_user=current_user),
    )
    return ok_response(
        data={
            "cluster_id": cluster.id,
            "instance_id": chosen.id,
            "result": result,
            "timeout_seconds": timeout_seconds,
            "execution_id": execution_id,
        }
    )


@bp.get("/history/query")
@require_menu_permission("data_history")
def query_history():
    return ok_response(data=_paginate_history({"data_access.query"}))


@bp.get("/history/change")
@require_menu_permission("data_history")
def change_history():
    return ok_response(data=_paginate_history({"data_access.change", "data_access.change.api"}))


@bp.post("/cancel")
@active_user_required
def cancel_running_execution():
    payload = request.get_json(silent=True) or {}
    execution_id = str(payload.get("execution_id") or "").strip()
    if not execution_id:
        return error_response("execution_id is required", code=400)
    user = get_current_user()
    ok, err = cancel_execution(execution_id, user.id if user else None, bool(user and user.role == "admin"))
    if not ok:
        return error_response(err, code=400)
    return ok_response(data={"execution_id": execution_id, "cancel_requested": True})
