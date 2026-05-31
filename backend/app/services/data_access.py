import json
import re
import threading
import time
from typing import Optional

from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.services.collectors import collect_instance_metrics
from app.services.monitor_snapshot_service import latest_snapshot_for_instance
from app.utils.crypto import decrypt_secret

QUERY_ROW_LIMIT = 1000
MONGO_READONLY_COMMANDS = {
    "aggregate",
    "buildinfo",
    "collstats",
    "count",
    "dbstats",
    "distinct",
    "find",
    "listcollections",
    "listdatabases",
    "ping",
    "replsetgetstatus",
    "serverstatus",
}
MONGO_WRITE_COMMANDS = {
    "insert",
    "update",
    "delete",
    "findandmodify",
}
ACTIVE_EXECUTIONS = {}
ACTIVE_EXECUTIONS_LOCK = threading.Lock()

# ---------------- 数据查询允许操作配置缓存 ----------------
# TTL 内复用数据库读取的白名单，避免每次查询都走 DB；配置更新后通过
# invalidate_query_ops_cache() 立即失效。数据表未导入或查询异常时，fallback 到
# 硬编码的 MySQL_FALLBACK / MONGO_READONLY_COMMANDS / REDIS_FALLBACK 保证服务可用。
_QUERY_OPS_CACHE = {"data": None, "ts": 0.0}
_QUERY_OPS_CACHE_TTL = 60.0
_QUERY_OPS_LOCK = threading.Lock()

_MYSQL_QUERY_FALLBACK = {"select"}
_REDIS_QUERY_FALLBACK = {
    "get", "mget", "hget", "hgetall", "hexists",
    "exists", "scard", "smembers", "lrange", "zrange", "zrangebyscore",
}


def _load_query_ops_from_db():
    """从数据库读取启用的允许操作，返回按 db_type 分组的小写关键字 set。"""
    try:
        from app.models.data_query_op import DataQueryOperationConfig

        rows = DataQueryOperationConfig.query.filter_by(enabled=True).all()
    except Exception:
        return None
    groups = {"mysql": set(), "mongodb": set(), "redis": set()}
    for row in rows:
        if not row.op_key:
            continue
        groups.setdefault(row.db_type, set()).add(row.op_key.strip().lower())
    return groups


def _get_query_ops(db_type: str):
    """获取指定数据库类型的允许操作小写 set，自动缓存并 fallback。"""
    now = time.monotonic()
    with _QUERY_OPS_LOCK:
        data = _QUERY_OPS_CACHE.get("data")
        ts = _QUERY_OPS_CACHE.get("ts") or 0.0
        if data is None or (now - ts) > _QUERY_OPS_CACHE_TTL:
            refreshed = _load_query_ops_from_db()
            if refreshed is not None:
                _QUERY_OPS_CACHE["data"] = refreshed
                _QUERY_OPS_CACHE["ts"] = now
                data = refreshed
    if not data or not data.get(db_type):
        # fallback
        if db_type == "mysql":
            return set(_MYSQL_QUERY_FALLBACK)
        if db_type == "mongodb":
            return set(MONGO_READONLY_COMMANDS)
        if db_type == "redis":
            return set(_REDIS_QUERY_FALLBACK)
        return set()
    return set(data.get(db_type) or set())


def invalidate_query_ops_cache():
    """立即失效查询允许操作缓存，供 API 增删改后调用。"""
    with _QUERY_OPS_LOCK:
        _QUERY_OPS_CACHE["data"] = None
        _QUERY_OPS_CACHE["ts"] = 0.0


def register_execution(execution_id: str, user_id: Optional[int], db_type: str):
    with ACTIVE_EXECUTIONS_LOCK:
        ACTIVE_EXECUTIONS[execution_id] = {
            "user_id": user_id,
            "db_type": db_type,
            "cancel_callback": None,
        }


def set_execution_cancel_callback(execution_id: str, cancel_callback):
    with ACTIVE_EXECUTIONS_LOCK:
        row = ACTIVE_EXECUTIONS.get(execution_id)
        if not row:
            return False
        row["cancel_callback"] = cancel_callback
        return True


def finish_execution(execution_id: str):
    with ACTIVE_EXECUTIONS_LOCK:
        ACTIVE_EXECUTIONS.pop(execution_id, None)


def cancel_execution(execution_id: str, user_id: Optional[int], is_admin: bool):
    with ACTIVE_EXECUTIONS_LOCK:
        row = ACTIVE_EXECUTIONS.get(execution_id)
    if not row:
        return False, "execution not found or already finished"
    owner = row.get("user_id")
    if (not is_admin) and owner is not None and owner != user_id:
        return False, "permission denied"
    cancel_callback = row.get("cancel_callback")
    if not callable(cancel_callback):
        return False, "cancel is only supported for mysql execution"
    try:
        cancel_callback()
        return True, None
    except Exception as exc:
        return False, str(exc)


def _json_safe(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    try:
        from datetime import date, datetime

        if isinstance(value, (datetime, date)):
            return value.isoformat()
    except Exception:
        pass
    try:
        from bson import Decimal128
        from bson.objectid import ObjectId

        if isinstance(value, ObjectId):
            return str(value)
        if isinstance(value, Decimal128):
            return str(value.to_decimal())
    except Exception:
        pass
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _to_mongo_bson(value):
    try:
        from bson import json_util

        return json_util.loads(json.dumps(value))
    except Exception:
        return value


def _strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    sql = re.sub(r"--.*?$", " ", sql, flags=re.M)
    return sql


def _first_keyword(sql: str) -> str:
    cleaned = _strip_sql_comments(sql or "").strip()
    if not cleaned:
        return ""
    return cleaned.split()[0].lower()


def _split_sql_statements(sql: str):
    statements = []
    current = []
    quote = ""
    escaped = False
    in_line_comment = False
    in_block_comment = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < len(sql) else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
                current.append(ch)
            i += 1
            continue
        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue
        if not quote and ch == "-" and nxt == "-":
            in_line_comment = True
            i += 2
            continue
        if not quote and ch == "/" and nxt == "*":
            in_block_comment = True
            i += 2
            continue
        if quote:
            current.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = ""
            i += 1
            continue
        if ch in {"'", '"', "`"}:
            quote = ch
            current.append(ch)
            i += 1
            continue
        if ch == ";":
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            i += 1
            continue
        current.append(ch)
        i += 1
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def _safe_positive_int(value, default_value: int):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default_value
    return parsed if parsed > 0 else default_value


def validate_mysql_query(sql: str):
    keyword = _first_keyword(sql)
    if not keyword:
        return False, "sql is required"
    allowed = _get_query_ops("mysql")
    if keyword not in allowed:
        allowed_display = ", ".join(sorted(k.upper() for k in allowed)) or "SELECT"
        return False, f"only allowed operations: {allowed_display}"
    if ";" in sql.strip().rstrip(";"):
        return False, "multiple statements are not allowed"
    return True, None


def validate_mysql_change(sql: str):
    statements = _split_sql_statements(sql or "")
    if not statements:
        return False, "sql is required"
    return True, None


def _select_instance_by_role(db_type: str, cluster_id: int, role_candidates, payload_key: str):
    instances = DatabaseInstance.query.filter_by(cluster_id=cluster_id, db_type=db_type, enabled=True).all()
    if not instances:
        fallback_instances = DatabaseInstance.query.filter_by(cluster_id=cluster_id, db_type=db_type).all()
        return fallback_instances[0] if fallback_instances else None
    snapshots = {}
    for ins in instances:
        snap = latest_snapshot_for_instance(instance_id=ins.id, db_type=ins.db_type, metric_type="status")
        snapshots[ins.id] = snap.payload_json if snap else {}
    for role in role_candidates:
        for ins in instances:
            payload = snapshots.get(ins.id) or {}
            if payload.get(payload_key) == role:
                return ins
            if role == "slave" and payload.get("read_only") is True:
                return ins
            if role == "master" and payload.get("effective_read_only") is False:
                return ins
    return instances[0]


def _safe_optional_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _configured_route_instance_id(cluster: DatabaseCluster, for_change: bool):
    route = cluster.data_access_route_json if cluster and isinstance(cluster.data_access_route_json, dict) else {}
    key = "change" if for_change else "query"
    item = route.get(key) if isinstance(route.get(key), dict) else {}
    if str(item.get("mode") or "auto").strip().lower() != "manual":
        return None
    return _safe_optional_int(item.get("instance_id"))


def pick_instance(db_type: str, cluster_id: int, instance_id: int, for_change: bool, route_mode: str = "auto"):
    if instance_id:
        query = DatabaseInstance.query.filter_by(id=instance_id, db_type=db_type)
        if cluster_id:
            query = query.filter_by(cluster_id=cluster_id)
        return query.first()
    if not cluster_id:
        return None
    cluster = DatabaseCluster.query.get(cluster_id)
    normalized_route_mode = str(route_mode or "auto").strip().lower()
    if normalized_route_mode == "manual":
        return None
    if normalized_route_mode != "manual":
        configured_instance_id = _configured_route_instance_id(cluster, for_change)
        if configured_instance_id:
            configured = DatabaseInstance.query.filter_by(
                id=configured_instance_id,
                cluster_id=cluster_id,
                db_type=db_type,
                enabled=True,
            ).first()
            if configured:
                return configured
    if db_type == "mysql":
        return _select_instance_by_role(db_type, cluster_id, ["master", "master_slave"] if for_change else ["slave", "master_slave", "master"], "replication_role")
    if db_type == "mongodb":
        return _select_instance_by_role(db_type, cluster_id, ["primary"] if for_change else ["secondary", "primary"], "mongo_role")
    if db_type == "redis":
        return _select_instance_by_role(db_type, cluster_id, ["master"] if for_change else ["slave", "master"], "role")
    return None


def execute_mysql(
    instance: DatabaseInstance,
    sql: str,
    timeout_seconds: Optional[int],
    for_change: bool,
    database: Optional[str] = None,
    execution_id: Optional[str] = None,
):
    import pymysql

    password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
    host = instance.resolved_ip or instance.host_input
    timeout = max(0, int(timeout_seconds or 0))
    read_timeout = timeout if timeout > 0 else None
    connection = pymysql.connect(
        host=host,
        port=instance.port,
        user=instance.username,
        password=password,
        charset="utf8mb4",
        connect_timeout=5,
        read_timeout=read_timeout,
        write_timeout=read_timeout,
        database=(database or None),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
    if execution_id:
        mysql_connection_id = connection.thread_id()

        def _cancel_mysql():
            kill_conn = pymysql.connect(
                host=host,
                port=instance.port,
                user=instance.username,
                password=password,
                charset="utf8mb4",
                connect_timeout=5,
                read_timeout=5,
                write_timeout=5,
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True,
            )
            try:
                with kill_conn.cursor() as kill_cursor:
                    kill_cursor.execute(f"KILL QUERY {int(mysql_connection_id)}")
            finally:
                kill_conn.close()

        set_execution_cancel_callback(execution_id, _cancel_mysql)
    try:
        with connection.cursor() as cursor:
            if not for_change and timeout > 0:
                cursor.execute(f"SET SESSION MAX_EXECUTION_TIME={timeout * 1000}")
            if for_change:
                statements = _split_sql_statements(sql or "")
                if not statements:
                    return {"columns": [], "rows": [], "affected_rows": 0, "statements": []}
                statement_results = []
                total_affected = 0
                for stmt in statements:
                    cursor.execute(stmt)
                    affected = cursor.rowcount
                    total_affected += affected if isinstance(affected, int) and affected > 0 else 0
                    statement_results.append({"sql": stmt, "affected_rows": affected})
                return {
                    "columns": [],
                    "rows": [],
                    "affected_rows": total_affected,
                    "statement_count": len(statement_results),
                    "statements": statement_results,
                }
            cursor.execute(sql)
            if cursor.description:
                rows = cursor.fetchmany(QUERY_ROW_LIMIT + 1)
                truncated = len(rows) > QUERY_ROW_LIMIT
                if truncated:
                    rows = rows[:QUERY_ROW_LIMIT]
                columns = [col[0] for col in cursor.description]
                # 将 datetime/date/Decimal 等类型转换为 JSON 可序列化的字符串，datetime 输出为 ISO 格式
                rows = [_json_safe(row) for row in rows]
                return {"columns": columns, "rows": rows, "truncated": truncated, "limit": QUERY_ROW_LIMIT}
            return {"columns": [], "rows": [], "affected_rows": cursor.rowcount}
    finally:
        connection.close()


def list_mysql_databases(instance: DatabaseInstance, timeout_seconds: Optional[int] = 10):
    import pymysql

    password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
    host = instance.resolved_ip or instance.host_input
    connection = pymysql.connect(
        host=host,
        port=instance.port,
        user=instance.username,
        password=password,
        charset="utf8mb4",
        connect_timeout=5,
        read_timeout=timeout_seconds,
        write_timeout=timeout_seconds,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SHOW DATABASES")
            rows = cursor.fetchall() or []
            names = [row.get("Database") for row in rows if isinstance(row, dict)]
            return sorted([name for name in names if name])
    finally:
        connection.close()


def _open_mysql_connection(instance: DatabaseInstance, database: Optional[str], timeout_seconds: Optional[int] = 10):
    import pymysql

    password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
    host = instance.resolved_ip or instance.host_input
    return pymysql.connect(
        host=host,
        port=instance.port,
        user=instance.username,
        password=password,
        database=(database or None),
        charset="utf8mb4",
        connect_timeout=5,
        read_timeout=timeout_seconds,
        write_timeout=timeout_seconds,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


def list_mysql_objects(instance: DatabaseInstance, database: str, timeout_seconds: Optional[int] = 15):
    """列出指定数据库下的 tables / views / procedures / functions / triggers / events。"""
    if not database:
        raise ValueError("database is required")
    connection = _open_mysql_connection(instance, database, timeout_seconds=timeout_seconds)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT TABLE_NAME AS name, IFNULL(TABLE_ROWS,0) AS row_count, "
                "IFNULL(DATA_LENGTH,0)+IFNULL(INDEX_LENGTH,0) AS size_bytes "
                "FROM information_schema.TABLES "
                "WHERE TABLE_SCHEMA=%s AND TABLE_TYPE='BASE TABLE' "
                "ORDER BY TABLE_NAME",
                (database,),
            )
            tables = [
                {
                    "name": r.get("name"),
                    "row_count": int(r.get("row_count") or 0),
                    "size_bytes": int(r.get("size_bytes") or 0),
                }
                for r in cursor.fetchall() or []
                if r.get("name")
            ]
            cursor.execute(
                "SELECT TABLE_NAME AS name FROM information_schema.VIEWS "
                "WHERE TABLE_SCHEMA=%s ORDER BY TABLE_NAME",
                (database,),
            )
            views = [{"name": r.get("name")} for r in cursor.fetchall() or [] if r.get("name")]
            cursor.execute(
                "SELECT ROUTINE_NAME AS name FROM information_schema.ROUTINES "
                "WHERE ROUTINE_SCHEMA=%s AND ROUTINE_TYPE='PROCEDURE' ORDER BY ROUTINE_NAME",
                (database,),
            )
            procedures = [{"name": r.get("name")} for r in cursor.fetchall() or [] if r.get("name")]
            cursor.execute(
                "SELECT ROUTINE_NAME AS name FROM information_schema.ROUTINES "
                "WHERE ROUTINE_SCHEMA=%s AND ROUTINE_TYPE='FUNCTION' ORDER BY ROUTINE_NAME",
                (database,),
            )
            functions = [{"name": r.get("name")} for r in cursor.fetchall() or [] if r.get("name")]
            cursor.execute(
                "SELECT TRIGGER_NAME AS name FROM information_schema.TRIGGERS "
                "WHERE TRIGGER_SCHEMA=%s ORDER BY TRIGGER_NAME",
                (database,),
            )
            triggers = [{"name": r.get("name")} for r in cursor.fetchall() or [] if r.get("name")]
            try:
                cursor.execute(
                    "SELECT EVENT_NAME AS name FROM information_schema.EVENTS "
                    "WHERE EVENT_SCHEMA=%s ORDER BY EVENT_NAME",
                    (database,),
                )
                events = [{"name": r.get("name")} for r in cursor.fetchall() or [] if r.get("name")]
            except Exception:
                events = []
        return {
            "database": database,
            "tables": tables,
            "views": views,
            "procedures": procedures,
            "functions": functions,
            "triggers": triggers,
            "events": events,
        }
    finally:
        connection.close()


def list_mysql_table_columns(instance: DatabaseInstance, database: str, table: str, timeout_seconds: Optional[int] = 10):
    """返回指定表的字段元信息。"""
    if not database or not table:
        raise ValueError("database and table are required")
    connection = _open_mysql_connection(instance, database, timeout_seconds=timeout_seconds)
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT COLUMN_NAME AS name, DATA_TYPE AS data_type, COLUMN_TYPE AS column_type, "
                "IS_NULLABLE AS nullable, COLUMN_KEY AS column_key, COLUMN_DEFAULT AS column_default, "
                "IFNULL(COLUMN_COMMENT,'') AS comment, ORDINAL_POSITION AS position "
                "FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s "
                "ORDER BY ORDINAL_POSITION",
                (database, table),
            )
            rows = cursor.fetchall() or []
            columns = []
            for r in rows:
                columns.append(
                    {
                        "name": r.get("name"),
                        "data_type": r.get("data_type"),
                        "column_type": r.get("column_type"),
                        "nullable": (str(r.get("nullable") or "").upper() == "YES"),
                        "column_key": r.get("column_key") or "",
                        "default": r.get("column_default"),
                        "comment": r.get("comment") or "",
                        "position": int(r.get("position") or 0),
                    }
                )
            return columns
    finally:
        connection.close()


def validate_mongo_query(payload):
    op = str(payload.get("op") or "").lower()
    if not op and isinstance(payload.get("command"), dict):
        op = "run_command"
    allowed = _get_query_ops("mongodb")
    # 基本 op 必须在启用列表中（find/find_one/aggregate/count_documents/run_command 等）
    if op not in allowed:
        allowed_display = ", ".join(sorted(allowed)) or "find"
        return False, f"only allowed mongodb operations: {allowed_display}"
    if op == "run_command":
        command = payload.get("command")
        if not isinstance(command, dict) or not command:
            return False, "mongodb run_command requires non-empty command object"
        command_name = str(next(iter(command.keys()))).lower()
        if command_name not in allowed:
            allowed_display = ", ".join(sorted(allowed)) or "find"
            return False, f"mongodb run_command only allows: {allowed_display}"
    return True, None


def validate_mongo_change(payload):
    op = str(payload.get("op") or "").lower()
    if not op and isinstance(payload.get("command"), dict):
        op = "run_command"
    if op not in {"insert_one", "insert_many", "update_one", "update_many", "delete_one", "delete_many", "replace_one"}:
        if op != "run_command":
            return False, "unsupported mongodb change op"
    if op == "run_command":
        command = payload.get("command")
        if not isinstance(command, dict) or not command:
            return False, "mongodb run_command requires non-empty command object"
    return True, None


def execute_mongo(
    instance: DatabaseInstance,
    payload: dict,
    timeout_seconds: Optional[int],
    for_change: bool,
    seed_nodes: Optional[list] = None,
):
    from pymongo import MongoClient, ReadPreference

    password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
    host = instance.resolved_ip or instance.host_input
    connection_target = seed_nodes if seed_nodes else host
    connection_port = None if seed_nodes else instance.port
    client = MongoClient(
        connection_target,
        connection_port,
        username=instance.username,
        password=password,
        authSource="admin",
        directConnection=False,
        tls=False,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=timeout_seconds * 1000 if timeout_seconds else None,
        appname="dbms-data-access",
    )
    try:
        db_name = payload.get("db") or "admin"
        op = str(payload.get("op") or "").lower()
        if not op and isinstance(payload.get("command"), dict):
            op = "run_command"
        coll_name = payload.get("collection")
        if op != "run_command" and not coll_name:
            raise ValueError("collection is required")
        db = client.get_database(db_name)
        if not for_change:
            db = db.with_options(read_preference=ReadPreference.SECONDARY_PREFERRED)

        max_time_ms = timeout_seconds * 1000 if timeout_seconds else None
        collection = db.get_collection(coll_name) if coll_name else None
        if op == "find":
            mongo_filter = _to_mongo_bson(payload.get("filter") or {})
            mongo_projection = _to_mongo_bson(payload.get("projection"))
            cursor = collection.find(mongo_filter, mongo_projection)
            if payload.get("sort"):
                cursor = cursor.sort(payload.get("sort"))
            limit = QUERY_ROW_LIMIT
            if payload.get("limit"):
                limit = min(QUERY_ROW_LIMIT, _safe_positive_int(payload.get("limit"), QUERY_ROW_LIMIT))
            cursor = cursor.limit(limit + 1)
            if max_time_ms:
                cursor = cursor.max_time_ms(max_time_ms)
            rows = list(cursor)
            truncated = len(rows) > QUERY_ROW_LIMIT
            if truncated:
                rows = rows[:QUERY_ROW_LIMIT]
            return {"rows": _json_safe(rows), "truncated": truncated, "limit": QUERY_ROW_LIMIT}
        if op == "find_one":
            mongo_filter = _to_mongo_bson(payload.get("filter") or {})
            mongo_projection = _to_mongo_bson(payload.get("projection"))
            doc = collection.find_one(mongo_filter, mongo_projection)
            return {"rows": _json_safe([doc])}
        if op == "aggregate":
            pipeline = _to_mongo_bson(payload.get("pipeline") or []) + [{"$limit": QUERY_ROW_LIMIT + 1}]
            cursor = collection.aggregate(pipeline, maxTimeMS=max_time_ms) if max_time_ms else collection.aggregate(pipeline)
            rows = list(cursor)
            truncated = len(rows) > QUERY_ROW_LIMIT
            if truncated:
                rows = rows[:QUERY_ROW_LIMIT]
            return {"rows": _json_safe(rows), "truncated": truncated, "limit": QUERY_ROW_LIMIT}
        if op == "count_documents":
            count = collection.count_documents(_to_mongo_bson(payload.get("filter") or {}))
            return {"rows": [{"count": count}]}
        if op == "run_command":
            command = dict(_to_mongo_bson(payload.get("command") or {}))
            if (not for_change) and max_time_ms and "maxTimeMS" not in command:
                command["maxTimeMS"] = max_time_ms
            result = db.command(command)
            cursor_data = result.get("cursor") if isinstance(result, dict) else None
            first_batch = cursor_data.get("firstBatch") if isinstance(cursor_data, dict) else None
            truncated = False
            if isinstance(first_batch, list) and len(first_batch) > QUERY_ROW_LIMIT:
                truncated = True
                cursor_data["firstBatch"] = first_batch[:QUERY_ROW_LIMIT]
            return {"rows": _json_safe([result]), "truncated": truncated, "limit": QUERY_ROW_LIMIT}

        if op == "insert_one":
            result = collection.insert_one(_to_mongo_bson(payload.get("document") or {}))
            return {"rows": [{"inserted_id": str(result.inserted_id)}]}
        if op == "insert_many":
            result = collection.insert_many(_to_mongo_bson(payload.get("documents") or []))
            return {"rows": [{"inserted_ids": [str(x) for x in result.inserted_ids]}]}
        if op == "update_one":
            result = collection.update_one(
                _to_mongo_bson(payload.get("filter") or {}),
                _to_mongo_bson(payload.get("update") or {}),
                upsert=bool(payload.get("upsert")),
            )
            return {"rows": [{"matched": result.matched_count, "modified": result.modified_count}]}
        if op == "update_many":
            result = collection.update_many(
                _to_mongo_bson(payload.get("filter") or {}),
                _to_mongo_bson(payload.get("update") or {}),
                upsert=bool(payload.get("upsert")),
            )
            return {"rows": [{"matched": result.matched_count, "modified": result.modified_count}]}
        if op == "delete_one":
            result = collection.delete_one(_to_mongo_bson(payload.get("filter") or {}))
            return {"rows": [{"deleted": result.deleted_count}]}
        if op == "delete_many":
            result = collection.delete_many(_to_mongo_bson(payload.get("filter") or {}))
            return {"rows": [{"deleted": result.deleted_count}]}
        if op == "replace_one":
            result = collection.replace_one(
                _to_mongo_bson(payload.get("filter") or {}),
                _to_mongo_bson(payload.get("replacement") or {}),
                upsert=bool(payload.get("upsert")),
            )
            return {"rows": [{"matched": result.matched_count, "modified": result.modified_count}]}
        raise ValueError("unsupported operation")
    finally:
        client.close()


def list_mongo_databases(instance: DatabaseInstance, timeout_seconds: Optional[int] = 10, seed_nodes: Optional[list] = None):
    from pymongo import MongoClient, ReadPreference

    password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
    host = instance.resolved_ip or instance.host_input
    connection_target = seed_nodes if seed_nodes else host
    connection_port = None if seed_nodes else instance.port
    client = MongoClient(
        connection_target,
        connection_port,
        username=instance.username,
        password=password,
        authSource="admin",
        directConnection=False,
        tls=False,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=timeout_seconds * 1000 if timeout_seconds else None,
        appname="dbms-data-access",
    )
    try:
        names = client.list_database_names()
        return sorted(names)
    finally:
        client.close()


def list_mongo_collections(
    instance: DatabaseInstance,
    database: str,
    timeout_seconds: Optional[int] = 15,
    seed_nodes: Optional[list] = None,
):
    """列出指定 MongoDB 数据库下的 collections / views。

    返回结构：{ database, collections: [{name, type, doc_count, size_bytes}], views: [{name}] }
    """
    from pymongo import MongoClient

    if not database:
        raise ValueError("database is required")
    password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
    host = instance.resolved_ip or instance.host_input
    connection_target = seed_nodes if seed_nodes else host
    connection_port = None if seed_nodes else instance.port
    client = MongoClient(
        connection_target,
        connection_port,
        username=instance.username,
        password=password,
        authSource="admin",
        directConnection=False,
        tls=False,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=timeout_seconds * 1000 if timeout_seconds else None,
        appname="dbms-data-access",
    )
    try:
        db = client.get_database(database)
        # 使用 listCollections 获取 name + type（轻量）
        infos = list(db.list_collections(filter=None, nameOnly=False))
        collections = []
        views = []
        for info in infos:
            name = info.get("name")
            if not name:
                continue
            coll_type = str(info.get("type") or "collection").lower()
            if coll_type == "view":
                views.append({"name": name})
                continue
            collections.append({
                "name": name,
                "type": coll_type or "collection",
                "doc_count": None,
                "size_bytes": None,
            })
        collections.sort(key=lambda x: x.get("name") or "")
        views.sort(key=lambda x: x.get("name") or "")
        return {
            "database": database,
            "collections": collections,
            "views": views,
        }
    finally:
        client.close()


def describe_mongo_collection(
    instance: DatabaseInstance,
    database: str,
    collection: str,
    timeout_seconds: Optional[int] = 10,
    seed_nodes: Optional[list] = None,
):
    """返回 MongoDB 集合的概要信息（文档数、大小、索引、示例字段）。"""
    from pymongo import MongoClient

    if not database or not collection:
        raise ValueError("database and collection are required")
    password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
    host = instance.resolved_ip or instance.host_input
    connection_target = seed_nodes if seed_nodes else host
    connection_port = None if seed_nodes else instance.port
    client = MongoClient(
        connection_target,
        connection_port,
        username=instance.username,
        password=password,
        authSource="admin",
        directConnection=False,
        tls=False,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=timeout_seconds * 1000 if timeout_seconds else None,
        appname="dbms-data-access",
    )
    try:
        db = client.get_database(database)
        stats = {}
        try:
            stats = db.command({"collStats": collection})
        except Exception:
            stats = {}
        doc_count = stats.get("count")
        size_bytes = stats.get("size") or stats.get("storageSize")
        indexes = []
        try:
            for idx in db.get_collection(collection).list_indexes():
                indexes.append({
                    "name": idx.get("name"),
                    "key": [list(item) for item in (idx.get("key") or {}).items()],
                    "unique": bool(idx.get("unique") or False),
                })
        except Exception:
            indexes = []
        sample_fields = []
        try:
            sample_doc = db.get_collection(collection).find_one()
            if isinstance(sample_doc, dict):
                for key, value in sample_doc.items():
                    sample_fields.append({
                        "name": key,
                        "type": type(value).__name__,
                    })
        except Exception:
            sample_fields = []
        return {
            "database": database,
            "collection": collection,
            "doc_count": int(doc_count) if isinstance(doc_count, (int, float)) else None,
            "size_bytes": int(size_bytes) if isinstance(size_bytes, (int, float)) else None,
            "indexes": indexes,
            "sample_fields": sample_fields,
        }
    finally:
        client.close()


def validate_redis_query(payload):
    cmd = str(payload.get("command") or "").strip()
    if not cmd:
        return False, "redis command is required"
    allowed = _get_query_ops("redis")
    if cmd.lower() not in allowed:
        allowed_display = ", ".join(sorted(k.upper() for k in allowed)) or "GET"
        return False, f"only allowed redis commands: {allowed_display}"
    return True, None


def validate_redis_change(payload):
    cmd = str(payload.get("command") or "").upper()
    if not cmd:
        return False, "redis command is required"
    return True, None


def execute_redis(instance: DatabaseInstance, payload: dict, timeout_seconds: Optional[int], seed_nodes: Optional[list] = None):
    import redis
    from redis.sentinel import Sentinel
    from app.models.monitor_snapshot import MonitorSnapshotRedis

    password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
    host = instance.resolved_ip or instance.host_input
    cmd = payload.get("command")
    args = payload.get("args") or []
    timeout = timeout_seconds if timeout_seconds else None

    # 尝试识别高可用模式
    ha_mode = "standalone"
    master_name = None
    
    if instance.cluster:
        # 1. 检查是否有哨兵角色
        sentinel_instances = [i for i in instance.cluster.instances if i.enabled and str(i.role_label or "").lower() == "sentinel"]
        if sentinel_instances:
            ha_mode = "sentinel"
            extra = instance.cluster.ha_status_json if isinstance(instance.cluster.ha_status_json, dict) else {}
            master_name = extra.get("master_name") or instance.cluster.name
        else:
            # 2. 检查快照中的 redis_mode
            snapshot = MonitorSnapshotRedis.query.filter_by(instance_id=instance.id).order_by(MonitorSnapshotRedis.collected_at.desc()).first()
            if snapshot and isinstance(snapshot.payload_json, dict):
                mode = str(snapshot.payload_json.get("redis_mode") or "").lower()
                if mode == "cluster":
                    ha_mode = "cluster"
                elif mode == "sentinel":
                    ha_mode = "sentinel"
                    master_name = snapshot.payload_json.get("master_name") or instance.cluster.name

    # 执行逻辑
    if ha_mode == "cluster":
        startup_nodes = []
        nodes_to_use = seed_nodes if seed_nodes else [f"{host}:{instance.port}"]
        for node in nodes_to_use:
            if ":" not in str(node): continue
            node_host, node_port = str(node).split(":", 1)
            try:
                startup_nodes.append(redis.cluster.ClusterNode(node_host, int(node_port)))
            except Exception: continue
        
        if startup_nodes:
            cluster_client = redis.RedisCluster(
                startup_nodes=startup_nodes,
                password=password,
                socket_connect_timeout=5,
                socket_timeout=timeout,
                decode_responses=True,
            )
            try:
                return {"rows": [cluster_client.execute_command(cmd, *args)]}
            finally:
                cluster_client.close()

    elif ha_mode == "sentinel" and master_name:
        sentinel_nodes = []
        if sentinel_instances:
            for s in sentinel_instances:
                s_host = s.resolved_ip or s.host_input
                sentinel_nodes.append((s_host, s.port))
        else:
            # 如果没找到哨兵实例，尝试把当前实例当哨兵（某些配置下可能如此）
            sentinel_nodes.append((host, instance.port))
            
        sentinel_client = Sentinel(
            sentinel_nodes,
            password=password,
            socket_connect_timeout=5,
            socket_timeout=timeout,
            decode_responses=True,
        )
        # 变更操作走主库，查询操作理论上可以走从库，但为了稳妥和统一，默认走主库
        master = sentinel_client.master_for(master_name)
        return {"rows": [master.execute_command(cmd, *args)]}

    # 默认 Standalone / Master-Slave (带 MOVED 处理以防识别漏掉)
    def _build_client(redis_host, redis_port):
        return redis.Redis(
            host=redis_host,
            port=redis_port,
            password=password,
            socket_connect_timeout=5,
            socket_timeout=timeout,
            decode_responses=True,
        )

    client = _build_client(host, instance.port)
    try:
        try:
            return {"rows": [client.execute_command(cmd, *args)]}
        except redis.exceptions.ResponseError as exc:
            message = str(exc)
            moved = re.match(r"^MOVED\s+\d+\s+([^\s:]+):(\d+)$", message, re.I)
            if not moved:
                raise
            target_host = moved.group(1)
            target_port = int(moved.group(2))
            redirected = _build_client(target_host, target_port)
            try:
                return {"rows": [redirected.execute_command(cmd, *args)]}
            finally:
                redirected.close()
    finally:
        client.close()


def normalize_payload(raw):
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return {}


def _parse_mongo_shell_command(raw_command: str):
    """
    解析 MongoDB shell 风格的命令字符串，如：
    db.test.updateOne({name:"Gemini"}, {$set: {name:"new"}})
    db.test.aggregate([{$group: {_id: "$status", count: {$sum: 1}}}])
    返回 (collection_name, operation, args_list)
    """
    import re

    command = raw_command.strip().rstrip(";")
    matched = re.match(r"^db\.([a-zA-Z_][\w]*)\.(insertOne|insertMany|updateOne|updateMany|deleteOne|deleteMany|replaceOne|find|findOne|aggregate)\(", command, re.I)
    if not matched:
        return None, None, None
    collection = matched.group(1)
    operation = matched.group(2).lower()
    start_pos = matched.end()

    args_str = _extract_args_from_pos(command, start_pos)
    if args_str is None:
        return None, None, None

    args = _split_mongo_args(args_str)
    return collection, operation, args


def _extract_args_from_pos(command: str, start_pos: int):
    """从 start_pos 开始提取配对的括号内容"""
    depth = 1
    i = start_pos
    start = i
    quote = None
    escaped = False

    while i < len(command) and depth > 0:
        ch = command[i]

        if escaped:
            escaped = False
            i += 1
            continue

        if ch == '\\':
            escaped = True
            i += 1
            continue

        if quote:
            if ch == quote:
                quote = None
            i += 1
            continue

        if ch in ("'", '"'):
            quote = ch
            i += 1
            continue

        if ch in ("{", "[", "("):
            depth += 1
            i += 1
            continue

        if ch in ("}", "]", ")"):
            depth -= 1
            if depth == 0:
                return command[start:i]
            i += 1
            continue

        i += 1

    return None


def _split_mongo_args(args_str: str):
    """
    解析 MongoDB shell 风格的参数列表，处理嵌套的 {} 和 [] 以及引号
    """
    args = []
    current = ""
    depth = 0
    quote = None
    escaped = False

    i = 0
    while i < len(args_str):
        ch = args_str[i]

        if escaped:
            current += ch
            escaped = False
            i += 1
            continue

        if ch == "\\":
            current += ch
            escaped = True
            i += 1
            continue

        if quote:
            current += ch
            if ch == quote:
                quote = None
            i += 1
            continue

        if ch in ("'", '"'):
            current += ch
            quote = ch
            i += 1
            continue

        if ch in ("{", "[", "("):
            depth += 1
            current += ch
            i += 1
            continue

        if ch in ("}", "]", ")"):
            depth = max(0, depth - 1)
            current += ch
            i += 1
            continue

        if ch == "," and depth == 0:
            args.append(current.strip())
            current = ""
            i += 1
            continue

        current += ch
        i += 1

    tail = current.strip()
    if tail:
        args.append(tail)

    return args


def _convert_mongo_arg(arg: str):
    """
    将 MongoDB shell 风格的参数字符串转换为 Python 对象
    """
    arg = arg.strip()
    if not arg:
        return None

    if arg in ("true", "false"):
        return arg == "true"
    if arg == "null":
        return None
    if arg == "undefined":
        return None

    try:
        return int(arg)
    except ValueError:
        pass

    try:
        return float(arg)
    except ValueError:
        pass

    try:
        return json.loads(arg)
    except Exception:
        pass

    arg_normalized = arg
    arg_normalized = re.sub(r"ObjectId\s*\(\s*'([^']+)'\s*\)", r'{"$oid": "\1"}', arg_normalized)
    arg_normalized = re.sub(r'ObjectId\s*\(\s*"([^"]+)"\s*\)', r'{"$oid": "\1"}', arg_normalized)
    arg_normalized = re.sub(r"([{,]\s*)([a-zA-Z_$][\w$]*)\s*:", r'\1"\2":', arg_normalized)
    arg_normalized = re.sub(r":\s*'([^'\\]*(?:\\.[^'\\]*)*)'", r': "\1"', arg_normalized)

    try:
        return json.loads(arg_normalized)
    except Exception:
        pass

    return arg


def _mongo_to_bson(value):
    """将 Python 值转换为 MongoDB BSON"""
    try:
        from bson import json_util
        return json_util.loads(json.dumps(value))
    except Exception:
        return value


def execute_mongo_raw(
    instance: DatabaseInstance,
    mongo_command: str,
    database: str,
    timeout_seconds: Optional[int],
    seed_nodes: Optional[list] = None,
):
    """
    执行原生 MongoDB shell 命令字符串
    """
    from pymongo import MongoClient

    password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
    host = instance.resolved_ip or instance.host_input
    connection_target = seed_nodes if seed_nodes else host
    connection_port = None if seed_nodes else instance.port
    client = MongoClient(
        connection_target,
        connection_port,
        username=instance.username,
        password=password,
        authSource="admin",
        directConnection=False,
        tls=False,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=timeout_seconds * 1000 if timeout_seconds else None,
        appname="dbms-data-access",
    )
    try:
        db = client.get_database(database or "admin")
        collection_name, operation, args = _parse_mongo_shell_command(mongo_command)

        if not operation:
            raise ValueError(f"无法解析 MongoDB 命令: {mongo_command}")

        collection = db.get_collection(collection_name)
        args_parsed = [_convert_mongo_arg(a) for a in args]
        args_bson = [_mongo_to_bson(a) for a in args_parsed]

        max_time_ms = timeout_seconds * 1000 if timeout_seconds else None

        if operation == "insertone":
            result = collection.insert_one(*args_bson)
            return {"rows": [{"inserted_id": str(result.inserted_id)}]}
        if operation == "insertmany":
            result = collection.insert_many(*args_bson)
            return {"rows": [{"inserted_ids": [str(x) for x in result.inserted_ids]}]}
        if operation == "updateone":
            result = collection.update_one(*args_bson)
            return {"rows": [{"matched": result.matched_count, "modified": result.modified_count}]}
        if operation == "updatemany":
            result = collection.update_many(*args_bson)
            return {"rows": [{"matched": result.matched_count, "modified": result.modified_count}]}
        if operation == "deleteone":
            result = collection.delete_one(*args_bson)
            return {"rows": [{"deleted": result.deleted_count}]}
        if operation == "deletemany":
            result = collection.delete_many(*args_bson)
            return {"rows": [{"deleted": result.deleted_count}]}
        if operation == "replaceone":
            result = collection.replace_one(*args_bson)
            return {"rows": [{"matched": result.matched_count, "modified": result.modified_count}]}
        if operation == "find":
            if not args_bson:
                args_bson = [{}]
            mongo_filter = args_bson[0] if args_bson else {}
            cursor = collection.find(mongo_filter)
            if max_time_ms:
                cursor = cursor.max_time_ms(max_time_ms)
            cursor = cursor.limit(QUERY_ROW_LIMIT + 1)
            rows = list(cursor)
            truncated = len(rows) > QUERY_ROW_LIMIT
            if truncated:
                rows = rows[:QUERY_ROW_LIMIT]
            return {"rows": _json_safe(rows), "truncated": truncated, "limit": QUERY_ROW_LIMIT}
        if operation == "findone":
            if not args_bson:
                args_bson = [{}]
            mongo_filter = args_bson[0] if args_bson else {}
            doc = collection.find_one(mongo_filter)
            return {"rows": _json_safe([doc]) if doc else []}

        raise ValueError(f"不支持的操作: {operation}")
    finally:
        client.close()


def execute_mongo_query_raw(
    instance: DatabaseInstance,
    mongo_command: str,
    database: str,
    timeout_seconds: Optional[int],
    seed_nodes: Optional[list] = None,
):
    """
    执行原生 MongoDB shell 查询命令字符串
    支持 db.collection.aggregate([...]), db.collection.find({...}) 等格式
    """
    from pymongo import MongoClient, ReadPreference

    password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
    host = instance.resolved_ip or instance.host_input
    connection_target = seed_nodes if seed_nodes else host
    connection_port = None if seed_nodes else instance.port
    client = MongoClient(
        connection_target,
        connection_port,
        username=instance.username,
        password=password,
        authSource="admin",
        directConnection=False,
        tls=False,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=timeout_seconds * 1000 if timeout_seconds else None,
        appname="dbms-data-access",
    )
    try:
        db = client.get_database(database or "admin")
        db = db.with_options(read_preference=ReadPreference.SECONDARY_PREFERRED)

        command_doc = _build_mongo_runcommand(mongo_command)
        if not command_doc:
            raise ValueError(f"无法解析查询命令: {mongo_command}")

        max_time_ms = timeout_seconds * 1000 if timeout_seconds else None
        if max_time_ms and "maxTimeMS" not in command_doc:
            command_doc["maxTimeMS"] = max_time_ms

        result = db.command(command_doc)

        if "cursor" in result and isinstance(result["cursor"], dict):
            cursor = result["cursor"]
            first_batch = cursor.get("firstBatch", [])
            next_batch = cursor.get("nextBatch", [])
            rows = first_batch + next_batch
            truncated = len(rows) > QUERY_ROW_LIMIT
            if truncated:
                rows = rows[:QUERY_ROW_LIMIT]
            return {"rows": _json_safe(rows), "truncated": truncated, "limit": QUERY_ROW_LIMIT}

        return {"rows": _json_safe([result])}
    finally:
        client.close()


def _build_mongo_runcommand(mongo_command: str):
    """
    将 MongoDB shell 命令转换为 runCommand 格式
    例如：db.test.aggregate([{$group: {_id: "$status", count: {$sum: 1}}}])
    转换为：{"aggregate": "test", "pipeline": [...], "cursor": {}}
    """
    import re

    command = mongo_command.strip().rstrip(";")
    match = re.match(r"^db\.([a-zA-Z_][\w]*)\.(aggregate|find|findOne|count|distinct)\((.*)\)$", command, re.DOTALL | re.I)
    if not match:
        return None

    collection_name = match.group(1)
    method = match.group(2).lower()
    args_str = match.group(3)

    args = _split_mongo_args(args_str)

    if method == "aggregate":
        pipeline = _convert_mongo_arg(args[0]) if args else []
        return {"aggregate": collection_name, "pipeline": pipeline, "cursor": {}}

    if method == "find":
        query = _convert_mongo_arg(args[0]) if args else {}
        return {"find": collection_name, "filter": query, "limit": QUERY_ROW_LIMIT}

    if method == "findone":
        query = _convert_mongo_arg(args[0]) if args else {}
        return {"find": collection_name, "filter": query, "limit": 1}

    if method == "count":
        query = _convert_mongo_arg(args[0]) if args else {}
        return {"count": collection_name, "query": query}

    if method == "distinct":
        if not args:
            return None
        field = _convert_mongo_arg(args[0])
        query = _convert_mongo_arg(args[1]) if len(args) > 1 else {}
        return {"distinct": collection_name, "key": field, "query": query}

    return None
