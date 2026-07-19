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
