import json
import re
from datetime import datetime
from pathlib import Path

from flask import current_app

from app.models.ai_config import AIModelConfig
from app.services.ai_service import get_mysql_metadata
from app.utils.crypto import decrypt_secret, encrypt_secret


def split_sql_statements(sql_text):
    statements, current = [], []
    quote = None
    escaped = False
    for char in str(sql_text or ""):
        if quote:
            current.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
            current.append(char)
        elif char == ";":
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
        else:
            current.append(char)
    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def _extract_json(text):
    source = str(text or "").strip()
    source = re.sub(r"^```(?:json)?\s*|\s*```$", "", source, flags=re.I)
    try:
        return json.loads(source)
    except Exception:
        match = re.search(r"\{.*\}", source, flags=re.S)
        if not match:
            raise ValueError("AI 初审未返回可解析的 JSON")
        return json.loads(match.group(0))


def review_release(instance, database, statements, db_type="mysql", progress_callback=None):
    config = AIModelConfig.query.filter_by(is_default=True, enabled=True).first()
    if not config:
        config = AIModelConfig.query.filter_by(enabled=True).first()
    if not config:
        raise ValueError("未配置可用的 AI 模型，无法提交上线申请")
    normalized_type = str(db_type or "mysql").lower()
    if normalized_type == "mysql":
        metadata = get_mysql_metadata(instance, database)
        compact_metadata = {
            "database": database,
            "tables": [{
                "table_name": item.get("table_name"), "rows": item.get("rows"),
                "data_size_mb": item.get("data_size_mb"), "create_sql": item.get("create_sql"),
                "indexes": item.get("indexes"),
            } for item in metadata.get("tables", [])],
        }
    elif normalized_type == "mongodb":
        from app.services.data_access import list_mongo_collections
        compact_metadata = list_mongo_collections(instance, database)
    elif normalized_type == "postgresql":
        from app.services.postgresql_backup import list_objects
        password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
        compact_metadata = list_objects(instance, password, database)
    else:
        raise ValueError("不支持的数据库类型")
    engine_name = {"mysql": "MySQL", "mongodb": "MongoDB", "postgresql": "PostgreSQL"}[normalized_type]
    api_url = (config.api_url or "").strip()
    if api_url.endswith("/v1") or api_url.endswith("/v1/"):
        api_url = api_url.rstrip("/") + "/chat/completions"
    import requests

    reviews = []
    for index, sql in enumerate(statements, start=1):
        prompt = f"""
你是数据库上线审核员。请结合元数据审核下面第 {index} 条 {engine_name} 变更语句，独立给出是否通过。
禁止无过滤条件的批量修改或删除、明显语法错误、危险全库或全表操作；有锁表、全表扫描、不可回滚风险时应不通过。
只返回 JSON，不要 Markdown：
{{"summary":"本条结论","items":[{{"line":{index},"passed":true,"risk_level":"low|medium|high","reason":"原因","suggestion":"修改建议"}}]}}
items 必须只包含当前这一条，line 必须为 {index}。
元数据：{json.dumps(compact_metadata, ensure_ascii=False, default=str)}
语句：{json.dumps([{"line": index, "sql": sql}], ensure_ascii=False)}
"""
        response = requests.post(
            api_url,
            headers={"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"},
            json={
                "model": config.model_name,
                "messages": [
                    {"role": "system", "content": f"你是严谨的 {engine_name} DBA，只输出合法 JSON。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0,
            },
            timeout=90,
        )
        response.raise_for_status()
        content = response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        parsed = _extract_json(content)
        raw_items = parsed.get("items") if isinstance(parsed, dict) else None
        if not isinstance(raw_items, list) or len(raw_items) != 1 or not isinstance(raw_items[0], dict):
            raise ValueError(f"AI 初审未返回第 {index} 条语句的完整结果")
        item = raw_items[0]
        try:
            reviewed_line = int(item.get("line", 0))
        except (TypeError, ValueError):
            reviewed_line = 0
        if reviewed_line != index:
            raise ValueError(f"AI 初审返回的第 {index} 条语句编号不匹配")
        review = {
            "line": index,
            "sql": sql,
            "passed": item.get("passed") is True,
            "risk_level": str(item.get("risk_level") or "high").lower(),
            "reason": str(item.get("reason") or "未提供原因"),
            "suggestion": str(item.get("suggestion") or ""),
            "status": "completed",
        }
        reviews.append(review)
        if progress_callback:
            progress_callback(review, len(statements))

    passed_count = sum(1 for item in reviews if item["passed"])
    return reviews, f"AI 初审完成：{passed_count}/{len(reviews)} 条通过"


_IDENTIFIER = r"(?:`[^`]+`|[A-Za-z_][A-Za-z0-9_$]*)(?:\.(?:`[^`]+`|[A-Za-z_][A-Za-z0-9_$]*))?"
_SIMPLE_IDENTIFIER = r"(?:`[^`]+`|[A-Za-z_][A-Za-z0-9_$]*)"


class PartialRollbackExecutionError(RuntimeError):
    def __init__(self, message, rollback_path=None):
        super().__init__(message)
        self.rollback_path = rollback_path


class ReleaseRollbackExecutionError(RuntimeError):
    def __init__(self, message, line=None):
        super().__init__(message)
        self.line = line


def _update_release_statement_status(release_id, line, statement, status, **extra):
    from app.extensions import db
    from app.models.sql_release import SqlRelease

    release = db.session.get(SqlRelease, release_id)
    if not release:
        return
    payload = dict(release.execution_result_json or {})
    statements = [dict(item) for item in (payload.get("statements") or [])]
    current = next((item for item in statements if int(item.get("line") or 0) == line), None)
    if current is None:
        current = {"line": line, "sql": statement}
        statements.append(current)
    current.update({"sql": statement, "status": status, **extra})
    statements.sort(key=lambda item: int(item.get("line") or 0))
    payload["statements"] = statements
    release.execution_result_json = payload
    db.session.commit()


def _quote_identifier(value):
    return "`" + str(value or "").replace("`", "``") + "`"


def _unquote_identifier(value):
    return str(value or "").strip().strip("`")


def _normalize_table_ref(raw, database):
    parts = [_unquote_identifier(item) for item in str(raw or "").split(".")]
    if len(parts) == 2:
        if parts[0] != database:
            raise ValueError("部分回滚不允许跨目标库执行")
        table = parts[1]
    elif len(parts) == 1:
        table = parts[0]
    else:
        raise ValueError("无法识别 DML 表名")
    if not table:
        raise ValueError("无法识别 DML 表名")
    return table, f"{_quote_identifier(database)}.{_quote_identifier(table)}"


def _split_top_level(source, delimiter=","):
    result, current = [], []
    quote = None
    escaped = False
    depth = 0
    for char in str(source or ""):
        if quote:
            current.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
            current.append(char)
        elif char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth -= 1
            current.append(char)
        elif char == delimiter and depth == 0:
            result.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if quote or depth != 0:
        raise ValueError("SQL 引号或括号不完整，无法生成回滚文件")
    tail = "".join(current).strip()
    if tail:
        result.append(tail)
    return result


def _extract_value_tuples(source):
    tuples = []
    current = []
    quote = None
    escaped = False
    depth = 0
    for char in str(source or "").strip():
        if quote:
            current.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            current.append(char)
        elif char == "(":
            if depth > 0:
                current.append(char)
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                raise ValueError("INSERT VALUES 括号不完整")
            if depth == 0:
                tuples.append(_split_top_level("".join(current)))
                current = []
            else:
                current.append(char)
        elif depth == 0:
            if char not in {",", " ", "\t", "\r", "\n"}:
                raise ValueError("仅支持 INSERT/REPLACE ... VALUES 形式生成回滚 SQL")
        else:
            current.append(char)
    if quote or depth != 0 or not tuples:
        raise ValueError("无法解析 INSERT/REPLACE VALUES")
    return tuples


def _primary_key_columns(cursor, quoted_table):
    cursor.execute(f"SHOW KEYS FROM {quoted_table} WHERE Key_name='PRIMARY' ORDER BY Seq_in_index")
    columns = [row.get("Column_name") for row in cursor.fetchall() or [] if row.get("Column_name")]
    return columns


def _fetch_rows(cursor, sql, max_rows):
    cursor.execute(sql)
    rows = cursor.fetchmany(max_rows + 1) or []
    if len(rows) > max_rows:
        raise ValueError(f"受影响记录超过 {max_rows} 行，拒绝生成超大回滚文件")
    return rows


def _literal(connection, value):
    escaped = connection.escape(value)
    return escaped.decode("utf-8") if isinstance(escaped, bytes) else str(escaped)


def _restore_rows_sql(connection, quoted_table, rows, use_upsert=True):
    statements = []
    for row in rows:
        columns = list(row.keys())
        column_sql = ", ".join(_quote_identifier(item) for item in columns)
        values_sql = ", ".join(_literal(connection, row[item]) for item in columns)
        statement = f"INSERT INTO {quoted_table} ({column_sql}) VALUES ({values_sql})"
        if use_upsert:
            updates_sql = ", ".join(
                f"{_quote_identifier(item)}=VALUES({_quote_identifier(item)})" for item in columns
            )
            statement += f" ON DUPLICATE KEY UPDATE {updates_sql}"
        statements.append(statement + ";")
    return statements


def _mysql_row_condition(connection, row, columns=None):
    selected = columns or list(row.keys())
    return "(" + " AND ".join(
        f"{_quote_identifier(column)} <=> {_literal(connection, row[column])}"
        for column in selected
    ) + ")"


def _parse_update(statement, database):
    match = re.match(rf"^\s*UPDATE\s+(?P<table>{_IDENTIFIER})\s+SET\s+(?P<body>.+)$", statement, flags=re.I | re.S)
    if not match:
        return None
    body = match.group("body")
    where_match = re.search(r"\s+WHERE\s+", body, flags=re.I)
    if not where_match:
        raise ValueError("UPDATE 缺少 WHERE 条件，无法进行部分备份")
    set_clause = body[:where_match.start()].strip()
    where_clause = body[where_match.end():].strip()
    if not set_clause or not where_clause:
        raise ValueError("UPDATE 语句不完整")
    table, quoted_table = _normalize_table_ref(match.group("table"), database)
    return {"kind": "update", "table": table, "quoted_table": quoted_table, "set": set_clause, "where": where_clause}


def _parse_delete(statement, database):
    match = re.match(rf"^\s*DELETE\s+FROM\s+(?P<table>{_IDENTIFIER})\s+WHERE\s+(?P<where>.+)$", statement, flags=re.I | re.S)
    if not match:
        return None
    table, quoted_table = _normalize_table_ref(match.group("table"), database)
    return {"kind": "delete", "table": table, "quoted_table": quoted_table, "where": match.group("where").strip()}


def _parse_insert(statement, database):
    match = re.match(
        rf"^\s*(?P<kind>INSERT(?:\s+IGNORE)?|REPLACE)\s+INTO\s+(?P<table>{_IDENTIFIER})\s*"
        r"(?:\((?P<columns>[^)]+)\)\s*)?VALUES\s*(?P<values>.+)$",
        statement,
        flags=re.I | re.S,
    )
    if not match:
        return None
    values_source = re.split(r"\s+ON\s+DUPLICATE\s+KEY\s+UPDATE\s+", match.group("values"), maxsplit=1, flags=re.I)[0].strip()
    columns = (
        [_unquote_identifier(item) for item in _split_top_level(match.group("columns"))]
        if match.group("columns")
        else None
    )
    value_tuples = _extract_value_tuples(values_source)
    if columns and any(len(values) != len(columns) for values in value_tuples):
        raise ValueError("INSERT/REPLACE 列数和值数量不一致")
    table, quoted_table = _normalize_table_ref(match.group("table"), database)
    return {"kind": "insert", "table": table, "quoted_table": quoted_table, "columns": columns, "values": value_tuples}


def _analyze_dml(statement, database):
    cleaned = str(statement or "").strip()
    while True:
        updated = re.sub(r"^(?:\s*(?:--[^\n]*(?:\n|$)|#[^\n]*(?:\n|$)|/\*.*?\*/))", "", cleaned, count=1, flags=re.S)
        if updated == cleaned:
            break
        cleaned = updated.strip()
    keyword_match = re.match(r"^\s*([A-Za-z]+)", cleaned)
    keyword = keyword_match.group(1).lower() if keyword_match else ""
    if keyword == "update":
        parsed = _parse_update(cleaned, database)
    elif keyword == "delete":
        parsed = _parse_delete(cleaned, database)
    elif keyword in {"insert", "replace"}:
        parsed = _parse_insert(cleaned, database)
    elif keyword == "alter":
        match = re.match(
            rf"^\s*ALTER\s+TABLE\s+(?P<table>{_IDENTIFIER})\s+ADD\s+(?:COLUMN\s+)?"
            rf"(?!(?:COLUMN|CONSTRAINT|PRIMARY|UNIQUE|CHECK|FOREIGN|IF)\b)"
            rf"(?P<column>{_SIMPLE_IDENTIFIER})\s+(?P<definition>.+)$",
            cleaned,
            flags=re.I | re.S,
        )
        if not match or len(_split_top_level(match.group("definition"))) != 1:
            raise ValueError("暂仅支持单列 ALTER TABLE ... ADD COLUMN 生成 MySQL 回滚 SQL")
        table, quoted_table = _normalize_table_ref(match.group("table"), database)
        parsed = {
            "kind": "add_column",
            "table": table,
            "quoted_table": quoted_table,
            "column": _unquote_identifier(match.group("column")),
        }
    elif keyword == "truncate":
        raise ValueError("TRUNCATE 无法进行部分行备份，请改用带 WHERE 的 DELETE")
    elif keyword == "with" and re.search(r"\b(insert|update|delete|replace)\b", cleaned, flags=re.I):
        raise ValueError("暂不支持 WITH DML 生成安全回滚 SQL，请改写为普通 DML")
    elif keyword in {"call", "load"}:
        raise ValueError(f"{keyword.upper()} 可能修改数据，无法生成可靠的部分回滚 SQL")
    else:
        return None
    if not parsed:
        raise ValueError(f"暂不支持该 {keyword.upper()} 写法生成安全回滚 SQL")
    return parsed


def _rollback_for_dml(connection, cursor, parsed, max_rows):
    quoted_table = parsed["quoted_table"]
    primary_keys = _primary_key_columns(cursor, quoted_table)
    if parsed["kind"] in {"update", "delete"}:
        if parsed["kind"] == "update":
            assigned_columns = {
                _unquote_identifier(item.split("=", 1)[0].split(".")[-1]).lower()
                for item in _split_top_level(parsed["set"])
                if "=" in item
            }
            if assigned_columns.intersection(item.lower() for item in primary_keys):
                raise ValueError("UPDATE 修改了主键，无法生成可靠的部分回滚 SQL")
        select_sql = f"SELECT * FROM {quoted_table} WHERE {parsed['where']} FOR UPDATE"
        if primary_keys:
            rows = _fetch_rows(cursor, select_sql, max_rows)
        else:
            cursor.execute(select_sql)
            rows = cursor.fetchall() or []
        if primary_keys:
            rollback = _restore_rows_sql(connection, quoted_table, rows)
        elif parsed["kind"] == "delete":
            rollback = _restore_rows_sql(connection, quoted_table, rows, use_upsert=False)
        else:
            assigned_columns = {
                _unquote_identifier(item.split("=", 1)[0].split(".")[-1]).lower()
                for item in _split_top_level(parsed["set"])
                if "=" in item
            }
            stable_columns = [column for column in (rows[0].keys() if rows else []) if column.lower() not in assigned_columns]
            conditions = [_mysql_row_condition(connection, row, stable_columns) for row in rows] if stable_columns else []
            rollback = [f"DELETE FROM {quoted_table} WHERE {condition} LIMIT 1;" for condition in conditions]
            if rows and not rollback:
                rollback = [f"DELETE FROM {quoted_table} WHERE {parsed['where']};"]
            rollback.extend(_restore_rows_sql(connection, quoted_table, rows, use_upsert=False))
        return rollback, len(rows), rows

    columns = parsed["columns"]
    if not columns:
        cursor.execute(f"SHOW COLUMNS FROM {quoted_table}")
        columns = [row.get("Field") for row in cursor.fetchall() or [] if row.get("Field")]
        if not columns:
            raise ValueError("无法读取 MySQL 目标表字段，不能安全生成回滚 SQL")
    if any(len(values) != len(columns) for values in parsed["values"]):
        raise ValueError("INSERT/REPLACE 列数和值数量不一致")
    positions = {column.lower(): index for index, column in enumerate(columns)}
    key_columns = primary_keys or columns
    missing = [column for column in key_columns if column.lower() not in positions]
    if missing:
        raise ValueError("INSERT/REPLACE 必须显式提供全部主键值才能生成回滚 SQL")
    conditions = []
    for values in parsed["values"]:
        key_parts = []
        for column in key_columns:
            raw_value = values[positions[column.lower()]].strip()
            if not re.match(
                r"^(?:NULL|TRUE|FALSE|-?\d+(?:\.\d+)?|0x[0-9A-F]+|X'[0-9A-F]+'|'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\")$",
                raw_value,
                flags=re.I | re.S,
            ):
                raise ValueError("INSERT/REPLACE 主键必须是明确的字面量")
            key_parts.append(f"{_quote_identifier(column)} <=> {raw_value}")
        conditions.append("(" + " AND ".join(key_parts) + ")")
    where = " OR ".join(conditions)
    select_sql = f"SELECT * FROM {quoted_table} WHERE {where} FOR UPDATE"
    if primary_keys:
        previous_rows = _fetch_rows(cursor, select_sql, max_rows)
    else:
        cursor.execute(select_sql)
        previous_rows = cursor.fetchall() or []
    rollback = [f"DELETE FROM {quoted_table} WHERE {where};"]
    rollback.extend(_restore_rows_sql(connection, quoted_table, previous_rows, use_upsert=bool(primary_keys)))
    return rollback, len(parsed["values"]), previous_rows


def _persist_release_rollback_backup(release_id, line, db_type, database, parsed, rows, rollback_sql):
    from app.extensions import db
    from app.models.sql_release import SqlRelease, SqlReleaseRollbackBackup

    if not db.session.get(SqlRelease, release_id):
        return
    record = SqlReleaseRollbackBackup.query.filter_by(
        release_id=release_id,
        statement_line=line,
    ).first()
    if not record:
        record = SqlReleaseRollbackBackup(release_id=release_id, statement_line=line)
    serializable_rows = [dict(row) for row in (rows or [])]
    record.db_type = db_type
    record.database_name = database
    record.table_name = parsed.get("quoted_table") if parsed else None
    record.operation = parsed.get("kind") if parsed else "statement"
    record.row_count = len(serializable_rows)
    record.rows_encrypted = encrypt_secret(json.dumps(serializable_rows, ensure_ascii=False, default=str))
    record.rollback_sql_encrypted = encrypt_secret("\n".join(rollback_sql or []))
    db.session.add(record)
    db.session.commit()


def _write_rollback_file(output_path, release_id, database, rollback_groups):
    lines = [
        f"-- SQL release #{release_id} partial rollback",
        f"-- database: {database}",
        f"-- generated_at: {datetime.now().isoformat(timespec='seconds')}",
        "SET NAMES utf8mb4;",
        "SET FOREIGN_KEY_CHECKS=0;",
        "START TRANSACTION;",
    ]
    for group in reversed(rollback_groups):
        lines.extend(group)
    lines.extend(["COMMIT;", "SET FOREIGN_KEY_CHECKS=1;", ""])
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    with temp_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines))
        handle.flush()
    temp_path.replace(output_path)


def execute_mysql_with_partial_rollback(instance, database, statements, release_id, timeout_seconds=86400):
    import pymysql

    backup_root = Path(current_app.config.get("SQL_RELEASE_BACKUP_DIR") or "data/sql_release_backups").resolve()
    backup_root.mkdir(parents=True, exist_ok=True)
    output_path = backup_root / f"release_{release_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_rollback.sql"
    max_rows = max(1, int(current_app.config.get("SQL_RELEASE_ROLLBACK_MAX_ROWS", 10000)))
    password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
    connection = pymysql.connect(
        host=instance.resolved_ip or instance.host_input,
        port=instance.port,
        user=instance.username,
        password=password,
        database=database,
        charset="utf8mb4",
        connect_timeout=5,
        read_timeout=timeout_seconds,
        write_timeout=timeout_seconds,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )
    rollback_groups = []
    statement_results = []
    total_affected = 0
    try:
        with connection.cursor() as cursor:
            for line, statement in enumerate(statements, start=1):
                phase = "backing_up"
                _update_release_statement_status(release_id, line, statement, phase)
                try:
                    parsed = _analyze_dml(statement, database)
                    if not parsed:
                        raise ValueError("暂不支持该语句生成可靠回滚 SQL，已阻止执行")
                    if parsed["kind"] == "add_column":
                        rollback_sql = [
                            f"ALTER TABLE {parsed['quoted_table']} DROP COLUMN {_quote_identifier(parsed['column'])};"
                        ]
                        backup_rows = 0
                        backed_up_rows = []
                    else:
                        rollback_sql, backup_rows, backed_up_rows = _rollback_for_dml(
                            connection, cursor, parsed, max_rows
                        )
                    _persist_release_rollback_backup(
                        release_id, line, "mysql", database, parsed, backed_up_rows, rollback_sql
                    )
                    rollback_groups.append([f"-- rollback for statement #{line}", *rollback_sql])
                    _write_rollback_file(output_path, release_id, database, rollback_groups)
                    phase = "backup_ready"
                    _update_release_statement_status(
                        release_id, line, statement, phase,
                        backup_rows=backup_rows,
                    )
                    phase = "executing"
                    _update_release_statement_status(release_id, line, statement, phase)
                    cursor.execute(statement)
                    affected = cursor.rowcount
                    connection.commit()
                    total_affected += affected if isinstance(affected, int) and affected > 0 else 0
                    result_item = {
                        "line": line,
                        "sql": statement,
                        "status": "success",
                        "affected_rows": affected,
                        "backup_rows": backup_rows,
                    }
                    statement_results.append(result_item)
                    _update_release_statement_status(release_id, line, statement, "success", **{
                        key: value for key, value in result_item.items() if key not in {"line", "sql", "status"}
                    })
                except Exception as statement_exc:
                    connection.rollback()
                    failed_status = "backup_failed" if phase in {"backing_up", "backup_ready"} else "failed"
                    _update_release_statement_status(
                        release_id, line, statement, failed_status, error=str(statement_exc)
                    )
                    raise
    except Exception as exc:
        connection.rollback()
        if not rollback_groups:
            output_path.unlink(missing_ok=True)
        raise PartialRollbackExecutionError(
            str(exc) or "SQL execution failed",
            str(output_path) if rollback_groups and output_path.exists() else None,
        ) from exc
    finally:
        connection.close()
    return {
        "columns": [],
        "rows": [],
        "affected_rows": total_affected,
        "statement_count": len(statement_results),
        "statements": statement_results,
    }, (str(output_path) if rollback_groups else None)


_PG_IDENTIFIER = r'(?:"[^"]+"|[A-Za-z_][A-Za-z0-9_$]*)(?:\.(?:"[^"]+"|[A-Za-z_][A-Za-z0-9_$]*))?'
_PG_SIMPLE_IDENTIFIER = r'(?:"[^"]+"|[A-Za-z_][A-Za-z0-9_$]*)'


def _pg_unquote(value):
    return str(value or "").strip().strip('"').replace('""', '"')


def _pg_quote(value):
    return '"' + str(value or "").replace('"', '""') + '"'


def _pg_table_ref(raw):
    parts = [_pg_unquote(item) for item in str(raw or "").split(".")]
    if len(parts) == 1:
        schema, table = "public", parts[0]
    elif len(parts) == 2:
        schema, table = parts
    else:
        raise ValueError("无法识别 PostgreSQL 表名")
    return schema, table, f"{_pg_quote(schema)}.{_pg_quote(table)}"


def _analyze_postgresql_dml(statement):
    cleaned = str(statement or "").strip()
    keyword_match = re.match(r"^\s*([A-Za-z]+)", cleaned)
    keyword = keyword_match.group(1).lower() if keyword_match else ""
    if keyword == "truncate":
        raise ValueError("TRUNCATE 无法生成部分回滚 SQL，请改用带 WHERE 的 DELETE")
    if keyword == "with" and re.search(r"\b(insert|update|delete)\b", cleaned, flags=re.I):
        raise ValueError("暂不支持 PostgreSQL WITH DML 生成安全回滚 SQL")
    if keyword == "update":
        match = re.match(rf"^\s*UPDATE\s+(?P<table>{_PG_IDENTIFIER})\s+SET\s+(?P<body>.+)$", cleaned, flags=re.I | re.S)
        if not match:
            raise ValueError("暂不支持该 PostgreSQL UPDATE 写法")
        where_match = re.search(r"\s+WHERE\s+", match.group("body"), flags=re.I)
        if not where_match:
            raise ValueError("UPDATE 缺少 WHERE 条件，无法进行部分备份")
        schema, table, quoted = _pg_table_ref(match.group("table"))
        where_clause = re.split(r"\s+RETURNING\b", match.group("body")[where_match.end():], maxsplit=1, flags=re.I)[0].strip()
        return {"kind": "update", "schema": schema, "table": table, "quoted_table": quoted,
                "set": match.group("body")[:where_match.start()].strip(),
                "where": where_clause}
    if keyword == "delete":
        match = re.match(rf"^\s*DELETE\s+FROM\s+(?P<table>{_PG_IDENTIFIER})\s+WHERE\s+(?P<where>.+)$", cleaned, flags=re.I | re.S)
        if not match:
            raise ValueError("DELETE 缺少 WHERE 条件或写法暂不支持")
        schema, table, quoted = _pg_table_ref(match.group("table"))
        where_clause = re.split(r"\s+RETURNING\b", match.group("where"), maxsplit=1, flags=re.I)[0].strip()
        return {"kind": "delete", "schema": schema, "table": table, "quoted_table": quoted, "where": where_clause}
    if keyword == "insert":
        match = re.match(
            rf"^\s*INSERT\s+INTO\s+(?P<table>{_PG_IDENTIFIER})\s*"
            rf"(?:\((?P<columns>[^)]+)\)\s*)?VALUES\s*(?P<values>.+)$",
            cleaned,
            flags=re.I | re.S,
        )
        if not match:
            raise ValueError("PostgreSQL INSERT 必须使用 VALUES 才能生成回滚 SQL")
        values_source = re.split(r"\s+(?:ON\s+CONFLICT|RETURNING)\b", match.group("values"), maxsplit=1, flags=re.I)[0].strip()
        schema, table, quoted = _pg_table_ref(match.group("table"))
        columns = (
            [_pg_unquote(item) for item in _split_top_level(match.group("columns"))]
            if match.group("columns")
            else None
        )
        values = _extract_value_tuples(values_source)
        if columns and any(len(row) != len(columns) for row in values):
            raise ValueError("PostgreSQL INSERT 列数和值数量不一致")
        return {"kind": "insert", "schema": schema, "table": table, "quoted_table": quoted, "columns": columns, "values": values}
    if keyword == "alter":
        match = re.match(
            rf"^\s*ALTER\s+TABLE\s+(?P<table>{_PG_IDENTIFIER})\s+ADD\s+(?:COLUMN\s+)?"
            rf"(?!(?:COLUMN|CONSTRAINT|PRIMARY|UNIQUE|CHECK|FOREIGN|IF)\b)"
            rf"(?P<column>{_PG_SIMPLE_IDENTIFIER})\s+(?P<definition>.+)$",
            cleaned,
            flags=re.I | re.S,
        )
        if not match or len(_split_top_level(match.group("definition"))) != 1:
            raise ValueError("暂仅支持单列 ALTER TABLE ... ADD COLUMN 生成 PostgreSQL 回滚 SQL")
        schema, table, quoted = _pg_table_ref(match.group("table"))
        return {
            "kind": "add_column",
            "schema": schema,
            "table": table,
            "quoted_table": quoted,
            "column": _pg_unquote(match.group("column")),
        }
    return None


def _pg_primary_keys(cursor, schema, table):
    cursor.execute(
        "SELECT a.attname FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "JOIN unnest(i.indkey) WITH ORDINALITY AS k(attnum, ord) ON TRUE "
        "JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=k.attnum "
        "WHERE i.indisprimary AND n.nspname=%s AND c.relname=%s ORDER BY k.ord",
        (schema, table),
    )
    keys = [row.get("attname") for row in cursor.fetchall() if row.get("attname")]
    return keys


def _pg_table_columns(cursor, schema, table):
    cursor.execute(
        "SELECT a.attname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
        "JOIN pg_attribute a ON a.attrelid=c.oid "
        "WHERE n.nspname=%s AND c.relname=%s AND a.attnum > 0 AND NOT a.attisdropped "
        "ORDER BY a.attnum",
        (schema, table),
    )
    columns = [row.get("attname") for row in cursor.fetchall() if row.get("attname")]
    if not columns:
        raise ValueError("无法读取 PostgreSQL 目标表字段，不能安全生成回滚 SQL")
    return columns


def _pg_restore_rows(cursor, quoted_table, primary_keys, rows):
    result = []
    for row in rows:
        columns = list(row.keys())
        values = cursor.mogrify("(" + ",".join(["%s"] * len(columns)) + ")", [row[item] for item in columns]).decode()
        statement = f"INSERT INTO {quoted_table} ({', '.join(_pg_quote(item) for item in columns)}) VALUES {values}"
        if primary_keys:
            updates = ", ".join(f"{_pg_quote(item)}=EXCLUDED.{_pg_quote(item)}" for item in columns)
            statement += (
                f" ON CONFLICT ({', '.join(_pg_quote(item) for item in primary_keys)}) "
                f"DO UPDATE SET {updates}"
            )
        result.append(statement + ";")
    return result


def _pg_row_condition(cursor, row, columns=None):
    selected = columns or list(row.keys())
    return "(" + " AND ".join(
        f"{_pg_quote(column)} IS NOT DISTINCT FROM {cursor.mogrify('%s', [row[column]]).decode()}"
        for column in selected
    ) + ")"


def _write_postgresql_rollback(output_path, release_id, database, groups):
    lines = [f"-- SQL release #{release_id} PostgreSQL partial rollback", f"-- database: {database}",
             f"-- generated_at: {datetime.now().isoformat(timespec='seconds')}", "BEGIN;"]
    for group in reversed(groups):
        lines.extend(group)
    lines.extend(["COMMIT;", ""])
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    temp_path.write_text("\n".join(lines), encoding="utf-8")
    temp_path.replace(output_path)


def execute_postgresql_with_partial_rollback(instance, database, statements, release_id, timeout_seconds=86400):
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from app.services.postgresql_backup import _connection_kwargs

    backup_root = Path(current_app.config.get("SQL_RELEASE_BACKUP_DIR") or "data/sql_release_backups").resolve()
    backup_root.mkdir(parents=True, exist_ok=True)
    output_path = backup_root / f"release_{release_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}_postgresql_rollback.sql"
    max_rows = max(1, int(current_app.config.get("SQL_RELEASE_ROLLBACK_MAX_ROWS", 10000)))
    password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
    kwargs = _connection_kwargs(instance, password, database=database)
    kwargs["options"] = f"-c statement_timeout={max(1, int(timeout_seconds)) * 1000}"
    connection = psycopg2.connect(**kwargs)
    groups, results, total = [], [], 0
    try:
        with connection.cursor(cursor_factory=RealDictCursor) as cursor:
            for line, statement in enumerate(statements, start=1):
                phase = "backing_up"
                _update_release_statement_status(release_id, line, statement, phase)
                try:
                    parsed = _analyze_postgresql_dml(statement)
                    if not parsed:
                        raise ValueError("暂不支持该语句生成可靠 PostgreSQL 回滚 SQL，已阻止执行")
                    backup_rows = 0
                    if parsed["kind"] == "add_column":
                        rollback = [
                            f"ALTER TABLE {parsed['quoted_table']} DROP COLUMN {_pg_quote(parsed['column'])};"
                        ]
                    else:
                        keys = _pg_primary_keys(cursor, parsed["schema"], parsed["table"])
                    if parsed["kind"] in {"update", "delete"}:
                        if parsed["kind"] == "update":
                            assigned = {_pg_unquote(item.split("=", 1)[0].split(".")[-1]).lower() for item in _split_top_level(parsed["set"]) if "=" in item}
                            if assigned.intersection(item.lower() for item in keys):
                                raise ValueError("UPDATE 修改了主键，无法生成可靠的 PostgreSQL 回滚 SQL")
                        cursor.execute(f"SELECT * FROM {parsed['quoted_table']} WHERE {parsed['where']} FOR UPDATE")
                        rows = cursor.fetchmany(max_rows + 1) if keys else cursor.fetchall()
                        if keys and len(rows) > max_rows:
                            raise ValueError(f"受影响记录超过 {max_rows} 行，拒绝生成超大回滚文件")
                        if keys:
                            rollback = _pg_restore_rows(cursor, parsed["quoted_table"], keys, rows)
                        elif parsed["kind"] == "delete":
                            rollback = _pg_restore_rows(cursor, parsed["quoted_table"], [], rows)
                        else:
                            assigned_columns = {
                                _pg_unquote(item.split("=", 1)[0].split(".")[-1]).lower()
                                for item in _split_top_level(parsed["set"])
                                if "=" in item
                            }
                            stable_columns = [
                                column for column in (rows[0].keys() if rows else [])
                                if column.lower() not in assigned_columns
                            ]
                            conditions = [
                                _pg_row_condition(cursor, row, stable_columns) for row in rows
                            ] if stable_columns else []
                            rollback = [
                                f"DELETE FROM {parsed['quoted_table']} WHERE ctid IN "
                                f"(SELECT ctid FROM {parsed['quoted_table']} WHERE {condition} LIMIT 1);"
                                for condition in conditions
                            ]
                            if rows and not rollback:
                                rollback = [f"DELETE FROM {parsed['quoted_table']} WHERE {parsed['where']};"]
                            rollback.extend(_pg_restore_rows(cursor, parsed["quoted_table"], [], rows))
                        backup_rows = len(rows)
                    elif parsed["kind"] == "insert":
                        columns = parsed["columns"] or _pg_table_columns(
                            cursor, parsed["schema"], parsed["table"]
                        )
                        if any(len(row) != len(columns) for row in parsed["values"]):
                            raise ValueError("PostgreSQL INSERT 列数和值数量不一致")
                        positions = {name.lower(): index for index, name in enumerate(columns)}
                        key_columns = keys or columns
                        if any(key.lower() not in positions for key in key_columns):
                            raise ValueError("PostgreSQL INSERT 必须显式提供全部主键值")
                        conditions = []
                        for values in parsed["values"]:
                            key_values = [values[positions[key.lower()]].strip() for key in key_columns]
                            literal_pattern = r"^(?:NULL|TRUE|FALSE|-?\d+(?:\.\d+)?|'(?:[^']|'')*'(?:::[A-Za-z0-9_.\s\[\]\"]+)?)$"
                            if any(not re.match(literal_pattern, value, flags=re.I | re.S) for value in key_values):
                                raise ValueError("PostgreSQL INSERT 主键必须是明确的字面量")
                            parts = [f"{_pg_quote(key)} IS NOT DISTINCT FROM {value}" for key, value in zip(key_columns, key_values)]
                            conditions.append("(" + " AND ".join(parts) + ")")
                        where = " OR ".join(conditions)
                        cursor.execute(f"SELECT * FROM {parsed['quoted_table']} WHERE {where} FOR UPDATE")
                        previous = cursor.fetchmany(max_rows + 1) if keys else cursor.fetchall()
                        if keys and len(previous) > max_rows:
                            raise ValueError(f"受影响记录超过 {max_rows} 行")
                        rollback = [f"DELETE FROM {parsed['quoted_table']} WHERE {where};"]
                        rollback.extend(_pg_restore_rows(cursor, parsed["quoted_table"], keys, previous))
                        backup_rows = len(parsed["values"])
                        rows = previous
                    if parsed["kind"] == "add_column":
                        rows = []
                    _persist_release_rollback_backup(
                        release_id, line, "postgresql", database, parsed, rows, rollback
                    )
                    groups.append([f"-- rollback for statement #{line}", *rollback])
                    _write_postgresql_rollback(output_path, release_id, database, groups)
                    phase = "backup_ready"
                    _update_release_statement_status(
                        release_id, line, statement, phase, backup_rows=backup_rows
                    )
                    phase = "executing"
                    _update_release_statement_status(release_id, line, statement, phase)
                    cursor.execute(statement)
                    affected = cursor.rowcount
                    connection.commit()
                    total += affected if isinstance(affected, int) and affected > 0 else 0
                    result_item = {
                        "line": line,
                        "sql": statement,
                        "status": "success",
                        "affected_rows": affected,
                        "backup_rows": backup_rows,
                    }
                    results.append(result_item)
                    _update_release_statement_status(release_id, line, statement, "success", **{
                        key: value for key, value in result_item.items() if key not in {"line", "sql", "status"}
                    })
                except Exception as statement_exc:
                    connection.rollback()
                    failed_status = "backup_failed" if phase in {"backing_up", "backup_ready"} else "failed"
                    _update_release_statement_status(
                        release_id, line, statement, failed_status, error=str(statement_exc)
                    )
                    raise
    except Exception as exc:
        connection.rollback()
        if not groups:
            output_path.unlink(missing_ok=True)
        raise PartialRollbackExecutionError(str(exc), str(output_path) if groups and output_path.exists() else None) from exc
    finally:
        connection.close()
    return {"columns": [], "rows": [], "affected_rows": total, "statement_count": len(results), "statements": results}, (str(output_path) if groups else None)


def validate_mongo_release_statement(statement):
    from app.services.data_access import _parse_mongo_shell_command
    collection, operation, args = _parse_mongo_shell_command(statement)
    if not collection or operation not in {"insertone", "insertmany", "updateone", "updatemany", "deleteone", "deletemany", "replaceone"}:
        return False, "仅支持 insertOne/insertMany/updateOne/updateMany/deleteOne/deleteMany/replaceOne"
    if operation in {"updateone", "updatemany", "deleteone", "deletemany", "replaceone"} and not args:
        return False, "MongoDB 变更命令缺少过滤条件"
    return True, None


def execute_mongodb_with_partial_rollback(instance, database, statements, release_id, timeout_seconds=86400, seed_nodes=None):
    from bson.objectid import ObjectId
    from pymongo import MongoClient
    from app.services.data_access import _convert_mongo_arg, _mongo_to_bson, _parse_mongo_shell_command, _json_safe

    password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
    target = seed_nodes if seed_nodes else (instance.resolved_ip or instance.host_input)
    port = None if seed_nodes else instance.port
    client = MongoClient(target, port, username=instance.username, password=password, authSource="admin",
                         directConnection=False, tls=False, serverSelectionTimeoutMS=5000, connectTimeoutMS=5000,
                         socketTimeoutMS=max(1, int(timeout_seconds)) * 1000, appname="dbms-sql-release")
    results, total = [], 0
    try:
        db_handle = client.get_database(database)
        for line, statement in enumerate(statements, start=1):
            _update_release_statement_status(release_id, line, statement, "backup_skipped")
            try:
                collection_name, operation, args = _parse_mongo_shell_command(statement)
                valid, reason = validate_mongo_release_statement(statement)
                if not valid:
                    raise ValueError(reason)
                parsed = [_mongo_to_bson(_convert_mongo_arg(item)) for item in args]
                collection = db_handle.get_collection(collection_name)
                if operation in {"insertone", "insertmany"}:
                    documents = [parsed[0]] if operation == "insertone" else list(parsed[0])
                    if not documents:
                        raise ValueError("MongoDB INSERT 文档不能为空")
                    for document in documents:
                        if "_id" not in document:
                            document["_id"] = ObjectId()
                else:
                    mongo_filter = parsed[0]
                    if not isinstance(mongo_filter, dict) or not mongo_filter:
                        raise ValueError("MongoDB UPDATE/DELETE/REPLACE 必须提供非空过滤条件")
                    option_index = 1 if operation in {"deleteone", "deletemany"} else 2
                    options = parsed[option_index] if len(parsed) > option_index and isinstance(parsed[option_index], dict) else {}
                    if options.get("upsert"):
                        raise ValueError("MongoDB 上线暂不支持 upsert")
                _update_release_statement_status(release_id, line, statement, "executing")
                if operation == "insertone":
                    result = collection.insert_one(documents[0]); affected = 1
                elif operation == "insertmany":
                    result = collection.insert_many(documents); affected = len(result.inserted_ids)
                elif operation == "updateone":
                    result = collection.update_one(parsed[0], parsed[1], **options); affected = result.modified_count
                elif operation == "updatemany":
                    result = collection.update_many(parsed[0], parsed[1], **options); affected = result.modified_count
                elif operation == "deleteone":
                    result = collection.delete_one(parsed[0], **options); affected = result.deleted_count
                elif operation == "deletemany":
                    result = collection.delete_many(parsed[0], **options); affected = result.deleted_count
                else:
                    result = collection.replace_one(parsed[0], parsed[1], **options); affected = result.modified_count
                total += int(affected or 0)
                item = {"line": line, "sql": statement, "status": "success", "affected_rows": int(affected or 0), "backup_rows": 0,
                        "result": _json_safe(getattr(result, "raw_result", {}))}
                results.append(item)
                _update_release_statement_status(release_id, line, statement, "success", affected_rows=int(affected or 0), backup_rows=0)
            except Exception as statement_exc:
                _update_release_statement_status(release_id, line, statement, "failed", error=str(statement_exc))
                raise
    except Exception as exc:
        raise PartialRollbackExecutionError(str(exc), None) from exc
    finally:
        client.close()
    return {"rows": [], "affected_rows": total, "statement_count": len(results), "statements": results}, None


def execute_release_rollback(instance, database, rollback_items, db_type, release_id, timeout_seconds=86400):
    normalized_type = str(db_type or "").lower()
    if normalized_type not in {"mysql", "postgresql"}:
        raise ValueError("当前仅支持 MySQL 和 PostgreSQL 工单回滚")

    if normalized_type == "mysql":
        import pymysql

        password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
        connection = pymysql.connect(
            host=instance.resolved_ip or instance.host_input,
            port=instance.port,
            user=instance.username,
            password=password,
            database=database,
            charset="utf8mb4",
            connect_timeout=5,
            read_timeout=timeout_seconds,
            write_timeout=timeout_seconds,
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=False,
        )
        cursor_kwargs = {}
    else:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        from app.services.postgresql_backup import _connection_kwargs

        password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
        kwargs = _connection_kwargs(instance, password, database=database)
        kwargs["options"] = f"-c statement_timeout={max(1, int(timeout_seconds)) * 1000}"
        connection = psycopg2.connect(**kwargs)
        cursor_kwargs = {"cursor_factory": RealDictCursor}

    completed = []
    try:
        with connection.cursor(**cursor_kwargs) as cursor:
            for item in rollback_items:
                line = int(item["line"])
                source_sql = str(item.get("source_sql") or "")
                _update_release_statement_status(
                    release_id, line, source_sql, "rollback_executing"
                )
                try:
                    affected = 0
                    for rollback_statement in split_sql_statements(item.get("rollback_sql") or ""):
                        cursor.execute(rollback_statement)
                        rowcount = cursor.rowcount
                        if isinstance(rowcount, int) and rowcount > 0:
                            affected += rowcount
                    connection.commit()
                    _update_release_statement_status(
                        release_id, line, source_sql, "rolled_back",
                        rollback_affected_rows=affected,
                    )
                    completed.append({"line": line, "affected_rows": affected})
                except Exception as exc:
                    connection.rollback()
                    _update_release_statement_status(
                        release_id, line, source_sql, "rollback_failed",
                        rollback_error=str(exc),
                    )
                    raise ReleaseRollbackExecutionError(str(exc), line=line) from exc
    finally:
        connection.close()
    return {"rolled_back_count": len(completed), "statements": completed}
