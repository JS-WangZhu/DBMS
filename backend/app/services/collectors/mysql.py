from datetime import datetime

from app.services.collectors.node_exporter import collect_node_exporter_metrics
from app.services.dns_resolver import resolve_host

def _to_bool_flag(value):
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"yes", "on", "1", "true"}:
        return True
    if text in {"no", "off", "0", "false"}:
        return False
    return None

def _safe_int(value):
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None

def collect_mysql_status(instance, password):
    warnings = []
    host_metrics = collect_node_exporter_metrics(instance)
    if host_metrics.get("node_exporter_error"):
        warnings.append(host_metrics["node_exporter_error"])

    def _fetch_status_like(cursor, key):
        try:
            cursor.execute(f"SHOW GLOBAL STATUS LIKE '{key}';")
            row = cursor.fetchone()
            return row[1] if row else None
        except Exception as exc:
            warnings.append(f"status:{key}:{exc}")
            return None

    def _fetch_variable_like(cursor, key):
        try:
            cursor.execute(f"SHOW GLOBAL VARIABLES LIKE '{key}';")
            row = cursor.fetchone()
            return row[1] if row else None
        except Exception as exc:
            warnings.append(f"variable:{key}:{exc}")
            return None

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
    except Exception as exc:
        return {"ok": False, "error": f"mysql connect failed: {exc}"}

    try:
        with conn.cursor() as cursor:
            try:
                cursor.execute("SELECT 1;")
                ping_row = cursor.fetchone()
                ping_ok = bool(ping_row and _safe_int(ping_row[0]) == 1)
            except Exception as exc:
                return {"ok": False, "error": f"mysql select1 failed: {exc}"}

            threads_connected = _safe_int(_fetch_status_like(cursor, "Threads_connected"))
            threads_running = _safe_int(_fetch_status_like(cursor, "Threads_running"))
            max_connections = _safe_int(_fetch_variable_like(cursor, "max_connections"))
            uptime = _safe_int(_fetch_status_like(cursor, "Uptime"))
            questions_total = _safe_int(_fetch_status_like(cursor, "Questions"))
            com_commit_total = _safe_int(_fetch_status_like(cursor, "Com_commit"))
            com_rollback_total = _safe_int(_fetch_status_like(cursor, "Com_rollback"))
            lock_waits = _safe_int(_fetch_status_like(cursor, "Innodb_row_lock_current_waits"))

            read_only_flag = _to_bool_flag(_fetch_variable_like(cursor, "read_only"))
            super_read_only_flag = _to_bool_flag(_fetch_variable_like(cursor, "super_read_only"))

            version = None
            try:
                cursor.execute("SELECT VERSION();")
                version_row = cursor.fetchone()
                version = version_row[0] if version_row else None
            except Exception as exc:
                warnings.append(f"version:{exc}")

            seconds_behind_master = None
            replica_io_running = None
            replica_sql_running = None
            replica_source_host = None
            replica_source_port = None
            replication_role = "master"

            try:
                cursor.execute("SHOW REPLICA STATUS;")
                repl_row = cursor.fetchone()
                if repl_row:
                    desc = [item[0] for item in cursor.description]
                    idx_lag = desc.index("Seconds_Behind_Source") if "Seconds_Behind_Source" in desc else None
                    idx_io = desc.index("Replica_IO_Running") if "Replica_IO_Running" in desc else None
                    idx_sql = desc.index("Replica_SQL_Running") if "Replica_SQL_Running" in desc else None
                    idx_source_host = desc.index("Source_Host") if "Source_Host" in desc else None
                    idx_source_port = desc.index("Source_Port") if "Source_Port" in desc else None
                    if idx_lag is not None:
                        seconds_behind_master = repl_row[idx_lag]
                    if idx_io is not None:
                        replica_io_running = _to_bool_flag(repl_row[idx_io])
                    if idx_sql is not None:
                        replica_sql_running = _to_bool_flag(repl_row[idx_sql])
                    if idx_source_host is not None:
                        replica_source_host = repl_row[idx_source_host]
                    if idx_source_port is not None:
                        replica_source_port = _safe_int(repl_row[idx_source_port])
                    replication_role = "slave"
            except Exception:
                try:
                    cursor.execute("SHOW SLAVE STATUS;")
                    repl_row = cursor.fetchone()
                    if repl_row:
                        desc = [item[0] for item in cursor.description]
                        idx_lag = desc.index("Seconds_Behind_Master") if "Seconds_Behind_Master" in desc else None
                        idx_io = desc.index("Slave_IO_Running") if "Slave_IO_Running" in desc else None
                        idx_sql = desc.index("Slave_SQL_Running") if "Slave_SQL_Running" in desc else None
                        idx_source_host = desc.index("Master_Host") if "Master_Host" in desc else None
                        idx_source_port = desc.index("Master_Port") if "Master_Port" in desc else None
                        if idx_lag is not None:
                            seconds_behind_master = repl_row[idx_lag]
                        if idx_io is not None:
                            replica_io_running = _to_bool_flag(repl_row[idx_io])
                        if idx_sql is not None:
                            replica_sql_running = _to_bool_flag(repl_row[idx_sql])
                        if idx_source_host is not None:
                            replica_source_host = repl_row[idx_source_host]
                        if idx_source_port is not None:
                            replica_source_port = _safe_int(repl_row[idx_source_port])
                        replication_role = "slave"
                except Exception:
                    seconds_behind_master = None

            mgr_member_state = None
            mgr_member_role = None
            mgr_group_name = None
            mgr_members = []
            try:
                cursor.execute(
                    "SELECT MEMBER_ID, MEMBER_HOST, MEMBER_PORT, MEMBER_STATE, MEMBER_ROLE "
                    "FROM performance_schema.replication_group_members"
                )
                desc = [item[0] for item in cursor.description]
                for raw_row in cursor.fetchall() or []:
                    member = {desc[idx].lower(): raw_row[idx] for idx in range(len(desc))}
                    member["member_port"] = _safe_int(member.get("member_port"))
                    mgr_members.append(member)
                cursor.execute("SELECT @@server_uuid, @@group_replication_group_name")
                group_row = cursor.fetchone()
                server_uuid = str(group_row[0] or "").strip() if group_row else ""
                mgr_group_name = str(group_row[1] or "").strip() if group_row and group_row[1] else None
                local_member = next(
                    (item for item in mgr_members if str(item.get("member_id") or "").strip() == server_uuid),
                    None,
                )
                if local_member:
                    mgr_member_state = str(local_member.get("member_state") or "").strip().upper() or None
                    mgr_member_role = str(local_member.get("member_role") or "").strip().upper() or None
                    if mgr_member_role == "PRIMARY":
                        replication_role = "mgr_primary"
                    elif mgr_member_role == "SECONDARY":
                        replication_role = "mgr_secondary"
            except Exception:
                # A missing table/variable is the normal non-MGR case.
                mgr_members = []

        if read_only_flag is None and super_read_only_flag is None:
            effective_read_only = None
        else:
            effective_read_only = bool(read_only_flag is True or super_read_only_flag is True)

        if replication_role not in {"slave", "mgr_primary", "mgr_secondary"}:
            if effective_read_only is True:
                replication_role = "read_only"
            elif effective_read_only is False:
                replication_role = "master"
            else:
                replication_role = "unknown"

        replica_source_host_value = str(replica_source_host).strip() if replica_source_host else None
        replica_source_resolved_ip = resolve_host(replica_source_host_value) if replica_source_host_value else None
        qps = None
        tps = None
        if uptime and uptime > 0:
            if questions_total is not None:
                qps = round(questions_total / uptime, 3)

            if com_commit_total is not None or com_rollback_total is not None:
                tps = round(((com_commit_total or 0) + (com_rollback_total or 0)) / uptime, 3)

        return {
            "ok": True,
            "ping_ok": ping_ok,
            "db_type": "mysql",
            "collected_at": datetime.now().isoformat(),
            "version": version,
            "uptime": uptime,
            "threads_connected": threads_connected,
            "threads_running": threads_running,
            "max_connections": max_connections,
            "questions_total": questions_total,
            "com_commit_total": com_commit_total,
            "com_rollback_total": com_rollback_total,
            "qps": qps,
            "tps": tps,
            "lock_waits": lock_waits,
            "read_only": read_only_flag,
            "super_read_only": super_read_only_flag,
            "effective_read_only": effective_read_only,
            "replication_role": replication_role,
            "mgr_member_role": mgr_member_role,
            "mgr_member_state": mgr_member_state,
            "mgr_group_name": mgr_group_name,
            "mgr_members": mgr_members,
            "replica_io_running": replica_io_running,
            "replica_sql_running": replica_sql_running,
            "replica_source_host": replica_source_host_value,
            "replica_source_resolved_ip": replica_source_resolved_ip,
            "replica_source_port": replica_source_port,
            "seconds_behind_master": _safe_int(seconds_behind_master),
            "warnings": warnings,
            **host_metrics,
        }
    except Exception as exc:
        return {"ok": False, "error": f"mysql collect failed: {exc}"}
    finally:
        try:
            conn.close()
        except Exception:
            pass
