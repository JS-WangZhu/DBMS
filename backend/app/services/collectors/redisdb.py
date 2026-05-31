from datetime import datetime

from app.services.collectors.node_exporter import collect_node_exporter_metrics


def _safe_int(value):
    try:
        return int(value)
    except Exception:
        return None


def _resolve_redis_role(info: dict):
    role = str(info.get("role") or "").strip().lower()
    if role in {"master", "slave", "replica"}:
        return "slave" if role == "replica" else role
    master_host = info.get("master_host")
    if master_host:
        return "slave"
    if _safe_int(info.get("connected_slaves")) not in (None, 0):
        return "master"
    return "unknown"


def _memory_usage_pct(used_memory, maxmemory):
    used = _safe_int(used_memory)
    max_mem = _safe_int(maxmemory)
    if used is None or max_mem is None or max_mem <= 0:
        return None
    return round(max(0.0, min((used / max_mem) * 100, 100.0)), 2)


def _connection_usage_pct(connected_clients, maxclients):
    connected = _safe_int(connected_clients)
    max_clients = _safe_int(maxclients)
    if connected is None or max_clients is None or max_clients <= 0:
        return None
    return round(max(0.0, min((connected / max_clients) * 100, 100.0)), 2)


def _key_count_total(info: dict):
    total = 0
    db_count = 0
    for key, value in (info or {}).items():
        if not str(key).startswith("db"):
            continue
        if not isinstance(value, dict):
            continue
        keys = _safe_int(value.get("keys"))
        if keys is None:
            continue
        db_count += 1
        total += keys
    return total, db_count


def collect_redis_status(instance, password):
    host_metrics = collect_node_exporter_metrics(instance)
    try:
        import redis

        client = redis.Redis(
            host=instance.resolved_ip or instance.host_input,
            port=instance.port,
            password=password,
            socket_connect_timeout=3,
            socket_timeout=3,
            decode_responses=True,
        )

        info = client.info()

        cluster_info = {}
        try:
            cluster_info = client.execute_command("CLUSTER INFO")
        except Exception:
            cluster_info = {}

        maxclients = _safe_int(info.get("maxclients"))
        if maxclients is None:
            try:
                maxclients = _safe_int((client.config_get("maxclients") or {}).get("maxclients"))
            except Exception:
                maxclients = None

        redis_role = _resolve_redis_role(info)
        used_memory = _safe_int(info.get("used_memory"))
        maxmemory = _safe_int(info.get("maxmemory"))
        connected_clients = _safe_int(info.get("connected_clients"))
        total_keys, keyspace_db_count = _key_count_total(info)
        master_host = info.get("master_host")
        master_port = info.get("master_port")
        replication_source = None
        if master_host:
            replication_source = f"{master_host}:{master_port}" if master_port not in (None, "") else str(master_host)
        replication_lag_seconds = _safe_int(info.get("master_last_io_seconds_ago"))

        return {
            "ok": True,
            "ping_ok": True,
            "db_type": "redis",
            "collected_at": datetime.now().isoformat(),
            "version": info.get("redis_version"),
            "redis_version": info.get("redis_version"),
            "redis_mode": info.get("redis_mode"),
            "cluster_enabled": _safe_int(info.get("cluster_enabled")),
            "role": redis_role,
            "master_host": master_host,
            "master_port": master_port,
            "replication_source": replication_source,
            "replication_lag_seconds": replication_lag_seconds,
            "master_link_status": info.get("master_link_status"),
            "connected_slaves": info.get("connected_slaves"),
            "connected_clients": connected_clients,
            "maxclients": maxclients,
            "connection_usage_pct": _connection_usage_pct(connected_clients, maxclients),
            "used_memory": used_memory,
            "used_memory_human": info.get("used_memory_human"),
            "maxmemory": maxmemory,
            "maxmemory_human": info.get("maxmemory_human"),
            "memory_usage_pct": _memory_usage_pct(used_memory, maxmemory),
            "used_memory_peak": _safe_int(info.get("used_memory_peak")),
            "used_memory_peak_human": info.get("used_memory_peak_human"),
            "keyspace_total_keys": total_keys,
            "keyspace_db_count": keyspace_db_count,
            "keyspace_hits": info.get("keyspace_hits"),
            "keyspace_misses": info.get("keyspace_misses"),
            "cluster_info": cluster_info,
            **host_metrics,
        }
    except Exception as exc:
        return {"ok": False, "error": f"redis collect failed: {exc}"}
