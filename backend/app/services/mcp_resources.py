from collections import Counter
from datetime import datetime, timedelta

from app.extensions import db
from app.models.backup import BackupLog, BackupPolicy, _utc_isoformat
from app.models.backup_agent import AgentInspectionStatus, BackupAgent
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.models.inspection import InspectionAlert, InspectionConfig
from app.services.inspection_service import DEFAULT_THRESHOLDS, _thresholds_from_config


BACKUP_DB_TYPES = {"mysql", "mongodb", "postgresql"}
INSPECTION_ITEM_DEFINITIONS = (
    ("collect_failed", "common", "采集结果有效性", None, None),
    ("connectivity", "common", "数据库连通性", None, None),
    ("ping_failed", "common", "数据库探活", None, None),
    ("host_cpu_high", "host", "主机 CPU 使用率", "host_cpu_usage_pct", "percent"),
    ("host_memory_high", "host", "主机内存使用率", "host_memory_usage_pct", "percent"),
    ("host_disk_high", "host", "主机数据盘使用率", "host_data_disk_usage_pct", "percent"),
    ("host_disk_io_latency", "host", "主机磁盘 I/O 延迟", "host_disk_io_latency_ms", "milliseconds"),
    ("mysql_replica_thread", "mysql", "MySQL 复制线程状态", None, None),
    ("mysql_replication_lag", "mysql", "MySQL 复制延迟", "mysql_replication_lag_seconds", "seconds"),
    ("mysql_connection_high", "mysql", "MySQL 连接使用率", "mysql_connection_usage_pct", "percent"),
    ("mysql_aborted_connects", "mysql", "MySQL 新连接握手失败", "mysql_aborted_connects_10m", "count_per_10m"),
    ("mongodb_replication_lag", "mongodb", "MongoDB 复制延迟", "mongodb_repl_lag_seconds", "seconds"),
    ("mongodb_cache_high", "mongodb", "MongoDB 缓存使用率", "mongodb_cache_used_pct", "percent"),
    ("redis_cluster_state", "redis", "Redis 集群状态", None, None),
    ("redis_memory_high", "redis", "Redis 内存使用率", "redis_memory_usage_pct", "percent"),
    ("redis_connection_high", "redis", "Redis 连接使用率", "redis_connection_usage_pct", "percent"),
    ("redis_blocked_clients", "redis", "Redis 阻塞客户端", "redis_blocked_clients_10m", "count"),
    ("redis_replication_link", "redis", "Redis 主从链路状态", None, None),
    ("postgresql_connection_high", "postgresql", "PostgreSQL 连接使用率", "postgresql_connection_usage_pct", "percent"),
    ("postgresql_sessions_fatal", "postgresql", "PostgreSQL 异常连接终止", "postgresql_sessions_fatal_10m", "count_per_10m"),
    ("postgresql_replication_receiver", "postgresql", "PostgreSQL WAL Receiver 状态", None, None),
    ("postgresql_replay_paused", "postgresql", "PostgreSQL 复制回放状态", None, None),
    ("postgresql_replication_lag", "postgresql", "PostgreSQL 复制延迟", "postgresql_replication_lag_seconds", "seconds"),
    ("postgresql_lock_wait", "postgresql", "PostgreSQL 锁等待", None, None),
    ("agent_health", "agent", "Agent 健康状态", None, None),
)


def _visible_clusters_and_instances(allowed_cluster_ids=None, include_disabled=True):
    cluster_query = DatabaseCluster.query
    instance_query = DatabaseInstance.query
    if allowed_cluster_ids is not None:
        ids = [int(item) for item in (allowed_cluster_ids or [])]
        if not ids:
            return [], []
        cluster_query = cluster_query.filter(DatabaseCluster.id.in_(ids))
        instance_query = instance_query.filter(DatabaseInstance.cluster_id.in_(ids))
    if not include_disabled:
        instance_query = instance_query.filter(DatabaseInstance.enabled.is_(True))
    clusters = cluster_query.order_by(DatabaseCluster.db_type.asc(), DatabaseCluster.id.asc()).all()
    instances = instance_query.order_by(DatabaseInstance.db_type.asc(), DatabaseInstance.id.asc()).all()
    return clusters, instances


def _instance_mapping_row(instance):
    return {
        "id": instance.id,
        "name": instance.name,
        "db_type": instance.db_type,
        "host": instance.host_input,
        "resolved_ip": instance.resolved_ip,
        "port": instance.port,
        "configured_role": instance.role_label,
        "is_read_only": bool(instance.is_read_only),
        "enabled": bool(instance.enabled),
        "running_status": instance.running_status,
        "access_mode": instance.access_mode if instance.access_mode in {"server", "agent"} else "server",
    }


def build_mcp_cluster_instance_map(filters=None, allowed_cluster_ids=None):
    filters = filters or {}
    clusters, instances = _visible_clusters_and_instances(
        allowed_cluster_ids=allowed_cluster_ids,
        include_disabled=not filters.get("enabled_only"),
    )
    db_type = str(filters.get("db_type") or "").strip().lower()
    if db_type:
        clusters = [row for row in clusters if row.db_type == db_type]
        instances = [row for row in instances if row.db_type == db_type]
    if filters.get("cluster_id"):
        cluster_id = int(filters["cluster_id"])
        clusters = [row for row in clusters if row.id == cluster_id]
        instances = [row for row in instances if row.cluster_id == cluster_id]

    instances_by_cluster = {}
    unassigned = []
    for instance in instances:
        if instance.cluster_id:
            instances_by_cluster.setdefault(instance.cluster_id, []).append(_instance_mapping_row(instance))
        else:
            unassigned.append(_instance_mapping_row(instance))

    items = []
    for cluster in clusters:
        cluster_instances = instances_by_cluster.get(cluster.id, [])
        items.append({
            "cluster_id": cluster.id,
            "cluster_name": cluster.name,
            "db_type": cluster.db_type,
            "business_line": cluster.business_line or cluster.namespace,
            "environment": cluster.environment,
            "description": cluster.description,
            "ha_domain": cluster.ha_domain,
            "ha_mode": cluster.ha_mode if cluster.ha_mode in {"none", "orc", "dbms"} else "none",
            "instance_count": len(cluster_instances),
            "instances": cluster_instances,
        })
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "filters": filters,
        "summary": {
            "cluster_total": len(items),
            "instance_total": sum(item["instance_count"] for item in items) + len(unassigned),
            "unassigned_instance_total": len(unassigned),
        },
        "clusters": items,
        "unassigned_instances": unassigned,
    }


def _latest_backup_row(log):
    if not log:
        return None
    return {
        "log_id": log.id,
        "status": log.status,
        "started_at": _utc_isoformat(log.started_at),
        "finished_at": _utc_isoformat(log.finished_at),
        "size_bytes": log.size_bytes,
        "error_message": log.error_message,
    }


def build_mcp_backup_status(filters=None, allowed_cluster_ids=None):
    filters = filters or {}
    _, instances = _visible_clusters_and_instances(allowed_cluster_ids=allowed_cluster_ids, include_disabled=True)
    instances = [row for row in instances if row.db_type in BACKUP_DB_TYPES]
    db_type = str(filters.get("db_type") or "").strip().lower()
    if db_type:
        instances = [row for row in instances if row.db_type == db_type]
    if filters.get("cluster_id"):
        instances = [row for row in instances if row.cluster_id == int(filters["cluster_id"])]
    if filters.get("instance_id"):
        instances = [row for row in instances if row.id == int(filters["instance_id"])]
    visible_instance_ids = {row.id for row in instances}
    visible_cluster_ids = {row.cluster_id for row in instances if row.cluster_id}

    policies = BackupPolicy.query.order_by(BackupPolicy.id.asc()).all()
    policies = [
        row for row in policies
        if (row.target_type == "instance" and row.target_id in visible_instance_ids)
        or (row.target_type == "cluster" and row.target_id in visible_cluster_ids)
    ]
    policy_ids = [row.id for row in policies]
    latest_by_policy = {}
    if policy_ids:
        latest_ids = (
            db.session.query(db.func.max(BackupLog.id).label("id"))
            .filter(BackupLog.policy_id.in_(policy_ids))
            .group_by(BackupLog.policy_id)
            .subquery()
        )
        latest_logs = BackupLog.query.filter(BackupLog.id.in_(db.session.query(latest_ids.c.id))).all()
        latest_by_policy = {log.policy_id: log for log in latest_logs}

    try:
        hours = max(1, min(int(filters.get("hours") or 48), 720))
    except (TypeError, ValueError):
        hours = 48
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    policies_by_instance = {}
    cluster_policies = {}
    for policy in policies:
        latest = latest_by_policy.get(policy.id)
        policy_row = {
            "policy_id": policy.id,
            "policy_name": policy.name,
            "target_type": policy.target_type,
            "target_id": policy.target_id,
            "db_type": policy.db_type,
            "backup_type": policy.backup_type,
            "cron_expr": policy.cron_expr,
            "retain_days": policy.retain_days,
            "enabled": bool(policy.enabled),
            "latest_backup": _latest_backup_row(latest),
        }
        if policy.target_type == "instance":
            policies_by_instance.setdefault(policy.target_id, []).append(policy_row)
        else:
            cluster_policies.setdefault(policy.target_id, []).append(policy_row)

    cluster_map = {row.id: row for row in DatabaseCluster.query.filter(DatabaseCluster.id.in_(visible_cluster_ids)).all()} if visible_cluster_ids else {}
    items = []
    for instance in instances:
        rows = list(policies_by_instance.get(instance.id, [])) + list(cluster_policies.get(instance.cluster_id, []))
        enabled_rows = [row for row in rows if row["enabled"]]
        latest_logs = [latest_by_policy.get(row["policy_id"]) for row in enabled_rows]
        if not enabled_rows:
            protection_status = "unconfigured"
        elif any(log and log.status == "running" for log in latest_logs):
            protection_status = "running"
        elif any(log is None for log in latest_logs):
            protection_status = "never_run"
        elif any(log.status != "success" for log in latest_logs):
            protection_status = "failed"
        elif any(log.started_at < cutoff for log in latest_logs):
            protection_status = "stale"
        else:
            protection_status = "healthy"
        cluster = cluster_map.get(instance.cluster_id)
        items.append({
            "instance_id": instance.id,
            "instance_name": instance.name,
            "db_type": instance.db_type,
            "cluster_id": instance.cluster_id,
            "cluster_name": cluster.name if cluster else None,
            "enabled": bool(instance.enabled),
            "protection_status": protection_status,
            "policy_count": len(rows),
            "policies": rows,
        })

    status_filter = str(filters.get("protection_status") or "").strip().lower()
    if status_filter:
        items = [row for row in items if row["protection_status"] == status_filter]
    counts = Counter(row["protection_status"] for row in items)
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "filters": {**filters, "hours": hours},
        "summary": {"instance_total": len(items), "by_protection_status": dict(counts)},
        "instances": items,
    }


def _inspection_alert_row(alert, instance, cluster):
    return {
        "alert_id": alert.id,
        "instance_id": alert.instance_id,
        "instance_name": instance.name if instance else None,
        "cluster_id": alert.cluster_id,
        "cluster_name": cluster.name if cluster else None,
        "db_type": alert.db_type,
        "issue_key": alert.issue_key,
        "issue_name": alert.issue_name,
        "severity": alert.severity,
        "status": alert.status,
        "message": alert.message,
        "first_seen_at": alert.first_seen_at.isoformat() if alert.first_seen_at else None,
        "last_seen_at": alert.last_seen_at.isoformat() if alert.last_seen_at else None,
        "recovered_at": alert.recovered_at.isoformat() if alert.recovered_at else None,
        "notify_count": alert.notify_count,
        "last_notified_at": alert.last_notified_at.isoformat() if alert.last_notified_at else None,
        "muted_until": alert.muted_until.isoformat() if alert.muted_until else None,
        "is_muted": alert.is_muted(),
    }


def build_mcp_inspection_status(filters=None, allowed_cluster_ids=None):
    filters = filters or {}
    clusters, instances = _visible_clusters_and_instances(allowed_cluster_ids=allowed_cluster_ids, include_disabled=False)
    db_type = str(filters.get("db_type") or "").strip().lower()
    if db_type:
        instances = [row for row in instances if row.db_type == db_type]
    if filters.get("cluster_id"):
        instances = [row for row in instances if row.cluster_id == int(filters["cluster_id"])]
    if filters.get("instance_id"):
        instances = [row for row in instances if row.id == int(filters["instance_id"])]
    instance_map = {row.id: row for row in instances}
    cluster_map = {row.id: row for row in clusters}

    alert_query = InspectionAlert.query.filter(InspectionAlert.instance_id.in_(list(instance_map))) if instance_map else None
    if alert_query is not None and not filters.get("include_recovered"):
        alert_query = alert_query.filter(InspectionAlert.status == "open")
    alerts = alert_query.order_by(InspectionAlert.id.desc()).all() if alert_query is not None else []
    alerts_by_instance = {}
    for alert in alerts:
        alerts_by_instance.setdefault(alert.instance_id, []).append(alert)

    cfg = InspectionConfig.query.first()
    thresholds = _thresholds_from_config(cfg) if cfg else dict(DEFAULT_THRESHOLDS)
    inspection_items = [
        {
            "issue_key": issue_key,
            "scope": scope,
            "name": name,
            "threshold_key": threshold_key,
            "threshold": thresholds.get(threshold_key) if threshold_key else None,
            "unit": unit,
        }
        for issue_key, scope, name, threshold_key, unit in INSPECTION_ITEM_DEFINITIONS
    ]
    assets = []
    for instance in instances:
        current = [row for row in alerts_by_instance.get(instance.id, []) if row.status == "open"]
        cluster = cluster_map.get(instance.cluster_id)
        assets.append({
            "asset_type": "database",
            "instance_id": instance.id,
            "instance_name": instance.name,
            "db_type": instance.db_type,
            "cluster_id": instance.cluster_id,
            "cluster_name": cluster.name if cluster else None,
            "inspection_status": "abnormal" if current else "normal",
            "open_alert_count": len(current),
            "open_alert_ids": [row.id for row in current],
        })

    if allowed_cluster_ids is None and not filters.get("instance_id") and not filters.get("cluster_id") and not db_type:
        agents = BackupAgent.query.filter_by(enabled=True).order_by(BackupAgent.id.asc()).all()
        status_rows = AgentInspectionStatus.query.filter(AgentInspectionStatus.agent_id.in_([row.id for row in agents])).all() if agents else []
        status_map = {row.agent_id: row for row in status_rows}
        for agent in agents:
            status_row = status_map.get(agent.id)
            status = status_row.status if status_row else "abnormal"
            assets.append({
                "asset_type": "agent",
                "agent_id": agent.id,
                "agent_name": agent.name,
                "inspection_status": status,
                "message": status_row.message if status_row else "尚未执行 Agent 状态巡检",
                "checked_at": status_row.checked_at.isoformat() if status_row and status_row.checked_at else None,
            })

    alert_items = [
        _inspection_alert_row(row, instance_map.get(row.instance_id), cluster_map.get(row.cluster_id))
        for row in alerts
    ]
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "filters": filters,
        "config": {
            "enabled": bool(cfg.enabled) if cfg else True,
            "interval_seconds": int(cfg.interval_seconds or 60) if cfg else 60,
            "last_run_at": cfg.last_run_at.isoformat() if cfg and cfg.last_run_at else None,
        },
        "summary": {
            "inspection_item_total": len(inspection_items),
            "asset_total": len(assets),
            "abnormal_asset_total": sum(1 for row in assets if row["inspection_status"] != "normal"),
            "alert_total": len(alert_items),
            "open_alert_total": sum(1 for row in alert_items if row["status"] == "open"),
        },
        "inspection_items": inspection_items,
        "assets": assets,
        "alerts": alert_items,
    }
