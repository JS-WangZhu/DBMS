import psycopg2


def _connection_kwargs(instance, password, database=None):
    extra = instance.extra_json if isinstance(instance.extra_json, dict) else {}
    return {
        "host": instance.resolved_ip or instance.host_input,
        "port": int(instance.port or 5432),
        "user": instance.username or "",
        "password": password or "",
        "dbname": database or extra.get("database") or extra.get("dbname") or "postgres",
        "sslmode": extra.get("sslmode") or "prefer",
        "connect_timeout": 5,
        "options": "-c statement_timeout=5000",
    }


def list_databases(instance, password):
    conn = psycopg2.connect(**_connection_kwargs(instance, password))
    try:
        conn.autocommit = True
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT datname FROM pg_database "
                "WHERE datallowconn AND NOT datistemplate ORDER BY datname"
            )
            return [row[0] for row in cursor.fetchall()]
    finally:
        conn.close()


def list_tables(instance, password, database):
    conn = psycopg2.connect(**_connection_kwargs(instance, password, database=database))
    try:
        conn.autocommit = True
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT n.nspname, c.relname "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE c.relkind IN ('r', 'p') "
                "AND n.nspname NOT IN ('pg_catalog', 'information_schema') "
                "AND n.nspname NOT LIKE 'pg_toast%' "
                "ORDER BY n.nspname, c.relname"
            )
            return [f"{row[0]}.{row[1]}" for row in cursor.fetchall()]
    finally:
        conn.close()


def list_objects(instance, password, database):
    conn = psycopg2.connect(**_connection_kwargs(instance, password, database=database))
    try:
        conn.autocommit = True
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT n.nspname, c.relname, c.relkind, "
                "CASE WHEN c.relkind IN ('r', 'p', 'm') THEN pg_total_relation_size(c.oid) ELSE 0 END, "
                "COALESCE(c.reltuples, 0)::bigint "
                "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                "WHERE c.relkind IN ('r', 'p', 'v', 'm') "
                "AND n.nspname NOT IN ('pg_catalog', 'information_schema') "
                "AND n.nspname NOT LIKE 'pg_toast%' ORDER BY n.nspname, c.relname"
            )
            tables, views = [], []
            for schema, name, kind, size_bytes, row_count in cursor.fetchall():
                item = {"name": f"{schema}.{name}", "schema": schema, "object_name": name}
                if kind in {"r", "p"}:
                    item.update({"size_bytes": int(size_bytes or 0), "row_count": int(row_count or 0)})
                    tables.append(item)
                else:
                    views.append(item)
            cursor.execute(
                "SELECT routine_schema, routine_name, routine_type FROM information_schema.routines "
                "WHERE routine_schema NOT IN ('pg_catalog', 'information_schema') "
                "ORDER BY routine_schema, routine_name"
            )
            procedures, functions = [], []
            for schema, name, routine_type in cursor.fetchall():
                item = {"name": f"{schema}.{name}", "schema": schema, "object_name": name}
                (procedures if routine_type == "PROCEDURE" else functions).append(item)
        return {
            "database": database,
            "tables": tables,
            "views": views,
            "procedures": procedures,
            "functions": functions,
            "triggers": [],
            "events": [],
        }
    finally:
        conn.close()


def list_table_columns(instance, password, database, table):
    parts = str(table or "").split(".", 1)
    schema, table_name = parts if len(parts) == 2 else ("public", parts[0])
    conn = psycopg2.connect(**_connection_kwargs(instance, password, database=database))
    try:
        conn.autocommit = True
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT c.column_name, c.data_type, c.udt_name, c.is_nullable, c.column_default, "
                "COALESCE(pgd.description, ''), c.ordinal_position, "
                "EXISTS (SELECT 1 FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name "
                "AND tc.constraint_schema=kcu.constraint_schema "
                "WHERE tc.constraint_type='PRIMARY KEY' AND tc.table_schema=c.table_schema "
                "AND tc.table_name=c.table_name AND kcu.column_name=c.column_name) "
                "FROM information_schema.columns c "
                "LEFT JOIN pg_catalog.pg_statio_all_tables st ON st.schemaname=c.table_schema AND st.relname=c.table_name "
                "LEFT JOIN pg_catalog.pg_description pgd ON pgd.objoid=st.relid AND pgd.objsubid=c.ordinal_position "
                "WHERE c.table_schema=%s AND c.table_name=%s ORDER BY c.ordinal_position",
                (schema, table_name),
            )
            return [{
                "name": row[0], "data_type": row[1], "column_type": row[2],
                "nullable": row[3] == "YES", "default": row[4], "comment": row[5] or "",
                "position": int(row[6] or 0), "column_key": "PRI" if row[7] else "",
            } for row in cursor.fetchall()]
    finally:
        conn.close()
