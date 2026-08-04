from datetime import datetime

from flask import Blueprint, current_app, request
from sqlalchemy import or_

from app.api.routes.common import (
    get_current_user,
    list_allowed_cluster_ids,
    require_cluster_permission,
    require_menu_permission,
)
from app.extensions import db
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.models.sql_release import SqlRelease
from app.services.audit import log_audit
from app.services.data_access import (
    describe_mongo_collection,
    list_mongo_collections,
    list_mongo_databases,
    list_mysql_databases,
    list_mysql_objects,
    list_mysql_table_columns,
    pick_instance,
    validate_mysql_change,
)
from app.services.sql_release_service import (
    execute_mongodb_with_partial_rollback,
    execute_mysql_with_partial_rollback,
    execute_postgresql_with_partial_rollback,
    review_release,
    split_sql_statements,
    validate_mongo_release_statement,
)
from app.services.sql_release_review import dispatch_sql_release_review
from app.services.postgresql_backup import list_databases as list_postgresql_databases
from app.services.postgresql_backup import list_objects as list_postgresql_objects
from app.services.postgresql_backup import list_table_columns as list_postgresql_table_columns
from app.utils.crypto import decrypt_secret
from app.utils.response import error_response, ok_response

bp = Blueprint("sql_releases", __name__, url_prefix="/sql-releases")
SUPPORTED_RELEASE_TYPES = {"mysql", "mongodb", "postgresql"}


def _cluster_seed_nodes(db_type, cluster_id):
    rows = DatabaseInstance.query.filter_by(cluster_id=cluster_id, db_type=db_type, enabled=True).all()
    return sorted({f"{item.resolved_ip or item.host_input}:{item.port}" for item in rows if item.resolved_ip or item.host_input})


def _serialize_release(row, user=None, executable_cluster_ids=None):
    data = row.to_dict()
    if user:
        data["can_execute"] = user.role == "admin" or (
            row.cluster_id in executable_cluster_ids
            if executable_cluster_ids is not None
            else require_cluster_permission(row.cluster_id, "execute")
        )
    if user and user.role != "admin":
        data.pop("rollback_backup_path", None)
    return data


@bp.get("/databases")
@require_menu_permission("sql_release_apply")
def list_release_databases():
    try:
        cluster_id = int(request.args.get("cluster_id"))
    except (TypeError, ValueError):
        return error_response("cluster_id is required", code=400)
    cluster = DatabaseCluster.query.get(cluster_id)
    db_type = str(request.args.get("db_type") or (cluster.db_type if cluster else "mysql")).strip().lower()
    if not cluster or db_type not in SUPPORTED_RELEASE_TYPES or cluster.db_type != db_type:
        return error_response("database type does not match cluster", code=400)
    if not require_cluster_permission(cluster.id, "change"):
        return error_response("permission denied", code=403)
    instance = pick_instance(db_type, cluster.id, None, for_change=True)
    if not instance:
        return error_response("no available writable instance", code=400)
    try:
        if db_type == "mysql":
            databases = list_mysql_databases(instance)
        elif db_type == "mongodb":
            databases = list_mongo_databases(instance, seed_nodes=_cluster_seed_nodes(db_type, cluster.id))
        else:
            password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
            databases = list_postgresql_databases(instance, password)
    except Exception as exc:
        return error_response(str(exc), code=400)
    return ok_response(data={"db_type": db_type, "databases": databases, "instance_id": instance.id})


@bp.get("/objects")
@require_menu_permission("sql_release_apply")
def list_release_objects():
    try:
        cluster_id = int(request.args.get("cluster_id"))
    except (TypeError, ValueError):
        return error_response("cluster_id is required", code=400)
    database = str(request.args.get("database") or "").strip()
    db_type = str(request.args.get("db_type") or "").strip().lower()
    cluster = DatabaseCluster.query.get(cluster_id)
    if not database or not cluster or db_type not in SUPPORTED_RELEASE_TYPES or cluster.db_type != db_type:
        return error_response("invalid database source", code=400)
    if not require_cluster_permission(cluster.id, "change"):
        return error_response("permission denied", code=403)
    instance = pick_instance(db_type, cluster.id, None, for_change=True)
    if not instance:
        return error_response("no available writable instance", code=400)
    try:
        if db_type == "mysql":
            objects = list_mysql_objects(instance, database)
        elif db_type == "mongodb":
            objects = list_mongo_collections(instance, database, seed_nodes=_cluster_seed_nodes(db_type, cluster.id))
        else:
            password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
            objects = list_postgresql_objects(instance, password, database)
    except Exception as exc:
        return error_response(str(exc), code=400)
    return ok_response(data=objects)


@bp.get("/columns")
@require_menu_permission("sql_release_apply")
def list_release_columns():
    try:
        cluster_id = int(request.args.get("cluster_id"))
    except (TypeError, ValueError):
        return error_response("cluster_id is required", code=400)
    database = str(request.args.get("database") or "").strip()
    table = str(request.args.get("table") or request.args.get("collection") or "").strip()
    db_type = str(request.args.get("db_type") or "").strip().lower()
    cluster = DatabaseCluster.query.get(cluster_id)
    if not database or not table or not cluster or db_type not in SUPPORTED_RELEASE_TYPES or cluster.db_type != db_type:
        return error_response("invalid database object", code=400)
    if not require_cluster_permission(cluster.id, "change"):
        return error_response("permission denied", code=403)
    instance = pick_instance(db_type, cluster.id, None, for_change=True)
    if not instance:
        return error_response("no available writable instance", code=400)
    try:
        if db_type == "mysql":
            columns = list_mysql_table_columns(instance, database, table)
            data = {"columns": columns}
        elif db_type == "mongodb":
            detail = describe_mongo_collection(instance, database, table, seed_nodes=_cluster_seed_nodes(db_type, cluster.id))
            data = {"columns": detail.get("sample_fields") or [], "indexes": detail.get("indexes") or []}
        else:
            password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
            data = {"columns": list_postgresql_table_columns(instance, password, database, table)}
    except Exception as exc:
        return error_response(str(exc), code=400)
    return ok_response(data={"database": database, "table": table, **data})


@bp.get("/mysql/objects")
@require_menu_permission("sql_release_apply")
def list_release_mysql_objects():
    try:
        cluster_id = int(request.args.get("cluster_id"))
    except (TypeError, ValueError):
        return error_response("cluster_id is required", code=400)
    database = str(request.args.get("database") or "").strip()
    if not database:
        return error_response("database is required", code=400)
    cluster = DatabaseCluster.query.get(cluster_id)
    if not cluster or cluster.db_type != "mysql":
        return error_response("only MySQL cluster is supported", code=400)
    if not require_cluster_permission(cluster.id, "change"):
        return error_response("permission denied", code=403)
    instance = pick_instance("mysql", cluster.id, None, for_change=True)
    if not instance:
        return error_response("no available writable instance", code=400)
    try:
        objects = list_mysql_objects(instance, database)
    except Exception as exc:
        return error_response(str(exc), code=400)
    return ok_response(data=objects)


@bp.get("/mysql/columns")
@require_menu_permission("sql_release_apply")
def list_release_mysql_columns():
    try:
        cluster_id = int(request.args.get("cluster_id"))
    except (TypeError, ValueError):
        return error_response("cluster_id is required", code=400)
    database = str(request.args.get("database") or "").strip()
    table = str(request.args.get("table") or "").strip()
    if not database or not table:
        return error_response("database and table are required", code=400)
    cluster = DatabaseCluster.query.get(cluster_id)
    if not cluster or cluster.db_type != "mysql":
        return error_response("only MySQL cluster is supported", code=400)
    if not require_cluster_permission(cluster.id, "change"):
        return error_response("permission denied", code=403)
    instance = pick_instance("mysql", cluster.id, None, for_change=True)
    if not instance:
        return error_response("no available writable instance", code=400)
    try:
        columns = list_mysql_table_columns(instance, database, table)
    except Exception as exc:
        return error_response(str(exc), code=400)
    return ok_response(data={"database": database, "table": table, "columns": columns})


def _resolve_payload(payload):
    try:
        cluster_id = int(payload.get("cluster_id"))
    except (TypeError, ValueError):
        return None, None, None, None, "cluster_id is required"
    cluster = DatabaseCluster.query.get(cluster_id)
    if not cluster or cluster.db_type not in SUPPORTED_RELEASE_TYPES:
        return None, None, None, None, "unsupported database type"
    requested_project = str(payload.get("project") or payload.get("business_line") or "").strip()
    if requested_project and requested_project != (cluster.business_line or cluster.namespace or ""):
        return None, None, None, None, "project does not match cluster"
    requested_db_type = str(payload.get("db_type") or cluster.db_type).strip().lower()
    if requested_db_type != cluster.db_type:
        return None, None, None, None, "database type does not match cluster"
    requested_environment = str(payload.get("environment") or "").strip()
    if requested_environment and requested_environment != (cluster.environment or ""):
        return None, None, None, None, "environment does not match cluster"
    if not require_cluster_permission(cluster.id, "change"):
        return None, None, None, None, "permission denied"
    database = str(payload.get("database") or "").strip()
    sql_text = str(payload.get("sql") or payload.get("statement") or "").strip()
    if not database or not sql_text:
        return None, None, None, None, "database and sql are required"
    instance_id = payload.get("instance_id")
    instance = pick_instance(requested_db_type, cluster.id, instance_id, for_change=True)
    if not instance:
        return None, None, None, None, "no available writable instance"
    statements = split_sql_statements(sql_text)
    if not statements:
        return None, None, None, None, "sql is empty"
    for index, statement in enumerate(statements, start=1):
        if requested_db_type == "mysql":
            valid, reason = validate_mysql_change(statement)
        elif requested_db_type == "mongodb":
            valid, reason = validate_mongo_release_statement(statement)
        else:
            valid, reason = (bool(statement.strip()), "statement is required")
        if not valid:
            return None, None, None, None, f"第 {index} 条语句校验失败：{reason}"
    return cluster, instance, database, statements, None


def _review(payload):
    cluster, instance, database, statements, error = _resolve_payload(payload)
    if error:
        return None, error
    try:
        reviews, summary = review_release(instance, database, statements, cluster.db_type)
    except Exception as exc:
        return None, f"AI 初审失败：{exc}"
    return {
        "cluster": cluster,
        "instance": instance,
        "database": database,
        "db_type": cluster.db_type,
        "statements": statements,
        "reviews": reviews,
        "summary": summary,
        "passed": all(item["passed"] for item in reviews),
    }, None


@bp.post("/review")
@require_menu_permission("sql_release_apply")
def review_sql_release():
    result, error = _review(request.get_json(silent=True) or {})
    if error:
        code = 403 if error == "permission denied" else 400
        return error_response(error, code=code)
    return ok_response(data={key: value for key, value in result.items() if key not in {"cluster", "instance"}})


@bp.post("")
@require_menu_permission("sql_release_apply")
def submit_sql_release():
    payload = request.get_json(silent=True) or {}
    cluster, instance, database, statements, error = _resolve_payload(payload)
    if error:
        code = 403 if error == "permission denied" else 400
        return error_response(error, code=code)
    user = get_current_user()
    release = SqlRelease(
        title=str(payload.get("title") or "").strip() or f"{database} SQL 上线",
        applicant_id=user.id,
        cluster_id=cluster.id,
        instance_id=instance.id,
        db_type=cluster.db_type,
        database_name=database,
        sql_text=";\n".join(statements) + ";",
        status="reviewing",
        ai_passed=False,
        force_submitted=False,
        ai_summary="AI 初审进行中",
        review_json=[],
    )
    db.session.add(release)
    db.session.commit()
    log_audit(
        user_id=user.id,
        action="sql_release.submit",
        target_type="sql_release",
        target_id=str(release.id),
        detail={"status": release.status},
    )
    dispatch_sql_release_review(current_app._get_current_object(), release.id)
    return ok_response(data=_serialize_release(release, user, set()), message="工单已提交，AI 初审正在异步进行", code=201)


@bp.get("")
@require_menu_permission("sql_release_history")
def list_sql_releases():
    user = get_current_user()
    query = SqlRelease.query
    executable_cluster_ids = None
    if user.role != "admin":
        executable_cluster_ids = set(list_allowed_cluster_ids("execute"))
        scope_filters = [SqlRelease.applicant_id == user.id]
        if executable_cluster_ids:
            scope_filters.append(SqlRelease.cluster_id.in_(executable_cluster_ids))
        query = query.filter(or_(*scope_filters))
    status = str(request.args.get("status") or "").strip()
    if status:
        query = query.filter_by(status=status)
    try:
        page = max(int(request.args.get("page", 1)), 1)
        page_size = min(max(int(request.args.get("page_size", 10)), 1), 100)
    except ValueError:
        page, page_size = 1, 10
    total = query.count()
    rows = query.order_by(SqlRelease.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return ok_response(data={
        "items": [_serialize_release(row, user, executable_cluster_ids) for row in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@bp.get("/<int:release_id>")
@require_menu_permission("sql_release_history")
def get_sql_release(release_id):
    row = SqlRelease.query.get_or_404(release_id)
    user = get_current_user()
    executable_cluster_ids = None if user.role == "admin" else set(list_allowed_cluster_ids("execute"))
    if user.role != "admin" and row.applicant_id != user.id and row.cluster_id not in executable_cluster_ids:
        return error_response("permission denied", code=403)
    return ok_response(data=_serialize_release(row, user, executable_cluster_ids))


@bp.post("/<int:release_id>/execute")
@require_menu_permission("sql_release_history")
def execute_sql_release(release_id):
    release = SqlRelease.query.get_or_404(release_id)
    user = get_current_user()
    if user.role != "admin" and not require_cluster_permission(release.cluster_id, "execute"):
        return error_response("permission denied", code=403)
    confirm_risk = (request.get_json(silent=True) or {}).get("confirm_risk") is True
    if release.status == "review_rejected":
        if not confirm_risk:
            return error_response("AI 初审未通过，执行前必须明确确认风险", code=409)
        release.force_submitted = True
    elif release.status != "pending":
        return error_response("AI 初审完成并通过后才能执行", code=409)
    instance = DatabaseInstance.query.get(release.instance_id)
    if not instance or not instance.enabled:
        return error_response("release instance is unavailable", code=400)
    db_type = release.db_type or instance.db_type or "mysql"
    if instance.db_type != db_type:
        return error_response("release instance database type mismatch", code=400)
    statements = split_sql_statements(release.sql_text)
    release.status = "executing"
    db.session.commit()
    backup_path = None
    try:
        if db_type == "mysql":
            result, backup_path = execute_mysql_with_partial_rollback(instance, release.database_name, statements, release.id)
        elif db_type == "mongodb":
            result, backup_path = execute_mongodb_with_partial_rollback(
                instance, release.database_name, statements, release.id,
                seed_nodes=_cluster_seed_nodes(db_type, release.cluster_id),
            )
        elif db_type == "postgresql":
            result, backup_path = execute_postgresql_with_partial_rollback(instance, release.database_name, statements, release.id)
        else:
            raise ValueError("unsupported database type")
        release.rollback_backup_path = backup_path
        release.status = "success"
        release.execution_result_json = result
    except Exception as exc:
        generated_rollback_path = getattr(exc, "rollback_path", None)
        if generated_rollback_path:
            backup_path = generated_rollback_path
            release.rollback_backup_path = generated_rollback_path
        release.status = "failed"
        release.execution_result_json = {"error": str(exc)}
    release.executed_by = user.id
    release.executed_at = datetime.utcnow()
    db.session.commit()
    log_audit(user_id=user.id, action="sql_release.execute", target_type="sql_release", target_id=str(release.id), detail={"status": release.status, "rollback_backup_path": backup_path})
    if release.status == "failed":
        message = "执行失败，可使用已生成的回滚文件恢复" if backup_path else "回滚文件生成失败，已中止执行"
        return error_response(message, code=500, data=_serialize_release(release, user))
    return ok_response(data=_serialize_release(release, user), message="执行成功")
