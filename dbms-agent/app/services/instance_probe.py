from datetime import datetime, timedelta
import json
import math
import re
import socket
import time
from urllib.request import Request, urlopen


METRIC_LINE_RE = re.compile(
    r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{([^}]*)\})?\s+([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)"
)
METRIC_LABEL_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="([^"]*)"')
HOST_RATE_CACHE = {}


def _safe_int(value):
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _bool_flag(value):
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"yes", "on", "1", "true"}:
        return True
    if text in {"no", "off", "0", "false"}:
        return False
    return None


def _as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off", ""}:
        return False
    return default


def _bson_to_json(value):
    try:
        from bson.json_util import dumps as bson_dumps

        return json.loads(bson_dumps(value))
    except Exception:
        return value


def _resolve_host(host):
    try:
        return socket.gethostbyname(host) if host else None
    except Exception:
        return None


def _metric_rows(text):
    metrics = {}
    for raw in str(text or "").splitlines():
        match = METRIC_LINE_RE.match(raw.strip())
        if not match:
            continue
        name, labels_raw, value_raw = match.groups()
        try:
            value = float(value_raw)
        except (TypeError, ValueError):
            continue
        if math.isnan(value):
            continue
        labels = {item.group(1): item.group(2) for item in METRIC_LABEL_RE.finditer(labels_raw or "")}
        metrics.setdefault(name, []).append((labels, value))
    return metrics


def _node_exporter_endpoint(instance):
    extra = instance.get("extra_json") if isinstance(instance.get("extra_json"), dict) else {}
    config = extra.get("node_exporter") if isinstance(extra.get("node_exporter"), dict) else {}
    enabled = _as_bool(config.get("enabled"), default=True)
    mode = str(config.get("mode") or "same_host").strip().lower()
    if mode == "custom":
        endpoint = str(config.get("address") or "").strip()
        if endpoint and not endpoint.startswith(("http://", "https://")):
            endpoint = f"http://{endpoint}"
    else:
        host = instance.get("resolved_ip") or instance.get("host_input") or ""
        try:
            port = int(config.get("port") or 9100)
        except (TypeError, ValueError):
            port = 9100
        endpoint = f"http://{host}:{port}" if host else ""
    if endpoint and not endpoint.endswith("/metrics"):
        endpoint = endpoint.rstrip("/") + "/metrics"
    return enabled, endpoint


def _collect_host_metrics(instance):
    enabled, endpoint = _node_exporter_endpoint(instance)
    result = {
        "node_exporter_enabled": enabled,
        "node_exporter_endpoint": endpoint,
        "node_exporter_status": "disabled" if not enabled else "unknown",
        "node_exporter_error": None,
        "host_cpu_usage_pct": None,
        "host_memory_usage_pct": None,
        "host_data_disk_usage_pct": None,
        "host_data_disk_mountpoint": None,
        "host_data_disk_device": None,
        "host_net_rates": [],
    }
    if not enabled:
        return result
    if not endpoint:
        result.update({"node_exporter_status": "error", "node_exporter_error": "node_exporter endpoint is empty"})
        return result
    try:
        with urlopen(Request(endpoint, headers={"User-Agent": "dbms-agent/1.0"}), timeout=2) as response:
            metrics = _metric_rows(response.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        result.update({"node_exporter_status": "error", "node_exporter_error": f"node_exporter collect failed: {exc}"})
        return result

    cpu_rows = metrics.get("node_cpu_seconds_total", [])
    total = sum(value for _labels, value in cpu_rows)
    idle = sum(value for labels, value in cpu_rows if labels.get("mode") == "idle")
    if total > 0:
        result["host_cpu_usage_pct"] = round(max(0.0, min((1 - idle / total) * 100, 100.0)), 2)

    def single(name):
        rows = metrics.get(name) or []
        return rows[0][1] if rows else None
    memory_total = single("node_memory_MemTotal_bytes")
    memory_available = single("node_memory_MemAvailable_bytes")
    if memory_total and memory_available is not None:
        result["host_memory_usage_pct"] = round(max(0.0, min((memory_total - memory_available) / memory_total * 100, 100.0)), 2)

    available_by_key = {
        (labels.get("device"), labels.get("mountpoint")): value
        for labels, value in metrics.get("node_filesystem_avail_bytes", [])
    }
    disks = []
    for labels, size in metrics.get("node_filesystem_size_bytes", []):
        mountpoint = labels.get("mountpoint") or ""
        device = labels.get("device") or ""
        fstype = labels.get("fstype") or ""
        if not size or not mountpoint or mountpoint.startswith(("/proc", "/sys", "/dev", "/run")):
            continue
        if fstype in {"tmpfs", "devtmpfs", "overlay", "squashfs"}:
            continue
        available = available_by_key.get((device, mountpoint))
        if available is not None:
            disks.append((size, device, mountpoint, round(max(0.0, min((size - available) / size * 100, 100.0)), 2)))
    if disks:
        _size, device, mountpoint, usage = max(disks, key=lambda item: item[0])
        result.update({
            "host_data_disk_usage_pct": usage,
            "host_data_disk_device": device,
            "host_data_disk_mountpoint": mountpoint,
        })

    now = time.time()
    rx = {labels.get("device"): value for labels, value in metrics.get("node_network_receive_bytes_total", []) if labels.get("device") != "lo"}
    tx = {labels.get("device"): value for labels, value in metrics.get("node_network_transmit_bytes_total", []) if labels.get("device") != "lo"}
    previous = HOST_RATE_CACHE.get(endpoint)
    HOST_RATE_CACHE[endpoint] = {"time": now, "rx": rx, "tx": tx}
    if previous and now > previous["time"]:
        elapsed = now - previous["time"]
        for device in sorted(set(rx) | set(tx)):
            old_rx = previous["rx"].get(device)
            old_tx = previous["tx"].get(device)
            rx_bps = (rx.get(device) - old_rx) / elapsed if rx.get(device) is not None and old_rx is not None else None
            tx_bps = (tx.get(device) - old_tx) / elapsed if tx.get(device) is not None and old_tx is not None else None
            result["host_net_rates"].append({
                "device": device,
                "rx_bps": round(rx_bps, 2) if rx_bps is not None and rx_bps >= 0 else None,
                "tx_bps": round(tx_bps, 2) if tx_bps is not None and tx_bps >= 0 else None,
            })
    result["node_exporter_status"] = "ok"
    return result


def _mysql(instance, password):
    import pymysql

    warnings = []
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
            def status_value(key):
                try:
                    cursor.execute(f"SHOW GLOBAL STATUS LIKE '{key}'")
                    item = cursor.fetchone()
                    return item[1] if item else None
                except Exception as exc:
                    warnings.append(f"status:{key}:{exc}")
                    return None

            def variable_value(key):
                try:
                    cursor.execute(f"SHOW GLOBAL VARIABLES LIKE '{key}'")
                    item = cursor.fetchone()
                    return item[1] if item else None
                except Exception as exc:
                    warnings.append(f"variable:{key}:{exc}")
                    return None

            cursor.execute("SELECT 1, VERSION()")
            row = cursor.fetchone()
            ping_ok = bool(row and row[0] == 1)
            version = row[1] if row else None
            read_only = _bool_flag(variable_value("read_only"))
            super_read_only = _bool_flag(variable_value("super_read_only"))
            effective_read_only = None if read_only is None and super_read_only is None else bool(read_only is True or super_read_only is True)

            uptime = _safe_int(status_value("Uptime"))
            threads_connected = _safe_int(status_value("Threads_connected"))
            threads_running = _safe_int(status_value("Threads_running"))
            max_connections = _safe_int(variable_value("max_connections"))
            questions_total = _safe_int(status_value("Questions"))
            com_commit_total = _safe_int(status_value("Com_commit"))
            com_rollback_total = _safe_int(status_value("Com_rollback"))
            lock_waits = _safe_int(status_value("Innodb_row_lock_current_waits"))
            qps = round(questions_total / uptime, 3) if uptime and questions_total is not None else None
            tps = None
            if uptime and (com_commit_total is not None or com_rollback_total is not None):
                tps = round(((com_commit_total or 0) + (com_rollback_total or 0)) / uptime, 3)

            payload = {
                "ok": ping_ok,
                "ping_ok": ping_ok,
                "db_type": "mysql",
                "version": version,
                "uptime": uptime,
                "started_at": (datetime.now() - timedelta(seconds=uptime)).isoformat() if uptime is not None else None,
                "threads_connected": threads_connected,
                "threads_running": threads_running,
                "max_connections": max_connections,
                "questions_total": questions_total,
                "com_commit_total": com_commit_total,
                "com_rollback_total": com_rollback_total,
                "qps": qps,
                "tps": tps,
                "lock_waits": lock_waits,
                "read_only": read_only,
                "super_read_only": super_read_only,
                "effective_read_only": effective_read_only,
                "replication_role": "unknown",
                "replica_io_running": None,
                "replica_sql_running": None,
                "seconds_behind_master": None,
                "replica_source_host": None,
                "replica_source_resolved_ip": None,
                "replica_source_port": None,
            }

            for command in ("SHOW REPLICA STATUS", "SHOW SLAVE STATUS"):
                try:
                    cursor.execute(command)
                    repl = cursor.fetchone()
                    if not repl:
                        continue
                    desc = [item[0] for item in cursor.description]
                    data = dict(zip(desc, repl))
                    source_host = data.get("Source_Host", data.get("Master_Host"))
                    payload.update({
                        "replication_role": "slave",
                        "replica_io_running": _bool_flag(data.get("Replica_IO_Running", data.get("Slave_IO_Running"))),
                        "replica_sql_running": _bool_flag(data.get("Replica_SQL_Running", data.get("Slave_SQL_Running"))),
                        "seconds_behind_master": _safe_int(data.get("Seconds_Behind_Source", data.get("Seconds_Behind_Master"))),
                        "replica_source_host": source_host,
                        "replica_source_resolved_ip": _resolve_host(source_host),
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
                members = []
                for item in cursor.fetchall() or []:
                    member = dict(zip(desc, item))
                    member["member_port"] = _safe_int(member.get("member_port"))
                    members.append(member)
                payload["mgr_members"] = members
                cursor.execute("SELECT @@server_uuid, @@group_replication_group_name")
                group_row = cursor.fetchone()
                server_uuid = str(group_row[0] or "").strip() if group_row else ""
                payload["mgr_group_name"] = str(group_row[1] or "").strip() or None if group_row else None
                local = next((item for item in members if str(item.get("member_id") or "").strip() == server_uuid), None)
                if local:
                    payload["mgr_member_role"] = str(local.get("member_role") or "").upper() or None
                    payload["mgr_member_state"] = str(local.get("member_state") or "").upper() or None
                    if payload["mgr_member_role"] == "PRIMARY":
                        payload["replication_role"] = "mgr_primary"
                    elif payload["mgr_member_role"] == "SECONDARY":
                        payload["replication_role"] = "mgr_secondary"
            except Exception:
                payload["mgr_members"] = []

            if payload["replication_role"] not in {"slave", "mgr_primary", "mgr_secondary"}:
                if effective_read_only is True:
                    payload["replication_role"] = "read_only"
                elif effective_read_only is False:
                    payload["replication_role"] = "master"
            payload["warnings"] = warnings
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
    cluster_info = {}
    try:
        cluster_info = client.execute_command("CLUSTER INFO") or {}
    except Exception:
        pass
    return {
        "ok": ping_ok,
        "ping_ok": ping_ok,
        "db_type": "redis",
        "version": info.get("redis_version"),
        "redis_version": info.get("redis_version"),
        "redis_mode": info.get("redis_mode"),
        "cluster_enabled": _safe_int(info.get("cluster_enabled")),
        "cluster_state": cluster_info.get("cluster_state") if isinstance(cluster_info, dict) else None,
        "cluster_info": cluster_info,
        "uptime": _safe_int(info.get("uptime_in_seconds")),
        "connected_clients": _safe_int(info.get("connected_clients")),
        "used_memory": _safe_int(info.get("used_memory")),
        "role": replication.get("role"),
        "master_host": replication.get("master_host"),
        "master_port": _safe_int(replication.get("master_port")),
        "master_link_status": replication.get("master_link_status"),
    }


def _mongo_repl_lag_seconds(repl_status):
    try:
        primary_optime = None
        self_optime = None
        for member in repl_status.get("members") or []:
            optime = member.get("optimeDate") or (member.get("optime") or {}).get("ts")
            if member.get("stateStr") == "PRIMARY":
                primary_optime = optime
            if member.get("self") is True:
                self_optime = optime
        if isinstance(primary_optime, datetime) and isinstance(self_optime, datetime):
            return max(0, int((primary_optime - self_optime).total_seconds()))
    except Exception:
        pass
    return None


def _mongo_cache_used_pct(status):
    cache = (status.get("wiredTiger") or {}).get("cache") or {}
    try:
        used = float(cache.get("bytes currently in the cache"))
        maximum = float(cache.get("maximum bytes configured"))
        return round(used / maximum * 100, 2) if maximum > 0 else None
    except (TypeError, ValueError):
        return None


def _mongodb(instance, password):
    from pymongo import MongoClient

    host = instance.get("resolved_ip") or instance.get("host_input")
    port = int(instance.get("port") or 27017)
    username = instance.get("username") or None
    extra = instance.get("extra_json") if isinstance(instance.get("extra_json"), dict) else {}
    auth_source = str(extra.get("auth_source") or extra.get("auth_db") or "admin").strip()
    auth_mechanism = str(extra.get("auth_mechanism") or "").strip()
    direct_connection = _as_bool(extra.get("direct_connection"), default=False)
    tls_enabled = _as_bool(extra.get("tls", extra.get("ssl")), default=False)
    options = {
        "serverSelectionTimeoutMS": 3000,
        "connectTimeoutMS": 3000,
        "socketTimeoutMS": 3000,
        "directConnection": direct_connection,
        "tls": tls_enabled,
        "appname": "dbms-agent-monitor",
    }
    if username and password:
        options.update({"username": username, "password": password, "authSource": auth_source})
        if auth_mechanism and auth_mechanism.lower() not in {"auto", "default", "none"}:
            options["authMechanism"] = auth_mechanism

    client = MongoClient(host, port, **options)
    try:
        ping = client.admin.command("ping")
        info = client.server_info()
        status = client.admin.command("serverStatus")
        try:
            hello = client.admin.command("hello")
        except Exception:
            hello = client.admin.command("isMaster")

        connections = status.get("connections") or {}
        current = _safe_int(connections.get("current"))
        available = _safe_int(connections.get("available"))
        maximum = current + available if current is not None and available is not None else None
        opcounters = status.get("opcounters") or {}
        op_insert = _safe_int(opcounters.get("insert"))
        op_query = _safe_int(opcounters.get("query"))
        op_update = _safe_int(opcounters.get("update"))
        op_delete = _safe_int(opcounters.get("delete"))
        op_getmore = _safe_int(opcounters.get("getmore"))
        op_read = (op_query or 0) + (op_getmore or 0)
        op_write = (op_insert or 0) + (op_update or 0) + (op_delete or 0)
        total_ops = op_read + op_write

        process = status.get("process")
        role = None
        topology = "standalone"
        if hello.get("msg") == "isdbgrid" or process == "mongos":
            role, topology = "mongos", "mongos"
        elif hello.get("configsvr"):
            role, topology = "configsvr", "configsvr"
        elif hello.get("arbiterOnly") is True:
            role = "arbiter"
        elif hello.get("isWritablePrimary") is True or hello.get("ismaster") is True:
            role = "primary"
        elif hello.get("secondary") is True:
            role = "secondary"
        if hello.get("setName") and topology == "standalone":
            topology = "replica_set"

        repl_status = None
        repl_config = None
        repl_summary = {"set": hello.get("setName"), "myState": None, "members": len(hello.get("hosts") or [])}
        repl_lag_seconds = None
        try:
            repl_status = client.admin.command("replSetGetStatus")
            repl_summary["set"] = repl_status.get("set") or repl_summary["set"]
            repl_summary["myState"] = repl_status.get("myState")
            repl_summary["members"] = len(repl_status.get("members") or [])
            repl_lag_seconds = _mongo_repl_lag_seconds(repl_status)
            state_roles = {1: "primary", 2: "secondary", 7: "arbiter"}
            role = state_roles.get(repl_status.get("myState"), role)
        except Exception:
            pass
        try:
            repl_config = client.admin.command("replSetGetConfig")
        except Exception:
            pass

        uptime = _safe_int(status.get("uptime"))
        return {
            "ok": ping.get("ok") == 1.0,
            "ping_ok": ping.get("ok") == 1.0,
            "db_type": "mongodb",
            "version": info.get("version"),
            "process": process,
            "mongo_role": role,
            "mongo_topology": topology,
            "started_at": (datetime.now() - timedelta(seconds=uptime)).isoformat() if uptime is not None else None,
            "uptime": uptime,
            "connections_current": current,
            "connections_max": maximum,
            "lock_waits": _safe_int(((status.get("globalLock") or {}).get("currentQueue") or {}).get("total")),
            "repl_lag_seconds": repl_lag_seconds,
            "op_insert": op_insert,
            "op_query": op_query,
            "op_update": op_update,
            "op_delete": op_delete,
            "op_read": op_read,
            "op_write": op_write,
            "op_read_pct": round(op_read / total_ops * 100, 2) if total_ops > 0 else None,
            "op_write_pct": round(op_write / total_ops * 100, 2) if total_ops > 0 else None,
            "cache_used_pct": _mongo_cache_used_pct(status),
            "connections": connections,
            "mem": status.get("mem") or {},
            "repl": {
                **repl_summary,
                "rs_status": _bson_to_json(repl_status),
                "rs_conf": _bson_to_json(repl_config),
            },
        }
    finally:
        client.close()


def _postgresql(instance, password):
    import psycopg2

    extra = instance.get("extra_json") if isinstance(instance.get("extra_json"), dict) else {}
    conn = psycopg2.connect(
        host=instance.get("resolved_ip") or instance.get("host_input"),
        port=int(instance.get("port") or 5432),
        user=instance.get("username") or "",
        password=password or "",
        dbname=extra.get("database") or extra.get("dbname") or "postgres",
        sslmode=extra.get("sslmode") or "prefer",
        connect_timeout=3,
        options="-c statement_timeout=3000",
    )
    conn.autocommit = True
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT version(), current_database(), pg_is_in_recovery(), "
                "EXTRACT(EPOCH FROM (now() - pg_postmaster_start_time()))::bigint, "
                "current_setting('max_connections')::int"
            )
            base = cursor.fetchone()
            in_recovery = bool(base[2])
            cursor.execute(
                "SELECT count(*)::bigint, "
                "count(*) FILTER (WHERE state = 'active')::bigint, "
                "count(*) FILTER (WHERE wait_event_type = 'Lock')::bigint "
                "FROM pg_stat_activity"
            )
            activity = cursor.fetchone() or (None, None, None)
            connections = _safe_int(activity[0])
            max_connections = _safe_int(base[4])
            lag = None
            lag_bytes = receive_lag_bytes = replay_lag_bytes = None
            wal_source_lsn = wal_receive_lsn = wal_replay_lsn = wal_current_lsn = None
            wal_receiver_status = wal_last_message_at = None
            replay_paused = False
            replica_count = 0
            if in_recovery:
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
                    " pg_is_wal_replay_paused(), last_message_at FROM positions"
                )
                repl = cursor.fetchone()
                if repl:
                    wal_receiver_status, wal_source_lsn, wal_receive_lsn, wal_replay_lsn = repl[:4]
                    lag_bytes = _safe_int(repl[4])
                    receive_lag_bytes = _safe_int(repl[5])
                    replay_lag_bytes = _safe_int(repl[6])
                    lag = round(float(repl[7]), 3) if repl[7] is not None else None
                    replay_paused = bool(repl[8])
                    wal_last_message_at = repl[9].isoformat() if hasattr(repl[9], "isoformat") else repl[9]
            else:
                cursor.execute(
                    "SELECT pg_current_wal_lsn()::text, "
                    "count(*) FILTER (WHERE state = 'streaming')::bigint FROM pg_stat_replication"
                )
                repl = cursor.fetchone()
                wal_current_lsn = repl[0] if repl else None
                replica_count = _safe_int(repl[1]) if repl else 0
            cursor.execute(
                "SELECT xact_commit, xact_rollback, deadlocks, pg_database_size(datname) "
                "FROM pg_stat_database WHERE datname = current_database()"
            )
            stats = cursor.fetchone() or (None, None, None, None)
            return {
                "ok": True,
                "ping_ok": True,
                "db_type": "postgresql",
                "version": base[0],
                "database": base[1],
                "uptime": _safe_int(base[3]),
                "replication_role": "standby" if in_recovery else "primary",
                "in_recovery": in_recovery,
                "replication_lag_seconds": lag,
                "replication_lag_bytes": lag_bytes,
                "receive_lag_bytes": receive_lag_bytes,
                "replay_lag_bytes": replay_lag_bytes,
                "wal_current_lsn": wal_current_lsn,
                "wal_source_lsn": wal_source_lsn,
                "wal_receive_lsn": wal_receive_lsn,
                "wal_replay_lsn": wal_replay_lsn,
                "wal_receiver_status": wal_receiver_status,
                "wal_last_message_at": wal_last_message_at,
                "replay_paused": replay_paused,
                "replica_count": replica_count,
                "connections": connections,
                "active_connections": _safe_int(activity[1]),
                "lock_waiting_connections": _safe_int(activity[2]),
                "max_connections": max_connections,
                "connection_usage_pct": round(connections * 100 / max_connections, 2) if max_connections and connections is not None else None,
                "xact_commit": _safe_int(stats[0]),
                "xact_rollback": _safe_int(stats[1]),
                "deadlocks": _safe_int(stats[2]),
                "database_size_bytes": _safe_int(stats[3]),
            }
    finally:
        conn.close()


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


COLLECTORS = {"mysql": _mysql, "redis": _redis, "mongodb": _mongodb, "postgresql": _postgresql, "doris": _doris}


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
