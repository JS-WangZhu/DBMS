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
from app.models.sql_release import SqlRelease, SqlReleaseRollbackBackup
from app.models.user import User
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
    execute_release_rollback,
    review_release,
    split_sql_statements,
    validate_mongo_release_statement,
)
from app.services.sql_release_review import dispatch_sql_release_review
from app.services.sql_release_agent import execute_sql_release_on_agent
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


def _serialize_release(row, user=None, executable_cluster_ids=None, include_rollback_sql=False):
    data = row.to_dict()
    data["execution_mode"] = "agent" if row.instance and row.instance.access_mode == "agent" else "server"
    data["execution_agent_name"] = row.instance.probe_agent.name if row.instance and row.instance.probe_agent else None
    can_execute = False
    if user:
        can_execute = user.role == "admin" or (
            row.cluster_id in executable_cluster_ids
            if executable_cluster_ids is not None
            else require_cluster_permission(row.cluster_id, "execute")
        )
        data["can_execute"] = can_execute
    backups = SqlReleaseRollbackBackup.query.filter_by(release_id=row.id).order_by(
        SqlReleaseRollbackBackup.statement_line
    ).all()
    backup_by_line = {item.statement_line: item for item in backups}
    execution_by_line = {
        int(item.get("line") or 0): item
        for item in ((row.execution_result_json or {}).get("statements") or [])
        if int(item.get("line") or 0) > 0
    }
    source_statements = split_sql_statements(row.sql_text)
    statement_executions = []
    for line, sql in enumerate(source_statements, start=1):
        backup = backup_by_line.get(line)
        state = dict(execution_by_line.get(line) or {})
        item = {
            "line": line,
            "sql": sql,
            "status": state.get("status") or "pending",
            "affected_rows": state.get("affected_rows"),
            "backup_rows": state.get("backup_rows", backup.row_count if backup else 0),
            "error": state.get("error"),
            "rollback_error": state.get("rollback_error"),
            "rollback_affected_rows": state.get("rollback_affected_rows"),
            "has_rollback": bool(backup),
        }
        if include_rollback_sql and can_execute and backup:
            item["rollback_sql"] = decrypt_secret(backup.rollback_sql_encrypted)
        statement_executions.append(item)
    data["statement_executions"] = statement_executions
    data["rollback_data_backups"] = [{
        "line": item.statement_line,
        "operation": item.operation,
        "table": item.table_name,
        "row_count": item.row_count,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    } for item in backups]
    data["can_retry_execute"] = False
    data["can_rollback"] = bool(
        can_execute
        and row.db_type in {"mysql", "postgresql"}
        and any(item["has_rollback"] and item["status"] in {"success", "rollback_failed"} for item in statement_executions)
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
        review_json=[{
            "line": index, "sql": statement, "passed": None,
            "risk_level": None, "reason": "等待 AI 初审",
            "suggestion": "", "status": "pending",
        } for index, statement in enumerate(statements, start=1)],
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


@bp.get("/<int:release_id>/review-progress")
@require_menu_permission("sql_release_apply")
def get_sql_release_review_progress(release_id):
    release = SqlRelease.query.get_or_404(release_id)
    user = get_current_user()
    if user.role != "admin" and release.applicant_id != user.id:
        return error_response("permission denied", code=403)
    return ok_response(data=_serialize_release(release, user))


@bp.post("/<int:release_id>/force-submit")
@require_menu_permission("sql_release_apply")
def force_submit_sql_release(release_id):
    release = SqlRelease.query.get_or_404(release_id)
    user = get_current_user()
    if user.role != "admin" and release.applicant_id != user.id:
        return error_response("permission denied", code=403)
    if not require_cluster_permission(release.cluster_id, "change"):
        return error_response("permission denied", code=403)
    if release.status != "review_rejected":
        return error_response("仅 AI 初审未通过的工单可以强制提交", code=409)
    release.force_submitted = True
    release.status = "pending"
    db.session.commit()
    log_audit(
        user_id=user.id,
        action="sql_release.force_submit",
        target_type="sql_release",
        target_id=str(release.id),
        detail={"status": release.status, "ai_passed": False},
    )
    return ok_response(data=_serialize_release(release, user), message="已确认影响，工单已强制提交")



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
    db_type = str(request.args.get("db_type") or "").strip().lower()
    if db_type:
        query = query.filter(SqlRelease.db_type == db_type)

    applicant = str(request.args.get("applicant") or "").strip()
    if applicant:
        escaped_applicant = applicant.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        applicant_pattern = f"%{escaped_applicant}%"
        query = query.join(User, SqlRelease.applicant_id == User.id).filter(or_(
            User.username.ilike(applicant_pattern, escape="\\"),
            User.display_name.ilike(applicant_pattern, escape="\\"),
        ))

    status = str(request.args.get("status") or "").strip()
    if status:
        query = query.filter(SqlRelease.status == status)

    title_keyword = str(request.args.get("title_keyword") or "").strip()
    if title_keyword:
        escaped_title = title_keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(SqlRelease.title.ilike(f"%{escaped_title}%", escape="\\"))

    start_time = str(request.args.get("start_time") or "").strip()
    end_time = str(request.args.get("end_time") or "").strip()
    try:
        start_dt = datetime.fromisoformat(start_time) if start_time else None
        end_dt = datetime.fromisoformat(end_time) if end_time else None
    except ValueError:
        return error_response("invalid time range", code=400)
    if start_dt and end_dt and start_dt > end_dt:
        return error_response("start_time must not be later than end_time", code=400)
    if start_dt:
        query = query.filter(SqlRelease.created_at >= start_dt)
    if end_dt:
        query = query.filter(SqlRelease.created_at <= end_dt)
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
    return ok_response(data=_serialize_release(row, user, executable_cluster_ids, include_rollback_sql=True))


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
    execution_source = "server"
    try:
        if instance.access_mode == "agent":
            if not instance.probe_agent_id:
                raise ValueError("实例为 Agent 模式但未绑定可用 Agent")
            execution_source = "agent"
            result = execute_sql_release_on_agent(
                instance,
                release.database_name,
                statements,
                db_type,
                seed_nodes=_cluster_seed_nodes(db_type, release.cluster_id) if db_type == "mongodb" else None,
            )
            backup_path = None
        elif db_type == "mysql":
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
        release.execution_result_json = {**result, "execution_source": execution_source}
    except Exception as exc:
        generated_rollback_path = getattr(exc, "rollback_path", None)
        if generated_rollback_path:
            backup_path = generated_rollback_path
            release.rollback_backup_path = generated_rollback_path
        release.status = "failed"
        execution_result = dict(getattr(exc, "result", None) or release.execution_result_json or {})
        execution_result["error"] = str(exc)
        execution_result["execution_source"] = execution_source
        release.execution_result_json = execution_result
    release.executed_by = user.id
    release.executed_at = datetime.utcnow()
    db.session.commit()
    log_audit(user_id=user.id, action="sql_release.execute", target_type="sql_release", target_id=str(release.id), detail={
        "status": release.status,
        "rollback_backup_path": backup_path,
        "execution_source": execution_source,
        "agent_id": instance.probe_agent_id if execution_source == "agent" else None,
        "database_user": instance.username,
    })
    if release.status == "failed":
        error_detail = str((release.execution_result_json or {}).get("error") or "").strip()
        if db_type == "mongodb":
            message = "MongoDB 执行失败，已停止后续语句（当前不生成回滚备份）"
        else:
            message = "执行失败，可使用已生成的回滚文件恢复" if backup_path else "回滚文件生成失败，已中止执行"
        if error_detail:
            message = f"{message}：{error_detail}"
        return error_response(message, code=500, data=_serialize_release(release, user, include_rollback_sql=True))
    return ok_response(data=_serialize_release(release, user, include_rollback_sql=True), message="执行成功")


@bp.post("/<int:release_id>/rollback")
@require_menu_permission("sql_release_history")
def rollback_sql_release(release_id):
    release = SqlRelease.query.get_or_404(release_id)
    user = get_current_user()
    if user.role != "admin" and not require_cluster_permission(release.cluster_id, "execute"):
        return error_response("permission denied", code=403)
    if release.db_type not in {"mysql", "postgresql"}:
        return error_response("MongoDB 工单当前不支持回滚", code=400)
    if release.status in {"executing", "rolling_back"}:
        return error_response("工单正在执行或回滚，请稍后再试", code=409)

    payload = request.get_json(silent=True) or {}
    requested_lines = payload.get("lines")
    if requested_lines is not None:
        if not isinstance(requested_lines, list):
            return error_response("lines must be an array", code=400)
        try:
            requested_lines = {int(line) for line in requested_lines}
        except (TypeError, ValueError):
            return error_response("invalid rollback line", code=400)
        if not requested_lines:
            return error_response("请选择需要回滚的 SQL", code=400)

    states = {
        int(item.get("line") or 0): item
        for item in ((release.execution_result_json or {}).get("statements") or [])
    }
    source_statements = split_sql_statements(release.sql_text)
    backups = SqlReleaseRollbackBackup.query.filter_by(release_id=release.id).all()
    eligible = {
        item.statement_line: item for item in backups
        if (states.get(item.statement_line) or {}).get("status") in {"success", "rollback_failed"}
    }
    selected_lines = requested_lines if requested_lines is not None else set(eligible)
    invalid_lines = selected_lines.difference(eligible)
    if invalid_lines:
        return error_response(
            f"第 {', '.join(str(line) for line in sorted(invalid_lines))} 条不可回滚",
            code=409,
        )
    if not selected_lines:
        return error_response("没有可回滚的已成功 SQL", code=409)

    instance = DatabaseInstance.query.get(release.instance_id)
    if not instance or not instance.enabled:
        return error_response("release instance is unavailable", code=400)
    rollback_items = [{
        "line": line,
        "source_sql": source_statements[line - 1] if line <= len(source_statements) else "",
        "rollback_sql": decrypt_secret(eligible[line].rollback_sql_encrypted),
    } for line in sorted(selected_lines, reverse=True)]
    release.status = "rolling_back"
    db.session.commit()
    try:
        result = execute_release_rollback(
            instance, release.database_name, rollback_items,
            release.db_type, release.id,
        )
        latest_states = (release.execution_result_json or {}).get("statements") or []
        release.status = "partial_rolled_back" if any(
            item.get("status") == "success" for item in latest_states
        ) else "rolled_back"
        message = "部分回滚完成" if release.status == "partial_rolled_back" else "回滚完成"
    except Exception as exc:
        result = {"error": str(exc), "line": getattr(exc, "line", None)}
        release.status = "rollback_failed"
        message = f"回滚失败：{exc}"
    db.session.commit()
    log_audit(
        user_id=user.id,
        action="sql_release.rollback",
        target_type="sql_release",
        target_id=str(release.id),
        detail={"status": release.status, "lines": sorted(selected_lines, reverse=True)},
    )
    if release.status == "rollback_failed":
        return error_response(message, code=500, data=_serialize_release(release, user, include_rollback_sql=True))
    return ok_response(
        data={"release": _serialize_release(release, user, include_rollback_sql=True), "result": result},
        message=message,
    )
