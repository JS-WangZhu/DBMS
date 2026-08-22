import re
from datetime import date, datetime
from decimal import Decimal


SENSITIVE_NAME_RE = re.compile(r"(password|passwd|secret|token|private.?key|keyfile|credential)", re.I)


def _json_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {
            str(key): ("******" if SENSITIVE_NAME_RE.search(str(key)) else _json_value(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_json_value(item) for item in value]
    return str(value)


def _item(name, value, **metadata):
    safe_value = "******" if SENSITIVE_NAME_RE.search(str(name)) else _json_value(value)
    item = {"name": str(name), "value": safe_value}
    item.update({key: _json_value(value) for key, value in metadata.items() if value is not None})
    return item


def _mysql(instance, password, timeout):
    import pymysql

    conn = pymysql.connect(
        host=instance.get("resolved_ip") or instance.get("host_input"),
        port=int(instance.get("port") or 3306),
        user=instance.get("username") or "",
        password=password or "",
        connect_timeout=timeout,
        read_timeout=timeout,
        write_timeout=timeout,
        autocommit=True,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute("SHOW GLOBAL VARIABLES")
            return [_item(row[0], row[1], scope="global") for row in cursor.fetchall()]
    finally:
        conn.close()


def _postgresql(instance, password, timeout):
    import psycopg2

    extra = instance.get("extra_json") if isinstance(instance.get("extra_json"), dict) else {}
    conn = psycopg2.connect(
        host=instance.get("resolved_ip") or instance.get("host_input"),
        port=int(instance.get("port") or 5432),
        user=instance.get("username") or "",
        password=password or "",
        dbname=extra.get("database") or extra.get("dbname") or "postgres",
        sslmode=extra.get("sslmode") or "prefer",
        connect_timeout=timeout,
        options=f"-c statement_timeout={max(1, timeout) * 1000}",
    )
    conn.autocommit = True
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT name, setting, unit, vartype, context, source, pending_restart "
                "FROM pg_settings ORDER BY name"
            )
            return [
                _item(row[0], row[1], unit=row[2], value_type=row[3], context=row[4], source=row[5], pending_restart=bool(row[6]))
                for row in cursor.fetchall()
            ]
    finally:
        conn.close()


def _redis(instance, password, timeout):
    import redis

    client = redis.Redis(
        host=instance.get("resolved_ip") or instance.get("host_input"),
        port=int(instance.get("port") or 6379),
        username=instance.get("username") or None,
        password=password or None,
        socket_connect_timeout=timeout,
        socket_timeout=timeout,
        decode_responses=True,
    )
    values = client.config_get("*") or {}
    return [_item(name, value, scope="runtime") for name, value in sorted(values.items())]


def _mongodb(instance, password, timeout):
    from pymongo import MongoClient

    extra = instance.get("extra_json") if isinstance(instance.get("extra_json"), dict) else {}
    client = MongoClient(
        host=instance.get("resolved_ip") or instance.get("host_input"),
        port=int(instance.get("port") or 27017),
        username=instance.get("username") or None,
        password=password or None,
        authSource=extra.get("auth_source") or extra.get("auth_db") or "admin",
        directConnection=True,
        serverSelectionTimeoutMS=timeout * 1000,
        connectTimeoutMS=timeout * 1000,
        socketTimeoutMS=timeout * 1000,
    )
    try:
        values = client.admin.command({"getParameter": "*"})
        values.pop("ok", None)
        return [_item(name, value, scope="runtime") for name, value in sorted(values.items())]
    finally:
        client.close()


def _doris(instance, password, timeout):
    import pymysql

    conn = pymysql.connect(
        host=instance.get("resolved_ip") or instance.get("host_input"),
        port=int(instance.get("port") or 9030),
        user=instance.get("username") or "",
        password=password or "",
        connect_timeout=timeout,
        read_timeout=timeout,
        write_timeout=timeout,
        autocommit=True,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute("SHOW VARIABLES")
            columns = [str(item[0]).lower() for item in cursor.description or []]
            name_idx = columns.index("variable_name") if "variable_name" in columns else 0
            value_idx = columns.index("value") if "value" in columns else 1
            return [_item(row[name_idx], row[value_idx], scope="session") for row in cursor.fetchall()]
    finally:
        conn.close()


COLLECTORS = {
    "mysql": _mysql,
    "postgresql": _postgresql,
    "redis": _redis,
    "mongodb": _mongodb,
    "doris": _doris,
}


def collect_database_parameters(instance, password, timeout_seconds=15):
    db_type = str(instance.get("db_type") or "").lower()
    collector = COLLECTORS.get(db_type)
    if not collector:
        raise ValueError(f"parameter collector not found for {db_type}")
    timeout = max(1, min(int(timeout_seconds or 15), 120))
    return collector(instance, password, timeout)
