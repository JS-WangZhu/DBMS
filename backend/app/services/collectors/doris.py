from datetime import datetime

from app.services.collectors.node_exporter import collect_node_exporter_metrics


def collect_doris_status(instance, password):
    # Doris FE can be queried through MySQL protocol for basic status.
    host_metrics = collect_node_exporter_metrics(instance)
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
            cursor.execute("SELECT VERSION();")
            row = cursor.fetchone()

        conn.close()

        return {
            "ok": True,
            "db_type": "doris",
            "collected_at": datetime.now().isoformat(),
            "version": row[0] if row else None,
            **host_metrics,
        }
    except Exception as exc:
        return {"ok": False, "error": f"doris collect failed: {exc}"}


