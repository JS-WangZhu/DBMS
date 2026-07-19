from datetime import datetime

from app.services.collectors.node_exporter import collect_node_exporter_metrics


def _safe_int(value):
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _safe_float(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def collect_postgresql_status(instance, password):
    warnings = []
    host_metrics = collect_node_exporter_metrics(instance)
    if host_metrics.get("node_exporter_error"):
        warnings.append(host_metrics["node_exporter_error"])

    extra = instance.extra_json if isinstance(instance.extra_json, dict) else {}
    try:
        import psycopg2

        conn = psycopg2.connect(
            host=instance.resolved_ip or instance.host_input,
            port=instance.port,
            user=instance.username or "",
            password=password or "",
            dbname=extra.get("database") or extra.get("dbname") or "postgres",
            sslmode=extra.get("sslmode") or "prefer",
            connect_timeout=3,
            options="-c statement_timeout=3000",
        )
        conn.autocommit = True
    except Exception as exc:
        return {"ok": False, "error": f"postgresql connect failed: {exc}", **host_metrics}

    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT version(), current_database(), pg_is_in_recovery(), "
                "EXTRACT(EPOCH FROM (now() - pg_postmaster_start_time()))::bigint, "
                "current_setting('max_connections')::int"
            )
            base = cursor.fetchone()
            version = base[0] if base else None
            database = base[1] if base else None
            in_recovery = bool(base[2]) if base else False
            uptime = _safe_int(base[3]) if base else None
            max_connections = _safe_int(base[4]) if base else None

            cursor.execute(
                "SELECT count(*)::bigint, "
                "count(*) FILTER (WHERE state = 'active')::bigint, "
                "count(*) FILTER (WHERE wait_event_type = 'Lock')::bigint "
                "FROM pg_stat_activity"
            )
            activity = cursor.fetchone() or (None, None, None)
            connections = _safe_int(activity[0])
            active_connections = _safe_int(activity[1])
            lock_waiting_connections = _safe_int(activity[2])

            xact_commit = xact_rollback = deadlocks = database_size_bytes = None
            try:
                cursor.execute(
                    "SELECT xact_commit, xact_rollback, deadlocks, pg_database_size(datname) "
                    "FROM pg_stat_database WHERE datname = current_database()"
                )
                stats = cursor.fetchone()
                if stats:
                    xact_commit = _safe_int(stats[0])
                    xact_rollback = _safe_int(stats[1])
                    deadlocks = _safe_int(stats[2])
                    database_size_bytes = _safe_int(stats[3])
            except Exception as exc:
                warnings.append(f"database_stats:{exc}")

            replication_lag_seconds = None
            replication_lag_bytes = None
            receive_lag_bytes = None
            replay_lag_bytes = None
            wal_source_lsn = None
            wal_receive_lsn = None
            wal_replay_lsn = None
            wal_current_lsn = None
            wal_receiver_status = None
            wal_last_message_at = None
            replay_paused = False
            replica_count = 0
            if in_recovery:
                try:
                    cursor.execute(
                        "WITH receiver AS ("
                        " SELECT status, latest_end_lsn, last_msg_receipt_time"
                        " FROM pg_stat_wal_receiver LIMIT 1"
                        "), positions AS ("
                        " SELECT (SELECT status FROM receiver) AS receiver_status,"
                        " (SELECT latest_end_lsn FROM receiver) AS source_lsn,"
                        " pg_last_wal_receive_lsn() AS receive_lsn,"
                        " pg_last_wal_replay_lsn() AS replay_lsn,"
                        " (SELECT last_msg_receipt_time FROM receiver) AS last_message_at"
                        ") SELECT receiver_status, source_lsn::text, receive_lsn::text, replay_lsn::text,"
                        " CASE WHEN receiver_status IS NULL OR source_lsn IS NULL THEN NULL ELSE GREATEST(COALESCE(pg_wal_lsn_diff(GREATEST(source_lsn, receive_lsn), replay_lsn), 0), 0)::bigint END,"
                        " CASE WHEN source_lsn IS NULL THEN NULL ELSE GREATEST(COALESCE(pg_wal_lsn_diff(GREATEST(source_lsn, receive_lsn), receive_lsn), 0), 0)::bigint END,"
                        " GREATEST(COALESCE(pg_wal_lsn_diff(receive_lsn, replay_lsn), 0), 0)::bigint,"
                        " CASE WHEN receiver_status IS NULL OR source_lsn IS NULL THEN NULL WHEN GREATEST(COALESCE(pg_wal_lsn_diff(GREATEST(source_lsn, receive_lsn), replay_lsn), 0), 0) > 0"
                        " AND pg_last_xact_replay_timestamp() IS NOT NULL"
                        " THEN EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp())) ELSE 0 END,"
                        " pg_is_wal_replay_paused(), last_message_at"
                        " FROM positions"
                    )
                    repl = cursor.fetchone()
                    if repl:
                        wal_receiver_status = repl[0]
                        wal_source_lsn = repl[1]
                        wal_receive_lsn = repl[2]
                        wal_replay_lsn = repl[3]
                        replication_lag_bytes = _safe_int(repl[4])
                        receive_lag_bytes = _safe_int(repl[5])
                        replay_lag_bytes = _safe_int(repl[6])
                        replication_lag_seconds = round(_safe_float(repl[7]), 3) if repl[7] is not None else None
                        replay_paused = bool(repl[8])
                        wal_last_message_at = repl[9].isoformat() if hasattr(repl[9], "isoformat") else repl[9]
                except Exception as exc:
                    warnings.append(f"replication:{exc}")
            else:
                try:
                    cursor.execute(
                        "SELECT pg_current_wal_lsn()::text, "
                        "(SELECT count(*)::bigint FROM pg_stat_replication WHERE state = 'streaming')"
                    )
                    row = cursor.fetchone()
                    wal_current_lsn = row[0] if row else None
                    replica_count = _safe_int(row[1]) if row else 0
                except Exception as exc:
                    warnings.append(f"replication:{exc}")

        connection_usage_pct = None
        if max_connections and connections is not None:
            connection_usage_pct = round(connections * 100 / max_connections, 2)

        return {
            "ok": True, "ping_ok": True, "db_type": "postgresql",
            "collected_at": datetime.now().isoformat(), "version": version,
            "database": database, "uptime": uptime,
            "replication_role": "standby" if in_recovery else "primary",
            "in_recovery": in_recovery, "replication_lag_seconds": replication_lag_seconds,
            "replication_lag_bytes": replication_lag_bytes,
            "receive_lag_bytes": receive_lag_bytes, "replay_lag_bytes": replay_lag_bytes,
            "wal_current_lsn": wal_current_lsn, "wal_source_lsn": wal_source_lsn,
            "wal_receive_lsn": wal_receive_lsn, "wal_replay_lsn": wal_replay_lsn,
            "wal_receiver_status": wal_receiver_status, "wal_last_message_at": wal_last_message_at,
            "replay_paused": replay_paused, "replica_count": replica_count,
            "connections": connections, "active_connections": active_connections,
            "lock_waiting_connections": lock_waiting_connections,
            "max_connections": max_connections, "connection_usage_pct": connection_usage_pct,
            "xact_commit": xact_commit, "xact_rollback": xact_rollback,
            "deadlocks": deadlocks, "database_size_bytes": database_size_bytes,
            "warnings": warnings, **host_metrics,
        }
    except Exception as exc:
        return {"ok": False, "error": f"postgresql collect failed: {exc}", **host_metrics}
    finally:
        conn.close()
