from collections import Counter, defaultdict
from datetime import datetime, timezone

from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.services.monitor_snapshot_service import latest_snapshots_by_instance_ids


STALE_SECONDS = 600
DB_TYPES = {"mysql", "mongodb", "redis", "doris"}


def _iso(value):
    return value.isoformat() if value else None


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _age_seconds(value):
    if not value:
        return None
    now = datetime.now(value.tzinfo or timezone.utc)
    base = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return max(int((now - base).total_seconds()), 0)


def _pick(payload, *keys):
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return value
    return None


def _role(instance, payload):
    if instance.db_type == "mysql":
        return _pick(payload, "replication_role", "role") or instance.role_label
    if instance.db_type == "mongodb":
        return _pick(payload, "mongo_role", "role", "topology") or instance.role_label
    if instance.db_type == "redis":
        return _pick(payload, "role", "redis_role") or instance.role_label
    return _pick(payload, "role") or instance.role_label


def _version(instance, payload):
    if instance.db_type == "redis":
        return _pick(payload, "redis_version", "version")
    return _pick(payload, "version", "server_version")


def _metrics(payload):
    keys = [
        "host_cpu_usage_pct",
        "host_memory_usage_pct",
        "host_data_disk_usage_pct",
        "connections_current",
        "connections_usage_pct",
        "seconds_behind_master",
        "replication_lag_seconds",
        "cache_used_pct",
        "memory_usage_pct",
        "used_memory",
        "maxmemory",
        "connected_clients",
        "keyspace_total_keys",
        "read_only",
        "effective_read_only",
    ]
    return {key: payload.get(key) for key in keys if key in payload}


def _alerts(instance, payload, snapshot, status, age):
    alerts = []
    if status in {"down", "error"}:
        alerts.append("instance_unreachable")
    if payload.get("error"):
        alerts.append("collector_error")
    if payload.get("node_exporter_error"):
        alerts.append("node_exporter_error")
    if snapshot is None:
        alerts.append("no_status_snapshot")
    elif age is not None and age > STALE_SECONDS:
        alerts.append("stale_status_snapshot")

    for key in ("host_cpu_usage_pct", "host_memory_usage_pct", "host_data_disk_usage_pct", "memory_usage_pct"):
        value = _to_float(payload.get(key))
        if value is not None and value >= 90:
            alerts.append(f"high_{key}")

    lag = _to_float(_pick(payload, "seconds_behind_master", "replication_lag_seconds"))
    if lag is not None and lag >= 60:
        alerts.append("replication_lag")
    return alerts


def _status(instance, payload, snapshot):
    raw = str(instance.running_status or "").strip().lower()
    if raw in {"running", "up", "online"}:
        status = "running"
    elif raw in {"down", "error", "offline"}:
        status = "down"
    elif payload.get("ping_ok") is True or payload.get("ok") is True:
        status = "running"
    elif payload.get("error"):
        status = "error"
    elif snapshot:
        status = "unknown"
    else:
        status = raw or "unknown"
    return status


def _cluster_data(cluster):
    if not cluster:
        return None
    return {
        "id": cluster.id,
        "name": cluster.name,
        "db_type": cluster.db_type,
        "business_line": cluster.business_line or cluster.namespace,
        "environment": cluster.environment,
        "ha_domain": cluster.ha_domain,
        "ha_switch_enabled": bool(cluster.ha_switch_enabled),
    }


def build_mcp_instance_status(filters=None, allowed_cluster_ids=None):
    filters = filters or {}
    query = DatabaseInstance.query
    db_type = (filters.get("db_type") or "").strip().lower()
    if db_type in DB_TYPES:
        query = query.filter(DatabaseInstance.db_type == db_type)
    if allowed_cluster_ids is not None:
        if not allowed_cluster_ids:
            return _empty_result(filters)
        query = query.filter(DatabaseInstance.cluster_id.in_(allowed_cluster_ids))
    if filters.get("cluster_id"):
        query = query.filter(DatabaseInstance.cluster_id == int(filters["cluster_id"]))
    if filters.get("enabled") is not None:
        query = query.filter(DatabaseInstance.enabled == bool(filters["enabled"]))

    instances = query.order_by(DatabaseInstance.db_type.asc(), DatabaseInstance.id.asc()).all()
    cluster_ids = sorted({item.cluster_id for item in instances if item.cluster_id})
    clusters = {item.id: item for item in DatabaseCluster.query.filter(DatabaseCluster.id.in_(cluster_ids)).all()} if cluster_ids else {}
    instances = _filter_by_cluster_fields(instances, clusters, filters)

    snapshots_by_type = {}
    for item_db_type in sorted({item.db_type for item in instances}):
        ids = [item.id for item in instances if item.db_type == item_db_type]
        snapshots_by_type[item_db_type] = latest_snapshots_by_instance_ids(item_db_type, ids, "status")

    items = []
    for instance in instances:
        snapshot = snapshots_by_type.get(instance.db_type, {}).get(instance.id)
        payload = snapshot.payload_json if snapshot and isinstance(snapshot.payload_json, dict) else {}
        age = _age_seconds(snapshot.collected_at) if snapshot else None
        status = _status(instance, payload, snapshot)
        alerts = _alerts(instance, payload, snapshot, status, age)
        if filters.get("status") and status != filters["status"]:
            continue
        if filters.get("unhealthy_only") and not alerts and status == "running":
            continue
        row = {
            "id": instance.id,
            "name": instance.name,
            "db_type": instance.db_type,
            "host": instance.host_input,
            "resolved_ip": instance.resolved_ip,
            "port": instance.port,
            "username": instance.username,
            "enabled": bool(instance.enabled),
            "configured_role": instance.role_label,
            "detected_role": _role(instance, payload),
            "is_read_only": bool(instance.is_read_only),
            "status": status,
            "version": _version(instance, payload),
            "cluster": _cluster_data(clusters.get(instance.cluster_id)),
            "metrics": _metrics(payload),
            "alerts": alerts,
            "latest_snapshot": {
                "id": snapshot.id if snapshot else None,
                "metric_type": snapshot.metric_type if snapshot else None,
                "collected_at": _iso(snapshot.collected_at) if snapshot else None,
                "age_seconds": age,
            },
            "updated_at": _iso(instance.updated_at),
        }
        if filters.get("include_raw_payload"):
            row["raw_payload"] = payload
        items.append(row)

    return _with_summary(items, filters)


def _filter_by_cluster_fields(instances, clusters, filters):
    business_line = (filters.get("business_line") or "").strip()
    environment = (filters.get("environment") or "").strip()
    cluster_name = (filters.get("cluster_name") or "").strip()
    if not business_line and not environment and not cluster_name:
        return instances
    result = []
    for instance in instances:
        cluster = clusters.get(instance.cluster_id)
        if cluster_name and (not cluster or cluster.name != cluster_name):
            continue
        if business_line and (not cluster or (cluster.business_line or cluster.namespace) != business_line):
            continue
        if environment and (not cluster or cluster.environment != environment):
            continue
        result.append(instance)
    return result


def _empty_result(filters):
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "filters": filters,
        "summary": {
            "total": 0,
            "by_db_type": {},
            "by_status": {},
            "alert_total": 0,
            "unhealthy_total": 0,
        },
        "instances": [],
    }


def _with_summary(items, filters):
    by_db_type = Counter(item["db_type"] for item in items)
    by_status = Counter(item["status"] for item in items)
    by_cluster = defaultdict(int)
    alert_total = 0
    unhealthy_total = 0
    for item in items:
        cluster = item.get("cluster") or {}
        if cluster.get("name"):
            by_cluster[cluster["name"]] += 1
        if item["alerts"]:
            alert_total += 1
        if item["status"] != "running" or item["alerts"]:
            unhealthy_total += 1

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "filters": filters,
        "summary": {
            "total": len(items),
            "by_db_type": dict(by_db_type),
            "by_status": dict(by_status),
            "by_cluster": dict(by_cluster),
            "alert_total": alert_total,
            "unhealthy_total": unhealthy_total,
        },
        "instances": items,
    }
