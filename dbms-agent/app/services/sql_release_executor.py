import json
import re


class SqlReleaseExecutionError(RuntimeError):
    def __init__(self, message, result):
        super().__init__(message)
        self.result = result


def _extract_mongo_args(command, start_pos):
    depth, index, start, quote, escaped = 1, start_pos, start_pos, None, False
    while index < len(command) and depth > 0:
        char = command[index]
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif quote:
            if char == quote:
                quote = None
        elif char in {"'", '"'}:
            quote = char
        elif char in "{[(":
            depth += 1
        elif char in "}])":
            depth -= 1
            if depth == 0:
                return command[start:index]
        index += 1
    return None


def _split_mongo_args(source):
    args, current, depth, quote, escaped = [], [], 0, None, False
    for char in source:
        if escaped:
            current.append(char); escaped = False; continue
        if char == "\\":
            current.append(char); escaped = True; continue
        if quote:
            current.append(char)
            if char == quote: quote = None
            continue
        if char in {"'", '"'}:
            current.append(char); quote = char; continue
        if char in "{[(": depth += 1
        elif char in "}])": depth = max(0, depth - 1)
        if char == "," and depth == 0:
            args.append("".join(current).strip()); current = []; continue
        current.append(char)
    if current:
        args.append("".join(current).strip())
    return args


def _parse_mongo_shell_command(raw_command):
    command = str(raw_command or "").strip().rstrip(";")
    matched = re.match(r"^db\.([a-zA-Z_][\w]*)\.(insertOne|insertMany|updateOne|updateMany|deleteOne|deleteMany|replaceOne)\(", command, re.I)
    if not matched:
        return None, None, None
    source = _extract_mongo_args(command, matched.end())
    return (matched.group(1), matched.group(2).lower(), _split_mongo_args(source)) if source is not None else (None, None, None)


def _convert_mongo_arg(arg):
    source = str(arg or "").strip()
    if source in {"true", "false"}: return source == "true"
    if source in {"null", "undefined"}: return None
    for converter in (int, float):
        try: return converter(source)
        except ValueError: pass
    try: return json.loads(source)
    except Exception: pass
    normalized = re.sub(r"ObjectId\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", r'{"$oid": "\1"}', source)
    normalized = re.sub(r"([{,]\s*)([a-zA-Z_$][\w$]*)\s*:", r'\1"\2":', normalized)
    normalized = re.sub(r":\s*'([^'\\]*(?:\\.[^'\\]*)*)'", r': "\1"', normalized)
    try: return json.loads(normalized)
    except Exception: return source


def _mongo_to_bson(value):
    try:
        from bson import json_util
        return json_util.loads(json.dumps(value))
    except Exception:
        return value


def _instance_connection(instance):
    return {
        "host": instance.get("resolved_ip") or instance.get("host_input"),
        "port": int(instance.get("port") or 0),
        "user": instance.get("username") or "",
        "password": instance.get("password") or "",
    }


def _execute_mysql(instance, database, statements, timeout_seconds):
    import pymysql

    connection = pymysql.connect(
        **_instance_connection(instance),
        database=database,
        charset="utf8mb4",
        connect_timeout=5,
        read_timeout=timeout_seconds,
        write_timeout=timeout_seconds,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
    results, total = [], 0
    try:
        with connection.cursor() as cursor:
            for line, statement in enumerate(statements, start=1):
                try:
                    cursor.execute(statement)
                    affected = int(cursor.rowcount or 0)
                    connection.commit()
                    total += max(affected, 0)
                    results.append({"line": line, "sql": statement, "status": "success", "affected_rows": affected, "backup_rows": 0})
                except Exception as exc:
                    connection.rollback()
                    results.append({"line": line, "sql": statement, "status": "failed", "error": str(exc), "backup_rows": 0})
                    raise SqlReleaseExecutionError(str(exc), {"affected_rows": total, "statement_count": len(results), "statements": results}) from exc
    finally:
        connection.close()
    return {"rows": [], "affected_rows": total, "statement_count": len(results), "statements": results}


def _execute_postgresql(instance, database, statements, timeout_seconds):
    import psycopg2

    extra = instance.get("extra_json") if isinstance(instance.get("extra_json"), dict) else {}
    connection = psycopg2.connect(
        host=instance.get("resolved_ip") or instance.get("host_input"),
        port=int(instance.get("port") or 5432),
        user=instance.get("username") or "",
        password=instance.get("password") or "",
        dbname=database,
        sslmode=extra.get("sslmode") or "prefer",
        connect_timeout=5,
        options=f"-c statement_timeout={max(1, int(timeout_seconds)) * 1000}",
    )
    results, total = [], 0
    try:
        with connection.cursor() as cursor:
            for line, statement in enumerate(statements, start=1):
                try:
                    cleaned = re.sub(
                        r"^\s*(?:(?:--[^\n]*(?:\n|$))|(?:/\*.*?\*/\s*))*",
                        "",
                        str(statement or ""),
                        flags=re.S,
                    )
                    non_transactional = bool(re.match(
                        r"^CREATE\s+(?:UNIQUE\s+)?INDEX\s+CONCURRENTLY\b",
                        cleaned,
                        flags=re.I,
                    ))
                    if non_transactional:
                        connection.commit()
                        connection.autocommit = True
                    cursor.execute(statement)
                    affected = int(cursor.rowcount or 0)
                    connection.commit()
                    if non_transactional:
                        connection.autocommit = False
                    total += max(affected, 0)
                    results.append({"line": line, "sql": statement, "status": "success", "affected_rows": affected, "backup_rows": 0})
                except Exception as exc:
                    connection.rollback()
                    results.append({"line": line, "sql": statement, "status": "failed", "error": str(exc), "backup_rows": 0})
                    raise SqlReleaseExecutionError(str(exc), {"affected_rows": total, "statement_count": len(results), "statements": results}) from exc
    finally:
        connection.close()
    return {"rows": [], "affected_rows": total, "statement_count": len(results), "statements": results}


def _execute_mongodb(instance, database, statements, timeout_seconds):
    from pymongo import MongoClient

    target = instance.get("seed_nodes") or (instance.get("resolved_ip") or instance.get("host_input"))
    port = None if instance.get("seed_nodes") else int(instance.get("port") or 27017)
    extra = instance.get("extra_json") if isinstance(instance.get("extra_json"), dict) else {}
    client = MongoClient(
        target, port, username=instance.get("username") or None, password=instance.get("password") or None,
        authSource=extra.get("auth_source") or extra.get("auth_db") or "admin", directConnection=False,
        serverSelectionTimeoutMS=5000, connectTimeoutMS=5000,
        socketTimeoutMS=max(1, int(timeout_seconds)) * 1000, appname="dbms-agent-sql-release",
    )
    results, total = [], 0
    try:
        handle = client.get_database(database)
        for line, statement in enumerate(statements, start=1):
            try:
                collection_name, operation, args = _parse_mongo_shell_command(statement)
                if not collection_name or not args:
                    raise ValueError("invalid MongoDB release statement")
                parsed = [_mongo_to_bson(_convert_mongo_arg(item)) for item in args]
                collection = handle.get_collection(collection_name)
                options_index = 1 if operation in {"deleteone", "deletemany"} else 2
                options = parsed[options_index] if len(parsed) > options_index and isinstance(parsed[options_index], dict) else {}
                if operation not in {"insertone", "insertmany"} and (not isinstance(parsed[0], dict) or not parsed[0]):
                    raise ValueError("MongoDB UPDATE/DELETE/REPLACE requires a non-empty filter")
                if options.get("upsert"):
                    raise ValueError("MongoDB release does not support upsert")
                if operation == "insertone": result = collection.insert_one(parsed[0]); affected = 1
                elif operation == "insertmany": result = collection.insert_many(list(parsed[0])); affected = len(result.inserted_ids)
                elif operation == "updateone": result = collection.update_one(parsed[0], parsed[1], **options); affected = result.modified_count
                elif operation == "updatemany": result = collection.update_many(parsed[0], parsed[1], **options); affected = result.modified_count
                elif operation == "deleteone": result = collection.delete_one(parsed[0], **options); affected = result.deleted_count
                elif operation == "deletemany": result = collection.delete_many(parsed[0], **options); affected = result.deleted_count
                elif operation == "replaceone": result = collection.replace_one(parsed[0], parsed[1], **options); affected = result.modified_count
                else: raise ValueError("unsupported MongoDB release operation")
                total += int(affected or 0)
                results.append({"line": line, "sql": statement, "status": "success", "affected_rows": int(affected or 0), "backup_rows": 0})
            except Exception as exc:
                results.append({"line": line, "sql": statement, "status": "failed", "error": str(exc), "backup_rows": 0})
                raise SqlReleaseExecutionError(str(exc), {"affected_rows": total, "statement_count": len(results), "statements": results}) from exc
    finally:
        client.close()
    return {"rows": [], "affected_rows": total, "statement_count": len(results), "statements": results}


def execute_sql_release(instance, database, statements, db_type, timeout_seconds=86400):
    if not isinstance(instance, dict) or not instance.get("username"):
        raise ValueError("database execution user is required")
    if not database or not isinstance(statements, list) or not statements:
        raise ValueError("database and statements are required")
    normalized = str(db_type or "").strip().lower()
    if normalized == "mysql":
        return _execute_mysql(instance, database, statements, timeout_seconds)
    if normalized == "postgresql":
        return _execute_postgresql(instance, database, statements, timeout_seconds)
    if normalized == "mongodb":
        return _execute_mongodb(instance, database, statements, timeout_seconds)
    raise ValueError("unsupported database type")
