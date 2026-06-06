from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta
import threading
from types import SimpleNamespace

from flask import current_app

from app.extensions import db
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.models.inspection import InspectionAlert, InspectionConfig
from app.models.monitor_snapshot import snapshot_model_for_instance
from app.services.collectors import collect_instance_metrics
from app.services.monitor_snapshot_service import latest_payload_by_instance_ids
from app.services.notifier import notify_with_targets
from app.services.redis_cache import (
    KEY_INSPECTION_SUMMARY,
    enqueue_snapshot_flush,
    get_json,
    set_json,
    set_latest_snapshot,
)
from app.utils.crypto import decrypt_secret

DEFAULT_THRESHOLDS = {
    "mysql_replication_lag_seconds": 60,
    "mysql_connection_usage_pct": 90,
    "mongodb_repl_lag_seconds": 60,
    "mongodb_cache_used_pct": 90,
    "redis_memory_usage_pct": 90,
    "redis_connection_usage_pct": 90,
    "host_cpu_usage_pct": 90,
    "host_memory_usage_pct": 90,
    "host_data_disk_usage_pct": 90,
}
_INSPECTION_LOCK = threading.Lock()
INSPECTION_CONFIG_CACHE_KEY = "dbms:config:inspection"


def _chunks(items, size: int):
    size = max(1, int(size or 1))
    for index in range(0, len(items), size):
        yield items[index:index + size]


def get_or_create_inspection_config():
    cached = get_json(INSPECTION_CONFIG_CACHE_KEY)
    cfg = InspectionConfig.query.first()
    if cfg:
        if not isinstance(cached, dict):
            set_json(INSPECTION_CONFIG_CACHE_KEY, cfg.to_dict())
        return cfg
    cfg = InspectionConfig(
        enabled=True,
        interval_seconds=60,
        collect_timeout_seconds=8,
        notify_enabled=True,
        notify_recovery=True,
        notify_target_ids_json=[],
        muted_cluster_ids_json=[],
        extra_json={"thresholds": DEFAULT_THRESHOLDS},
    )
    db.session.add(cfg)
    db.session.commit()
    set_json(INSPECTION_CONFIG_CACHE_KEY, cfg.to_dict())
    return cfg


def refresh_inspection_config_cache(cfg: InspectionConfig):
    set_json(INSPECTION_CONFIG_CACHE_KEY, cfg.to_dict())


def update_inspection_config(cfg: InspectionConfig, payload: dict):
    if "enabled" in payload:
        cfg.enabled = bool(payload.get("enabled"))
    if "interval_seconds" in payload:
        try:
            cfg.interval_seconds = max(10, int(payload.get("interval_seconds")))
        except (TypeError, ValueError):
            return "interval_seconds must be integer >= 10"
    if "collect_timeout_seconds" in payload:
        try:
            cfg.collect_timeout_seconds = max(3, int(payload.get("collect_timeout_seconds")))
        except (TypeError, ValueError):
            return "collect_timeout_seconds must be integer >= 3"
    if "notify_enabled" in payload:
        cfg.notify_enabled = bool(payload.get("notify_enabled"))
    if "notify_recovery" in payload:
        cfg.notify_recovery = bool(payload.get("notify_recovery"))
    if "notify_target_ids" in payload:
        ids = []
        for item in payload.get("notify_target_ids") or []:
            try:
                ids.append(int(item))
            except (TypeError, ValueError):
                continue
        cfg.notify_target_ids_json = sorted(set(ids))
    if "muted_cluster_ids" in payload:
        ids = []
        for item in payload.get("muted_cluster_ids") or []:
            try:
                ids.append(int(item))
            except (TypeError, ValueError):
                continue
        cfg.muted_cluster_ids_json = sorted(set(ids))
    if "thresholds" in payload:
        thresholds = payload.get("thresholds") or {}
        if not isinstance(thresholds, dict):
            return "thresholds must be object"
        merged = _thresholds_from_config(cfg)
        for key, value in thresholds.items():
            if key not in DEFAULT_THRESHOLDS:
                continue
            try:
                merged[key] = float(value)
            except (TypeError, ValueError):
                continue
        cfg.extra_json = {**(cfg.extra_json or {}), "thresholds": merged}
    return None


def _thresholds_from_config(cfg: InspectionConfig):
    extra = cfg.extra_json if isinstance(cfg.extra_json, dict) else {}
    raw = extra.get("thresholds") if isinstance(extra.get("thresholds"), dict) else {}
    merged = dict(DEFAULT_THRESHOLDS)
    for key, default_value in DEFAULT_THRESHOLDS.items():
        value = raw.get(key, default_value)
        try:
            merged[key] = float(value)
        except (TypeError, ValueError):
            merged[key] = float(default_value)
    return merged


def _safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value):
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _collect_instance(instance_id: int, instance_data: dict, password: str):
    try:
        data = collect_instance_metrics(instance=SimpleNamespace(**instance_data), password=password) or {}
        payload = dict(data)
        payload.setdefault("ok", False)
        payload.setdefault("collected_at", datetime.now().isoformat())
        running_status = "running" if payload.get("ok") and payload.get("ping_ok", True) else "error"
        return instance_id, payload, running_status
    except Exception as exc:
        payload = {"ok": False, "error": f"collect failed: {exc}", "collected_at": datetime.now().isoformat()}
        return instance_id, payload, "error"


# 最近 N 分钟的指标均值窗口，用于减少 CPU 瞬时峰值误报
CPU_AVERAGE_WINDOW_MINUTES = 10


def _metric_average_window(instance: DatabaseInstance, metric_key: str, current_value, minutes: int = CPU_AVERAGE_WINDOW_MINUTES):
    """结合当前采集值 + 近 N 分钟已写入的 inspection 快照均值，返回平均值。

    用于判定主机 CPU 均值是否超阈，避免单次瞬时峰值引起误报。
    """
    values = []
    try:
        model = snapshot_model_for_instance(instance)
        if model is not None:
            since = datetime.now() - timedelta(minutes=minutes)
            rows = (
                model.query
                .filter(
                    model.instance_id == instance.id,
                    model.metric_type == "inspection",
                    model.collected_at >= since,
                )
                .all()
            )
            for row in rows:
                snapshot_payload = row.payload_json if isinstance(row.payload_json, dict) else {}
                val = snapshot_payload.get(metric_key)
                fval = _safe_float(val)
                if fval is not None:
                    values.append(fval)
    except Exception:
        # 查询失败时降级为仅用当前值，不影响巡检主流程
        values = []

    current_fval = _safe_float(current_value)
    if current_fval is not None:
        values.append(current_fval)

    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _build_issue(issue_key: str, issue_name: str, message: str, severity: str = "warning"):
    return {
        "issue_key": issue_key,
        "issue_name": issue_name,
        "message": message,
        "severity": severity,
    }


def _extract_issues(instance: DatabaseInstance, payload: dict, thresholds: dict):
    issues = []
    if not isinstance(payload, dict):
        return [_build_issue("collect_failed", "采集失败", "采集结果格式错误", "critical")]
    if payload.get("ok") is False:
        return [_build_issue("connectivity", "连通性异常", str(payload.get("error") or "采集失败"), "critical")]
    if payload.get("ping_ok") is False:
        return [_build_issue("ping_failed", "连通性异常", "探活失败（ping/select 失败）", "critical")]

    host_cpu = _safe_float(payload.get("host_cpu_usage_pct"))
    host_mem = _safe_float(payload.get("host_memory_usage_pct"))
    host_disk = _safe_float(payload.get("host_data_disk_usage_pct"))

    # CPU 采用近 10 分钟均值判断，避免瞬时峰值误报
    host_cpu_avg = _metric_average_window(instance, "host_cpu_usage_pct", host_cpu, CPU_AVERAGE_WINDOW_MINUTES)
    if host_cpu_avg is not None:
        payload["host_cpu_usage_pct_avg_10m"] = host_cpu_avg
    if host_cpu_avg is not None and host_cpu_avg >= thresholds["host_cpu_usage_pct"]:
        issues.append(_build_issue(
            "host_cpu_high",
            "主机CPU高",
            f"CPU使用率 {host_cpu_avg}% (近10分钟均值，当前 {host_cpu if host_cpu is not None else '-'}%)",
        ))
    if host_mem is not None and host_mem >= thresholds["host_memory_usage_pct"]:
        issues.append(_build_issue("host_memory_high", "主机内存高", f"内存使用率 {host_mem}%"))
    if host_disk is not None and host_disk >= thresholds["host_data_disk_usage_pct"]:
        mount = payload.get("host_data_disk_mountpoint") or "-"
        issues.append(_build_issue("host_disk_high", "主机磁盘高", f"磁盘使用率 {host_disk}% (挂载点 {mount})"))

    if instance.db_type == "mysql":
        lag = _safe_int(payload.get("seconds_behind_master"))
        if payload.get("replication_role") == "slave":
            if payload.get("replica_io_running") is False or payload.get("replica_sql_running") is False:
                issues.append(_build_issue("mysql_replica_thread", "MySQL复制线程异常", "Replica IO/SQL 线程状态异常", "critical"))
            if lag is not None and lag >= thresholds["mysql_replication_lag_seconds"]:
                issues.append(_build_issue("mysql_replication_lag", "MySQL复制延迟高", f"复制延迟 {lag}s"))
        max_conn = _safe_int(payload.get("max_connections"))
        threads_connected = _safe_int(payload.get("threads_connected"))
        if max_conn and threads_connected is not None and max_conn > 0:
            usage = round(threads_connected * 100 / max_conn, 2)
            if usage >= thresholds["mysql_connection_usage_pct"]:
                issues.append(_build_issue("mysql_connection_high", "MySQL连接数高", f"连接使用率 {usage}%"))

    if instance.db_type == "mongodb":
        lag = _safe_int(payload.get("repl_lag_seconds"))
        cache_used_pct = _safe_float(payload.get("cache_used_pct"))
        if lag is not None and lag >= thresholds["mongodb_repl_lag_seconds"]:
            issues.append(_build_issue("mongodb_replication_lag", "MongoDB复制延迟高", f"复制延迟 {lag}s"))
        if cache_used_pct is not None and cache_used_pct >= thresholds["mongodb_cache_used_pct"]:
            issues.append(_build_issue("mongodb_cache_high", "MongoDB缓存使用率高", f"WT缓存使用率 {cache_used_pct}%"))

    if instance.db_type == "redis":
        memory_pct = _safe_float(payload.get("memory_usage_pct"))
        connection_pct = _safe_float(payload.get("connection_usage_pct"))
        if connection_pct is None:
            maxclients = _safe_int(payload.get("maxclients"))
            connected_clients = _safe_int(payload.get("connected_clients"))
            if maxclients and connected_clients is not None and maxclients > 0:
                connection_pct = round(connected_clients * 100 / maxclients, 2)
        if memory_pct is not None and memory_pct >= thresholds["redis_memory_usage_pct"]:
            issues.append(_build_issue("redis_memory_high", "Redis内存使用率高", f"内存使用率 {memory_pct}%"))
        if connection_pct is not None and connection_pct >= thresholds["redis_connection_usage_pct"]:
            issues.append(_build_issue("redis_connection_high", "Redis连接数使用率高", f"连接数使用率 {connection_pct}%"))
        if payload.get("role") == "slave" and str(payload.get("master_link_status") or "").lower() == "down":
            issues.append(_build_issue("redis_replication_link", "Redis主从链路异常", "master_link_status=down", "critical"))

    return issues


def _send_event_notification(event_type: str, cfg: InspectionConfig, instance: DatabaseInstance, cluster: DatabaseCluster, issue_or_alert):
    if not cfg.notify_enabled:
        return {"ok": False, "message": "notify disabled"}
    target_ids = cfg.get_notify_target_ids()
    if not target_ids:
        return {"ok": False, "message": "no targets"}
    cluster_name = f"{cluster.name}" if cluster else "-"
    biz = (cluster.business_line or cluster.namespace) if cluster else "-"
    env = cluster.environment if cluster else "-"
    if event_type == "alert":
        title = "数据库巡检异常告警"
        content = "\n".join(
            [
                f"> 业务: <font color=\"comment\">{biz}/{env}</font>",
                f"> 集群: <font color=\"comment\">{cluster_name}</font>",
                f"> 实例: <font color=\"warning\">{instance.name}</font>",
                f"> 类型: <font color=\"comment\">{instance.db_type}</font>",
                f"> 异常项: <font color=\"warning\">{issue_or_alert.get('issue_name')}</font>",
                f"> 详情: <font color=\"warning\">{issue_or_alert.get('message')}</font>",
                f"> 时间: <font color=\"comment\">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</font>",
            ]
        )
    else:
        title = "数据库巡检恢复通知"
        content = "\n".join(
            [
                f"> 业务: <font color=\"comment\">{biz}/{env}</font>",
                f"> 集群: <font color=\"comment\">{cluster_name}</font>",
                f"> 实例: <font color=\"info\">{instance.name}</font>",
                f"> 类型: <font color=\"comment\">{instance.db_type}</font>",
                f"> 恢复项: <font color=\"info\">{issue_or_alert.issue_name}</font>",
                f"> 时间: <font color=\"comment\">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</font>",
            ]
        )
    return notify_with_targets(target_ids=target_ids, title=title, content=content)


def run_inspection_cycle(trigger: str = "manual", force: bool = False):
    if not _INSPECTION_LOCK.acquire(blocking=False):
        return {"ok": False, "message": "inspection is already running", "code": 409}

    started_at = datetime.now()
    try:
        cfg = get_or_create_inspection_config()
        if not cfg.enabled and not force:
            return {"ok": True, "message": "inspection is disabled", "data": {"enabled": False, "skipped": True}}

        thresholds = _thresholds_from_config(cfg)
        instances = DatabaseInstance.query.filter_by(enabled=True).all()
        instance_map = {item.id: item for item in instances}
        cluster_ids = sorted({item.cluster_id for item in instances if item.cluster_id})
        cluster_map = {
            row.id: row
            for row in DatabaseCluster.query.filter(DatabaseCluster.id.in_(cluster_ids)).all()
        } if cluster_ids else {}

        payload_by_instance = {}
        issue_map = {}
        work_items = []
        for instance in instances:
            try:
                password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
            except Exception as exc:
                payload = {"ok": False, "error": f"decrypt failed: {exc}", "collected_at": datetime.now().isoformat()}
                payload_by_instance[instance.id] = payload
                issue_map[instance.id] = _extract_issues(instance, payload, thresholds)
                instance.running_status = "error"
                continue
            instance_data = {
                "id": instance.id,
                "db_type": instance.db_type,
                "host_input": instance.host_input,
                "resolved_ip": instance.resolved_ip,
                "port": instance.port,
                "username": instance.username,
                "extra_json": instance.extra_json,
            }
            work_items.append((instance.id, instance_data, password))

        max_workers = max(1, min(int(current_app.config.get("INSPECTION_COLLECT_WORKERS", 8)), max(1, len(work_items))))
        timeout_seconds = max(3, int(cfg.collect_timeout_seconds or 8))
        batch_count = 0
        for batch in _chunks(work_items, max_workers):
            batch_count += 1
            future_map = {}
            completed = set()
            pool = ThreadPoolExecutor(max_workers=max(1, len(batch)), thread_name_prefix="inspection-collect")
            try:
                for instance_id, instance_data, password in batch:
                    future = pool.submit(_collect_instance, instance_id, instance_data, password)
                    future_map[future] = instance_id
                try:
                    for future in as_completed(future_map, timeout=timeout_seconds):
                        completed.add(future)
                        instance_id, payload, running_status = future.result()
                        payload_by_instance[instance_id] = payload
                        instance = instance_map.get(instance_id)
                        if not instance:
                            continue
                        instance.running_status = running_status
                        issue_map[instance_id] = _extract_issues(instance, payload, thresholds)
                except FuturesTimeoutError:
                    current_app.logger.warning(
                        "inspection batch timeout: %ss batch=%s instances=%s workers=%s",
                        timeout_seconds,
                        batch_count,
                        len(batch),
                        max_workers,
                    )

                pending = set(future_map.keys()) - completed
                for future in pending:
                    instance_id = future_map[future]
                    future.cancel()
                    instance = instance_map.get(instance_id)
                    if not instance:
                        continue
                    payload = {
                        "ok": False,
                        "error": f"collect timeout (>{timeout_seconds}s per instance)",
                        "collected_at": datetime.now().isoformat(),
                    }
                    payload_by_instance[instance_id] = payload
                    issue_map[instance_id] = _extract_issues(instance, payload, thresholds)
                    instance.running_status = "error"
            finally:
                pool.shutdown(wait=False)

        now = datetime.now()
        app_obj = current_app._get_current_object()
        for instance in instances:
            payload = payload_by_instance.get(instance.id) or {"ok": False, "error": "collect missing", "collected_at": now.isoformat()}
            set_latest_snapshot(
                db_type=instance.db_type,
                instance_id=instance.id,
                metric_type="inspection",
                payload_json=payload,
                collected_at=now,
                running_status=instance.running_status or None,
            )
            enqueue_snapshot_flush(
                app=app_obj,
                db_type=instance.db_type,
                instance_id=instance.id,
                metric_type="inspection",
                payload_json=payload,
                collected_at=now,
            )

        alerts = InspectionAlert.query.filter(InspectionAlert.instance_id.in_(list(instance_map.keys()))).all() if instance_map else []
        alert_map = {(row.instance_id, row.issue_key): row for row in alerts}
        current_keys = set()
        muted_cluster_ids = set(cfg.get_muted_cluster_ids())
        new_alerts = 0
        recovered_alerts = 0
        sent_alerts = 0
        sent_recoveries = 0

        for instance_id, issues in issue_map.items():
            instance = instance_map.get(instance_id)
            if not instance:
                continue
            cluster = cluster_map.get(instance.cluster_id)
            for issue in issues:
                key = (instance_id, issue["issue_key"])
                current_keys.add(key)
                alert = alert_map.get(key)
                is_new_or_reopen = False
                if not alert:
                    alert = InspectionAlert(
                        instance_id=instance.id,
                        cluster_id=instance.cluster_id,
                        db_type=instance.db_type,
                        issue_key=issue["issue_key"],
                        issue_name=issue["issue_name"],
                        severity=issue["severity"],
                        status="open",
                        message=issue["message"],
                        first_seen_at=now,
                        last_seen_at=now,
                        recovered_at=None,
                        last_payload_json=payload_by_instance.get(instance_id) or {},
                    )
                    db.session.add(alert)
                    alert_map[key] = alert
                    new_alerts += 1
                    is_new_or_reopen = True
                else:
                    if alert.status != "open":
                        alert.first_seen_at = now
                        alert.recovered_at = None
                        alert.recovery_notified_at = None
                        new_alerts += 1
                        is_new_or_reopen = True
                    alert.status = "open"
                    alert.last_seen_at = now
                    alert.cluster_id = instance.cluster_id
                    alert.db_type = instance.db_type
                    alert.issue_name = issue["issue_name"]
                    alert.severity = issue["severity"]
                    alert.message = issue["message"]
                    alert.last_payload_json = payload_by_instance.get(instance_id) or {}

                if is_new_or_reopen and instance.cluster_id not in muted_cluster_ids:
                    notify_result = _send_event_notification("alert", cfg, instance, cluster, issue)
                    if notify_result.get("ok"):
                        sent_alerts += 1
                        alert.notify_count = int(alert.notify_count or 0) + 1
                        alert.last_notified_at = now

        for alert in alerts:
            key = (alert.instance_id, alert.issue_key)
            if alert.status != "open":
                continue
            if key in current_keys:
                continue
            instance = instance_map.get(alert.instance_id)
            if not instance:
                continue
            cluster = cluster_map.get(instance.cluster_id)
            alert.status = "recovered"
            alert.recovered_at = now
            recovered_alerts += 1
            if cfg.notify_recovery and instance.cluster_id not in muted_cluster_ids:
                notify_result = _send_event_notification("recovery", cfg, instance, cluster, alert)
                if notify_result.get("ok"):
                    sent_recoveries += 1
                    alert.recovery_notified_at = now

        abnormal_instances = sum(1 for item in issue_map.values() if item)
        issue_total = sum(len(item) for item in issue_map.values())
        summary = {
            "trigger": trigger,
            "inspected_total": len(instances),
            "abnormal_instances": abnormal_instances,
            "issue_total": issue_total,
            "new_alerts": new_alerts,
            "recovered_alerts": recovered_alerts,
            "sent_alerts": sent_alerts,
            "sent_recoveries": sent_recoveries,
            "collect_workers": max_workers,
            "collect_timeout_seconds": timeout_seconds,
            "collect_batches": batch_count,
            "started_at": started_at.isoformat(),
            "finished_at": now.isoformat(),
            "duration_ms": int((now - started_at).total_seconds() * 1000),
        }
        cfg.last_run_at = now
        cfg.last_run_summary_json = summary
        db.session.commit()
        set_json(KEY_INSPECTION_SUMMARY, summary)
        refresh_inspection_config_cache(cfg)
        return {"ok": True, "data": summary}
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception("inspection cycle failed: %s", exc)
        return {"ok": False, "message": str(exc), "code": 500}
    finally:
        _INSPECTION_LOCK.release()


def inspection_overview(
    db_type: str = None,
    cluster_id: int = None,
    status: str = None,
    page: int = 1,
    page_size: int = 10,
    allowed_cluster_ids=None,
):
    try:
        page = int(page)
    except (TypeError, ValueError):
        page = 1
    try:
        page_size = int(page_size)
    except (TypeError, ValueError):
        page_size = 10
    page = max(page, 1)
    page_size = max(1, min(page_size, 100))

    instances_query = DatabaseInstance.query.filter_by(enabled=True)
    if db_type:
        instances_query = instances_query.filter_by(db_type=db_type)
    if cluster_id:
        instances_query = instances_query.filter_by(cluster_id=cluster_id)
    if allowed_cluster_ids is not None:
        ids = [int(item) for item in (allowed_cluster_ids or []) if item is not None]
        if not ids:
            return {
                "items": [],
                "page": page,
                "page_size": page_size,
                "total": 0,
                "summary": {"total": 0, "abnormal": 0, "normal": 0},
            }
        instances_query = instances_query.filter(DatabaseInstance.cluster_id.in_(ids))
    instances = instances_query.order_by(DatabaseInstance.id.desc()).all()
    if not instances:
        return {
            "items": [],
            "page": page,
            "page_size": page_size,
            "total": 0,
            "summary": {"total": 0, "abnormal": 0, "normal": 0},
        }

    cluster_ids = sorted({item.cluster_id for item in instances if item.cluster_id})
    cluster_map = {
        row.id: row
        for row in DatabaseCluster.query.filter(DatabaseCluster.id.in_(cluster_ids)).all()
    } if cluster_ids else {}
    instance_ids = [item.id for item in instances]
    open_alerts = (
        InspectionAlert.query
        .filter(InspectionAlert.instance_id.in_(instance_ids), InspectionAlert.status == "open")
        .order_by(InspectionAlert.id.desc())
        .all()
    )
    alerts_by_instance = {}
    for row in open_alerts:
        alerts_by_instance.setdefault(row.instance_id, []).append(row)

    payload_by_instance = {}
    for t in {"mysql", "mongodb", "redis", "doris"}:
        ids = [item.id for item in instances if item.db_type == t]
        if ids:
            payload_by_instance.update(latest_payload_by_instance_ids(db_type=t, instance_ids=ids, metric_type="inspection"))

    items = []
    for instance in instances:
        payload = payload_by_instance.get(instance.id) or {}
        issues = alerts_by_instance.get(instance.id) or []
        item_status = "abnormal" if issues else "normal"
        if status in {"abnormal", "normal"} and item_status != status:
            continue
        cluster = cluster_map.get(instance.cluster_id)
        items.append(
            {
                "instance_id": instance.id,
                "instance_name": instance.name,
                "db_type": instance.db_type,
                "cluster_id": instance.cluster_id,
                "cluster_name": cluster.name if cluster else None,
                "business_line": (cluster.business_line or cluster.namespace) if cluster else None,
                "environment": cluster.environment if cluster else None,
                "inspection_status": item_status,
                "issues": [row.to_dict() for row in issues],
                "issue_count": len(issues),
                "payload_json": payload,
                "collected_at": payload.get("collected_at"),
            }
        )
    abnormal = sum(1 for item in items if item["inspection_status"] == "abnormal")
    total = len(items)
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    paged_items = items[start:end]

    return {
        "items": paged_items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "summary": {
            "total": total,
            "abnormal": abnormal,
            "normal": total - abnormal,
        },
    }
