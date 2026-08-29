import base64
import json
import re
import zlib
from datetime import datetime, timedelta, timezone
from threading import Lock
from uuid import uuid4

from flask import current_app

from app.extensions import db
from app.models.query_audit import QueryAuditOutbox
from app.utils.crypto import decrypt_secret, encrypt_secret


AUDIT_COLUMNS = [
    "event_id", "version", "created_at", "finished_at", "user_id", "username",
    "client_ip", "user_agent", "execution_id", "db_type", "business_line",
    "environment", "cluster_id", "cluster_name", "instance_id", "instance_name",
    "database_name", "statement", "request_json", "success", "status",
    "failure_stage", "http_status", "error_message", "duration_ms", "result_json",
    "result_row_count", "result_truncated",
]

LIST_COLUMNS = [
    "event_id", "created_at", "finished_at", "user_id", "username", "db_type",
    "business_line", "environment", "cluster_id", "cluster_name", "instance_id",
    "instance_name", "database_name", "statement", "success", "status",
    "failure_stage", "http_status", "error_message", "duration_ms",
    "result_row_count", "result_truncated",
]

_client = None
_client_key = None
_schema_key = None
_client_lock = Lock()


class QueryAuditUnavailable(RuntimeError):
    pass


def _utc_now():
    return datetime.now(timezone.utc)


def _json_dumps(value):
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))


def _json_loads(value, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _identifier(value, fallback):
    normalized = str(value or fallback).strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", normalized):
        raise QueryAuditUnavailable("ClickHouse audit identifier is invalid")
    return normalized


def _settings():
    return {
        "host": str(current_app.config.get("CLICKHOUSE_AUDIT_HOST") or "").strip(),
        "port": int(current_app.config.get("CLICKHOUSE_AUDIT_PORT") or 8123),
        "username": str(current_app.config.get("CLICKHOUSE_AUDIT_USER") or "default"),
        "password": str(current_app.config.get("CLICKHOUSE_AUDIT_PASSWORD") or ""),
        "database": _identifier(current_app.config.get("CLICKHOUSE_AUDIT_DATABASE"), "dbms_audit"),
        "table": _identifier(current_app.config.get("CLICKHOUSE_AUDIT_TABLE"), "query_audit_events"),
        "secure": bool(current_app.config.get("CLICKHOUSE_AUDIT_SECURE")),
        "verify": bool(current_app.config.get("CLICKHOUSE_AUDIT_VERIFY")),
        "connect_timeout": int(current_app.config.get("CLICKHOUSE_AUDIT_CONNECT_TIMEOUT") or 5),
        "send_receive_timeout": int(current_app.config.get("CLICKHOUSE_AUDIT_QUERY_TIMEOUT") or 15),
    }


def _get_client():
    global _client, _client_key
    settings = _settings()
    if not settings["host"]:
        raise QueryAuditUnavailable("ClickHouse audit host is not configured")
    key = tuple(settings.items())
    with _client_lock:
        if _client is not None and _client_key == key:
            return _client
        try:
            import clickhouse_connect

            _client = clickhouse_connect.get_client(
                host=settings["host"],
                port=settings["port"],
                username=settings["username"],
                password=settings["password"],
                secure=settings["secure"],
                verify=settings["verify"],
                connect_timeout=settings["connect_timeout"],
                send_receive_timeout=settings["send_receive_timeout"],
            )
        except Exception as exc:
            _client = None
            _client_key = None
            raise QueryAuditUnavailable(str(exc) or "ClickHouse connection failed") from exc
        _client_key = key
        return _client


def reset_clickhouse_client():
    global _client, _client_key, _schema_key
    with _client_lock:
        _client = None
        _client_key = None
        _schema_key = None


def _qualified_table():
    settings = _settings()
    return f"`{settings['database']}`.`{settings['table']}`"


def ensure_clickhouse_schema():
    global _schema_key
    settings = _settings()
    client = _get_client()
    schema_key = (id(client), settings["database"], settings["table"])
    if _schema_key == schema_key:
        return
    client.command(f"CREATE DATABASE IF NOT EXISTS `{settings['database']}`")
    client.command(
        f"""
        CREATE TABLE IF NOT EXISTS {_qualified_table()} (
            event_id UUID,
            version UInt64,
            created_at DateTime64(3, 'UTC'),
            finished_at Nullable(DateTime64(3, 'UTC')),
            user_id UInt64,
            username String,
            client_ip String,
            user_agent String,
            execution_id String,
            db_type LowCardinality(String),
            business_line String,
            environment String,
            cluster_id UInt64,
            cluster_name String,
            instance_id UInt64,
            instance_name String,
            database_name String,
            statement String CODEC(ZSTD(3)),
            request_json String CODEC(ZSTD(3)),
            success UInt8,
            status LowCardinality(String),
            failure_stage LowCardinality(String),
            http_status UInt16,
            error_message String CODEC(ZSTD(3)),
            duration_ms UInt64,
            result_json String CODEC(ZSTD(3)),
            result_row_count UInt32,
            result_truncated UInt8,
            INDEX idx_statement statement TYPE tokenbf_v1(32768, 3, 0) GRANULARITY 4
        )
        ENGINE = ReplacingMergeTree(version)
        PARTITION BY toYYYYMM(created_at)
        ORDER BY (created_at, user_id, event_id)
        TTL created_at + INTERVAL 180 DAY DELETE
        SETTINGS index_granularity = 8192
        """
    )
    _schema_key = schema_key


def build_query_audit_event(user, payload, client_ip="", user_agent=""):
    now = _utc_now()
    payload = dict(payload or {})
    return {
        "event_id": str(uuid4()),
        "version": int(now.timestamp() * 1000),
        "created_at": now,
        "finished_at": None,
        "user_id": int(user.id),
        "username": str(user.username or ""),
        "client_ip": str(client_ip or "")[:128],
        "user_agent": str(user_agent or "")[:1024],
        "execution_id": str(payload.get("execution_id") or ""),
        "db_type": str(payload.get("db_type") or "").lower(),
        "business_line": str(payload.get("business_line") or payload.get("product") or ""),
        "environment": str(payload.get("environment") or ""),
        "cluster_id": int(payload.get("cluster_id") or 0) if str(payload.get("cluster_id") or "").isdigit() else 0,
        "cluster_name": "",
        "instance_id": int(payload.get("instance_id") or 0) if str(payload.get("instance_id") or "").isdigit() else 0,
        "instance_name": "",
        "database_name": str(payload.get("database") or payload.get("mongo_database") or ""),
        "statement": extract_query_statement(payload),
        "request_json": _json_dumps(payload),
        "success": 0,
        "status": "pending",
        "failure_stage": "",
        "http_status": 0,
        "error_message": "",
        "duration_ms": 0,
        "result_json": "",
        "result_row_count": 0,
        "result_truncated": 0,
    }


def extract_query_statement(payload):
    payload = payload or {}
    db_type = str(payload.get("db_type") or "").lower()
    if db_type in {"mysql", "postgresql"}:
        value = payload.get("statement") or payload.get("sql")
    elif db_type == "mongodb":
        value = payload.get("statement") or payload.get("mongo_command") or payload.get("query")
    else:
        value = payload.get("statement") or payload.get("query")
    if isinstance(value, str):
        return value
    return _json_dumps(value) if value is not None else ""


def complete_query_audit_event(event, *, success, http_status, stage="", error="", result=None):
    finished_at = _utc_now()
    event["finished_at"] = finished_at
    event["duration_ms"] = max(0, int((finished_at - event["created_at"]).total_seconds() * 1000))
    event["success"] = 1 if success else 0
    event["status"] = "success" if success else "failed"
    event["failure_stage"] = str(stage or "")
    event["http_status"] = int(http_status or 0)
    event["error_message"] = str(error or "")
    if result is not None:
        event["result_json"] = _json_dumps(result)
        rows = result.get("rows") if isinstance(result, dict) else None
        event["result_row_count"] = len(rows) if isinstance(rows, list) else 0
        event["result_truncated"] = 1 if isinstance(result, dict) and result.get("truncated") else 0
    return event


def enrich_query_audit_target(event, cluster=None, instance=None, database_name=None, execution_id=None):
    if cluster is not None:
        event["cluster_id"] = int(cluster.id or 0)
        event["cluster_name"] = str(cluster.name or "")
        event["business_line"] = event["business_line"] or str(cluster.business_line or cluster.namespace or "")
        event["environment"] = event["environment"] or str(cluster.environment or "")
    if instance is not None:
        event["instance_id"] = int(instance.id or 0)
        event["instance_name"] = str(instance.name or "")
    if database_name is not None:
        event["database_name"] = str(database_name or "")
    if execution_id is not None:
        event["execution_id"] = str(execution_id or "")


def _event_values(event):
    values = dict(event)
    for key in ("user_id", "cluster_id", "instance_id", "http_status", "duration_ms", "result_row_count", "version"):
        values[key] = max(0, int(values.get(key) or 0))
    for key in ("success", "result_truncated"):
        values[key] = 1 if values.get(key) else 0
    return [values.get(column) for column in AUDIT_COLUMNS]


def insert_query_audit_event(event):
    ensure_clickhouse_schema()
    _get_client().insert(_qualified_table(), [_event_values(event)], column_names=AUDIT_COLUMNS)


def _encode_outbox_payload(event):
    serializable = dict(event)
    for key in ("created_at", "finished_at"):
        value = serializable.get(key)
        serializable[key] = value.isoformat() if isinstance(value, datetime) else value
    compressed = zlib.compress(_json_dumps(serializable).encode("utf-8"), level=9)
    return encrypt_secret(base64.b64encode(compressed).decode("ascii")).encode("utf-8")


def _decode_outbox_payload(blob):
    encrypted = bytes(blob or b"").decode("utf-8")
    compressed = base64.b64decode(decrypt_secret(encrypted).encode("ascii"))
    payload = json.loads(zlib.decompress(compressed).decode("utf-8"))
    for key in ("created_at", "finished_at"):
        if payload.get(key):
            payload[key] = datetime.fromisoformat(payload[key])
    return payload


def persist_query_audit_event(event):
    try:
        insert_query_audit_event(event)
        return "clickhouse"
    except Exception as exc:
        current_app.logger.warning("query audit ClickHouse write failed event_id=%s: %s", event.get("event_id"), exc)
        try:
            existing = QueryAuditOutbox.query.filter_by(event_id=event["event_id"]).first()
            if not existing:
                db.session.add(QueryAuditOutbox(
                    event_id=event["event_id"],
                    payload_blob=_encode_outbox_payload(event),
                    attempt_count=0,
                    next_retry_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    last_error=str(exc)[:4000],
                ))
            db.session.commit()
            return "outbox"
        except Exception as outbox_exc:
            db.session.rollback()
            raise QueryAuditUnavailable("查询审计暂时无法持久化") from outbox_exc


def flush_query_audit_outbox(batch_size=100):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = (
        QueryAuditOutbox.query
        .filter(QueryAuditOutbox.next_retry_at <= now)
        .order_by(QueryAuditOutbox.id.asc())
        .limit(max(1, min(int(batch_size or 100), 500)))
        .all()
    )
    synced = 0
    failed = 0
    for row in rows:
        try:
            insert_query_audit_event(_decode_outbox_payload(row.payload_blob))
            db.session.delete(row)
            db.session.commit()
            synced += 1
        except Exception as exc:
            db.session.rollback()
            current = QueryAuditOutbox.query.get(row.id)
            if current:
                current.attempt_count = int(current.attempt_count or 0) + 1
                delay_seconds = min(300, 5 * (2 ** min(current.attempt_count - 1, 6)))
                current.next_retry_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(seconds=delay_seconds)
                current.last_error = str(exc)[:4000]
                db.session.commit()
            failed += 1
            reset_clickhouse_client()
    return {"processed": len(rows), "synced": synced, "failed": failed}


def _rows_as_dicts(result):
    columns = list(getattr(result, "column_names", []) or [])
    return [dict(zip(columns, row)) for row in (getattr(result, "result_rows", []) or [])]


def _history_filters(filters, current_user):
    clauses = []
    params = {}
    if current_user.role != "admin":
        clauses.append("user_id = {current_user_id:UInt64}")
        params["current_user_id"] = int(current_user.id)
    elif filters.get("user_id"):
        clauses.append("user_id = {user_id:UInt64}")
        params["user_id"] = int(filters["user_id"])
    elif filters.get("username"):
        clauses.append("positionCaseInsensitiveUTF8(username, {username:String}) > 0")
        params["username"] = str(filters["username"])
    for key in ("db_type", "business_line", "environment"):
        if filters.get(key):
            clauses.append(f"{key} = {{{key}:String}}")
            params[key] = str(filters[key])
    if filters.get("cluster_id"):
        clauses.append("cluster_id = {cluster_id:UInt64}")
        params["cluster_id"] = int(filters["cluster_id"])
    if filters.get("success") is not None:
        clauses.append("success = {success:UInt8}")
        params["success"] = 1 if filters["success"] else 0
    if filters.get("keyword"):
        clauses.append("positionCaseInsensitiveUTF8(statement, {keyword:String}) > 0")
        params["keyword"] = str(filters["keyword"])
    if filters.get("start_dt"):
        clauses.append("created_at >= {start_dt:DateTime64(3, 'UTC')}")
        params["start_dt"] = filters["start_dt"]
    if filters.get("end_dt"):
        clauses.append("created_at < {end_dt:DateTime64(3, 'UTC')}")
        params["end_dt"] = filters["end_dt"]
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params


def list_query_audits(current_user, page, page_size, filters):
    ensure_clickhouse_schema()
    where_sql, params = _history_filters(filters, current_user)
    client = _get_client()
    count_result = client.query(f"SELECT count() AS total FROM {_qualified_table()} FINAL{where_sql}", parameters=params)
    count_rows = _rows_as_dicts(count_result)
    total = int(count_rows[0]["total"]) if count_rows else 0
    query_params = dict(params)
    query_params.update({"limit": int(page_size), "offset": int((page - 1) * page_size)})
    result = client.query(
        f"SELECT {', '.join(LIST_COLUMNS)} FROM {_qualified_table()} FINAL{where_sql} "
        "ORDER BY created_at DESC LIMIT {limit:UInt32} OFFSET {offset:UInt64}",
        parameters=query_params,
    )
    items = [_format_history_item(row) for row in _rows_as_dicts(result)]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def get_query_audit(current_user, event_id):
    ensure_clickhouse_schema()
    params = {"event_id": str(event_id)}
    user_clause = ""
    if current_user.role != "admin":
        user_clause = " AND user_id = {current_user_id:UInt64}"
        params["current_user_id"] = int(current_user.id)
    result = _get_client().query(
        f"SELECT {', '.join(AUDIT_COLUMNS)} FROM {_qualified_table()} FINAL "
        f"WHERE event_id = {{event_id:UUID}}{user_clause} ORDER BY version DESC LIMIT 1",
        parameters=params,
    )
    rows = _rows_as_dicts(result)
    if not rows:
        return None
    item = _format_history_item(rows[0])
    item["request"] = _json_loads(rows[0].get("request_json"), {})
    item["result"] = _json_loads(rows[0].get("result_json"), None)
    item["client_ip"] = rows[0].get("client_ip") or ""
    item["user_agent"] = rows[0].get("user_agent") or ""
    item["execution_id"] = rows[0].get("execution_id") or ""
    return item


def _format_history_item(row):
    created_at = row.get("created_at")
    finished_at = row.get("finished_at")
    if isinstance(created_at, datetime):
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        created_iso = created_at.isoformat()
        created_cn = created_at.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    else:
        created_iso = str(created_at or "")
        created_cn = created_iso
    return {
        "id": str(row.get("event_id") or ""),
        "event_id": str(row.get("event_id") or ""),
        "user_id": int(row.get("user_id") or 0),
        "username": row.get("username") or "未知用户",
        "db_type": row.get("db_type") or "",
        "business_line": row.get("business_line") or "",
        "environment": row.get("environment") or "",
        "cluster_id": int(row.get("cluster_id") or 0),
        "cluster_name": row.get("cluster_name") or "未知集群",
        "instance_id": int(row.get("instance_id") or 0),
        "instance_name": row.get("instance_name") or "未知实例",
        "database_name": row.get("database_name") or "",
        "statement": row.get("statement") or "",
        "success": bool(row.get("success")),
        "status": row.get("status") or "failed",
        "failure_stage": row.get("failure_stage") or "",
        "http_status": int(row.get("http_status") or 0),
        "error": row.get("error_message") or "",
        "duration_ms": int(row.get("duration_ms") or 0),
        "result_row_count": int(row.get("result_row_count") or 0),
        "result_truncated": bool(row.get("result_truncated")),
        "created_at": created_iso,
        "created_at_cn": created_cn,
        "finished_at": (
            (finished_at if finished_at.tzinfo else finished_at.replace(tzinfo=timezone.utc)).isoformat()
            if isinstance(finished_at, datetime)
            else (str(finished_at) if finished_at else None)
        ),
    }
