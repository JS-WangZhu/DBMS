from datetime import datetime

from app.services.collectors.node_exporter import collect_node_exporter_metrics


def _json_value(value):
    return value.isoformat() if hasattr(value, "isoformat") else value


def _show_rows(cursor, statement):
    cursor.execute(statement)
    columns = [item[0] for item in cursor.description or []]
    return [
        {columns[index]: _json_value(value) for index, value in enumerate(row)}
        for row in (cursor.fetchall() or [])
    ]


def _alive_count(rows):
    if rows is None:
        return None
    total = 0
    for row in rows:
        alive = next((value for key, value in row.items() if str(key).lower() == "alive"), None)
        if str(alive).strip().lower() in {"true", "1", "yes", "on"}:
            total += 1
    return total


def collect_doris_status(instance, password):
    # Doris FE exposes cluster node status through its MySQL protocol.
    host_metrics = collect_node_exporter_metrics(instance)
    warnings = []
    conn = None
    try:
        import pymysql

        conn = pymysql.connect(
            host=instance.resolved_ip or instance.host_input,
            port=instance.port,
            user=instance.username,
            password=password,
            connect_timeout=3,
            read_timeout=3,
            write_timeout=3,
            autocommit=True,
        )

        with conn.cursor() as cursor:
            cursor.execute("SELECT 1, VERSION();")
            row = cursor.fetchone()
            ping_ok = bool(row and row[0] == 1)
            frontends = None
            backends = None
            try:
                frontends = _show_rows(cursor, "SHOW FRONTENDS")
            except Exception as exc:
                warnings.append(f"frontends:{exc}")
            try:
                backends = _show_rows(cursor, "SHOW BACKENDS")
            except Exception as exc:
                warnings.append(f"backends:{exc}")

        return {
            "ok": ping_ok,
            "ping_ok": ping_ok,
            "db_type": "doris",
            "collected_at": datetime.now().isoformat(),
            "version": row[1] if row else None,
            "frontend_count": len(frontends) if frontends is not None else None,
            "frontend_alive_count": _alive_count(frontends),
            "backend_count": len(backends) if backends is not None else None,
            "backend_alive_count": _alive_count(backends),
            "frontends": frontends,
            "backends": backends,
            "warnings": warnings,
            **host_metrics,
        }
    except Exception as exc:
        return {"ok": False, "error": f"doris collect failed: {exc}", **host_metrics}
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


