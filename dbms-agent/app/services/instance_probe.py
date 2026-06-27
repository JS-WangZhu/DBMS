from datetime import datetime


def _safe_int(value):
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _bool_flag(value):
    text = str(value or "").strip().lower()
    if text in {"yes", "on", "1", "true"}:
        return True
    if text in {"no", "off", "0", "false"}:
        return False
    return None


def _mysql(instance, password):
    import pymysql

    conn = pymysql.connect(
        host=instance.get("resolved_ip") or instance.get("host_input"),
        port=int(instance.get("port") or 3306),
        user=instance.get("username") or "",
        password=password or "",
        connect_timeout=3,
        read_timeout=5,
        write_timeout=5,
        autocommit=True,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1, VERSION()")
            row = cursor.fetchone()
            read_only = None
            super_read_only = None
            for variable in ("read_only", "super_read_only"):
                try:
                    cursor.execute(f"SHOW GLOBAL VARIABLES LIKE '{variable}'")
                    variable_row = cursor.fetchone()
                    if variable == "read_only":
                        read_only = _bool_flag(variable_row[1]) if variable_row else None
                    else:
                        super_read_only = _bool_flag(variable_row[1]) if variable_row else None
                except Exception:
                    continue
            payload = {
                "ok": bool(row and row[0] == 1),
                "ping_ok": bool(row and row[0] == 1),
                "db_type": "mysql",
                "version": row[1] if row else None,
                "read_only": read_only,
                "super_read_only": super_read_only,
                "replication_role": "master",
                "replica_io_running": None,
                "replica_sql_running": None,
                "seconds_behind_master": None,
            }
            payload["effective_read_only"] = bool(payload["read_only"] or payload["super_read_only"])
            for command in ("SHOW REPLICA STATUS", "SHOW SLAVE STATUS"):
                try:
                    cursor.execute(command)
                    repl = cursor.fetchone()
                    if not repl:
                        continue
                    desc = [item[0] for item in cursor.description]
                    data = dict(zip(desc, repl))
                    payload.update({
                        "replication_role": "slave",
                        "replica_io_running": _bool_flag(data.get("Replica_IO_Running", data.get("Slave_IO_Running"))),
                        "replica_sql_running": _bool_flag(data.get("Replica_SQL_Running", data.get("Slave_SQL_Running"))),
                        "seconds_behind_master": _safe_int(data.get("Seconds_Behind_Source", data.get("Seconds_Behind_Master"))),
                        "replica_source_host": data.get("Source_Host", data.get("Master_Host")),
                        "replica_source_port": _safe_int(data.get("Source_Port", data.get("Master_Port"))),
                    })
                    break
                except Exception:
                    continue

            payload.update({"mgr_member_role": None, "mgr_member_state": None, "mgr_group_name": None, "mgr_members": []})
            try:
                cursor.execute(
                    "SELECT MEMBER_ID, MEMBER_HOST, MEMBER_PORT, MEMBER_STATE, MEMBER_ROLE "
                    "FROM performance_schema.replication_group_members"
                )
                desc = [item[0].lower() for item in cursor.description]
                payload["mgr_members"] = [dict(zip(desc, item)) for item in (cursor.fetchall() or [])]
                cursor.execute("SELECT @@server_uuid, @@group_replication_group_name")
                group_row = cursor.fetchone()
                server_uuid = str(group_row[0] or "") if group_row else ""
                payload["mgr_group_name"] = group_row[1] if group_row else None
                local = next((item for item in payload["mgr_members"] if str(item.get("member_id") or "") == server_uuid), None)
                if local:
                    payload["mgr_member_role"] = str(local.get("member_role") or "").upper() or None
                    payload["mgr_member_state"] = str(local.get("member_state") or "").upper() or None
                    if payload["mgr_member_role"] == "PRIMARY":
                        payload["replication_role"] = "mgr_primary"
                    elif payload["mgr_member_role"] == "SECONDARY":
                        payload["replication_role"] = "mgr_secondary"
            except Exception:
                payload["mgr_members"] = []
            return payload
    finally:
        conn.close()


def _redis(instance, password):
    import redis

    client = redis.Redis(
        host=instance.get("resolved_ip") or instance.get("host_input"),
        port=int(instance.get("port") or 6379),
        username=instance.get("username") or None,
        password=password or None,
        socket_connect_timeout=3,
        socket_timeout=5,
        decode_responses=True,
    )
    ping_ok = bool(client.ping())
    info = client.info()
    replication = client.info("replication")
    return {
        "ok": ping_ok,
        "ping_ok": ping_ok,
        "db_type": "redis",
        "version": info.get("redis_version"),
        "uptime": _safe_int(info.get("uptime_in_seconds")),
        "connected_clients": _safe_int(info.get("connected_clients")),
        "used_memory": _safe_int(info.get("used_memory")),
        "role": replication.get("role"),
        "master_host": replication.get("master_host"),
        "master_port": _safe_int(replication.get("master_port")),
        "master_link_status": replication.get("master_link_status"),
    }


def _mongodb(instance, password):
    from pymongo import MongoClient

    username = instance.get("username") or None
    client = MongoClient(
        host=instance.get("resolved_ip") or instance.get("host_input"),
        port=int(instance.get("port") or 27017),
        username=username,
        password=password or None,
        serverSelectionTimeoutMS=3000,
        connectTimeoutMS=3000,
    )
    try:
        ping = client.admin.command("ping")
        build = client.admin.command("buildInfo")
        payload = {"ok": ping.get("ok") == 1.0, "ping_ok": ping.get("ok") == 1.0, "db_type": "mongodb", "version": build.get("version")}
        try:
            from bson import json_util
            import json

            payload["repl"] = json.loads(json_util.dumps(client.admin.command("replSetGetStatus")))
        except Exception as exc:
            payload["repl_error"] = str(exc)
        return payload
    finally:
        client.close()


def _doris(instance, password):
    import pymysql

    conn = pymysql.connect(
        host=instance.get("resolved_ip") or instance.get("host_input"),
        port=int(instance.get("port") or 9030),
        user=instance.get("username") or "",
        password=password or "",
        connect_timeout=3,
        read_timeout=5,
        autocommit=True,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1, VERSION()")
            row = cursor.fetchone()
            return {"ok": bool(row and row[0] == 1), "ping_ok": bool(row and row[0] == 1), "db_type": "doris", "version": row[1] if row else None}
    finally:
        conn.close()


COLLECTORS = {"mysql": _mysql, "redis": _redis, "mongodb": _mongodb, "doris": _doris}


def probe_instance(instance, password):
    db_type = str(instance.get("db_type") or "").lower()
    collector = COLLECTORS.get(db_type)
    if not collector:
        return {"ok": False, "error": f"unsupported db_type: {db_type}"}
    try:
        result = collector(instance, password)
        result.setdefault("collected_at", datetime.now().isoformat())
        result.setdefault("probe_source", "agent")
        return result
    except Exception as exc:
        return {"ok": False, "error": f"{db_type} collect failed: {exc}", "collected_at": datetime.now().isoformat(), "probe_source": "agent"}