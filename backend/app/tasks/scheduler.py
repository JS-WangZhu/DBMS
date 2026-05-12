from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta
from types import SimpleNamespace

from apscheduler.triggers.cron import CronTrigger
from flask import current_app

from app.extensions import db
from app.models.backup import BackupLog, BackupPolicy
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.models.inspection import InspectionConfig
from app.models.monitor_snapshot import SNAPSHOT_MODEL_BY_DB_TYPE, snapshot_model_for_instance
from app.services.backup_agent_client import BackupAgentError, execute_backup_on_agent
from app.services.backup_executor import run_backup_policy
from app.services.collectors import collect_instance_metrics
from app.services.dns_resolver import refresh_all_dns, resolve_host
from app.services.inspection_service import get_or_create_inspection_config, run_inspection_cycle
from app.services.instance_status_config import get_or_create_instance_status_config
from app.services.notifier import notify_backup_failure
from app.services.topology_history import (
    extract_mongo_topology,
    extract_mysql_topology,
    extract_redis_topology,
    record_topology_change_if_diff,
)
from app.utils.crypto import decrypt_secret

CRON_ALIAS_MAP = {
    "@every_minute": "* * * * *",
    "@hourly": "0 * * * *",
    "@daily": "0 0 * * *",
    "@weekly": "0 0 * * 0",
    "@monthly": "0 0 1 * *",
}


def _trigger_from_expr(expr: str):
    normalized = CRON_ALIAS_MAP.get((expr or "").strip(), (expr or "").strip())
    tz_name = current_app.config.get("SCHEDULER_TIMEZONE", "Asia/Shanghai")
    try:
        import pytz

        timezone = pytz.timezone(tz_name)
    except Exception:
        timezone = None
    return CronTrigger.from_crontab(normalized, timezone=timezone)


def _resolve_app(app):
    if app is None:
        return None
    getter = getattr(app, "_get_current_object", None)
    if callable(getter):
        try:
            return getter()
        except Exception:
            return None
    return app


def register_jobs(scheduler, app):
    app = _resolve_app(app) or app
    scheduler.add_job(
        id="dns_refresh_hourly",
        func=job_dns_refresh,
        trigger="interval",
        hours=1,
        replace_existing=True,
        kwargs={"app": app},
    )

    sync_monitor_collect_job(scheduler=scheduler, app=app)

    scheduler.add_job(
        id="monitor_snapshot_cleanup_daily",
        func=job_monitor_snapshot_cleanup,
        trigger=CronTrigger.from_crontab("0 0 * * *"),
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        kwargs={"app": app},
    )

    sync_backup_jobs(scheduler=scheduler, app=app)
    sync_inspection_job(scheduler=scheduler, app=app)


def sync_backup_jobs(scheduler, app):
    app = _resolve_app(app) or app
    existing = scheduler.get_jobs()
    for job in existing:
        if job.id.startswith("backup_policy_"):
            scheduler.remove_job(job.id)

    with app.app_context():
        policies = BackupPolicy.query.filter_by(enabled=True).all()
        for policy in policies:
            try:
                trigger = _trigger_from_expr(policy.cron_expr)
            except Exception:
                continue

            scheduler.add_job(
                id=f"backup_policy_{policy.id}",
                func=job_run_backup_policy,
                trigger=trigger,
                replace_existing=True,
                kwargs={"app": app, "policy_id": policy.id},
            )


def sync_monitor_collect_job(scheduler, app):
    app = _resolve_app(app) or app
    job_id = "monitor_collect_1min"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    with app.app_context():
        cfg = get_or_create_instance_status_config()
        interval_seconds = max(10, int(cfg.probe_poll_interval_seconds or 30))
        scheduler.add_job(
            id=job_id,
            func=job_monitor_collect,
            trigger="interval",
            seconds=interval_seconds,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            kwargs={"app": app},
        )


def sync_inspection_job(scheduler, app):
    app = _resolve_app(app) or app
    job_id = "inspection_periodic"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    with app.app_context():
        cfg = InspectionConfig.query.first() or get_or_create_inspection_config()
        if not cfg or not cfg.enabled:
            return
        interval_seconds = max(10, int(cfg.interval_seconds or 60))
        scheduler.add_job(
            id=job_id,
            func=job_run_inspection,
            trigger="interval",
            seconds=interval_seconds,
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            kwargs={"app": app},
        )


def job_run_inspection(app):
    app = _resolve_app(app) or app
    if app is None:
        current_app.logger.error("inspection job missing app context")
        return
    with app.app_context():
        result = run_inspection_cycle(trigger="scheduler", force=False)
        if not result.get("ok"):
            current_app.logger.warning("inspection job failed: %s", result.get("message"))


def job_run_backup_policy(app, policy_id: int):
    app = _resolve_app(app) or app
    if app is None:
        current_app.logger.error("backup policy job missing app context")
        return {"ok": False, "message": "app context missing"}
    with app.app_context():
        policy = BackupPolicy.query.get(policy_id)
        if not policy:
            app.logger.error(f"Backup policy not found: policy_id={policy_id}")
            return {"ok": False, "message": "policy not found"}

        agent_id = policy.backup_agent_id
        if agent_id:
            log = BackupLog(
                policy_id=policy.id,
                started_at=datetime.utcnow(),
                status="running",
                extra_json={"remote": True, "agent_id": agent_id},
            )
            db.session.add(log)
            db.session.commit()
            try:
                result = execute_backup_on_agent(policy_id=policy_id, agent_id=agent_id, dry_run=False)
                if not result.get("ok"):
                    instance = DatabaseInstance.query.get(policy.target_id)
                    error_message = result.get("message") or ((result.get("data") or {}).get("message")) or "remote backup failed"
                    notify_backup_failure(policy=policy, instance=instance, error_message=error_message, command=(result.get("data") or {}).get("command", []))
                    raise BackupAgentError(error_message)

                remote_data = result.get("data") or {}
                compress_method = (policy.extra_json or {}).get("compress_method") if isinstance(policy.extra_json, dict) else None
                if compress_method not in {"none", "gzip", "zstd"}:
                    compress_method = "gzip" if policy.compress else "none"
                remote_extra = {
                    "remote": True,
                    "agent_id": agent_id,
                    "command": remote_data.get("command", []),
                    "compress": compress_method != "none",
                    "compress_method": remote_data.get("compress_method") or compress_method,
                    "encrypt": ((policy.extra_json or {}).get("encrypt") if isinstance(policy.extra_json, dict) else None),
                    "s3": {"ok": False, "message": "s3 upload disabled"},
                }
                if isinstance(remote_data.get("encrypt"), dict):
                    remote_extra["encrypt"] = remote_data.get("encrypt")
                if isinstance(remote_data.get("s3"), dict):
                    remote_extra["s3"] = remote_data.get("s3")

                log.status = "success"
                log.finished_at = datetime.utcnow()
                log.file_path = remote_data.get("output_file")
                log.size_bytes = remote_data.get("file_size")
                log.error_message = None
                log.extra_json = remote_extra
                db.session.commit()

                remote_data["backup_log_id"] = log.id
                result["data"] = remote_data
                app.logger.info(f"Remote backup completed: policy_id={policy_id}, agent_id={agent_id}, result={result}")
                return result
            except BackupAgentError as e:
                instance = DatabaseInstance.query.get(policy.target_id)
                notify_backup_failure(policy=policy, instance=instance, error_message=str(e), command=[])
                log.status = "failed"
                log.finished_at = datetime.utcnow()
                log.error_message = str(e)
                log.extra_json = {**(log.extra_json or {}), "remote": True, "agent_id": agent_id}
                db.session.commit()
                app.logger.error(f"Remote backup failed: policy_id={policy_id}, agent_id={agent_id}, error={str(e)}")
                raise
        return run_backup_policy(policy_id=policy_id, dry_run=False)


def job_dns_refresh(app):
    app = _resolve_app(app) or app
    if app is None:
        current_app.logger.error("dns refresh job missing app context")
        return
    with app.app_context():
        instances = DatabaseInstance.query.filter_by(enabled=True).all()
        refresh_all_dns(instances)
        db.session.commit()


def _collect_instance_snapshot(instance_id: int, instance_data: dict, password: str):
    try:
        instance_stub = SimpleNamespace(**instance_data)
        data = collect_instance_metrics(instance=instance_stub, password=password) or {}
        payload = dict(data)
        payload.setdefault("ok", False)
        payload.setdefault("collected_at", datetime.now().isoformat())
        running_status = "running" if payload.get("ok") and payload.get("ping_ok") else "error"
        return instance_id, payload, running_status
    except Exception as exc:
        payload = {"ok": False, "error": f"collect failed: {exc}", "collected_at": datetime.now().isoformat()}
        return instance_id, payload, "error"


def _refresh_mysql_cluster_ha(instances, payload_by_instance):
    mysql_clusters = DatabaseCluster.query.filter_by(db_type="mysql").all()
    if not mysql_clusters:
        return

    instance_rows = [item for item in instances if item.db_type == "mysql" and item.enabled and item.cluster_id]
    cluster_instances = {}
    for ins in instance_rows:
        cluster_instances.setdefault(ins.cluster_id, []).append(ins)

    def _instance_host_key(instance):
        host = (instance.resolved_ip or instance.host_input or "").strip().lower()
        if not host or instance.port in (None, ""):
            return None
        return f"{host}:{int(instance.port)}"

    def _payload_source_key(payload):
        host = (payload.get("replica_source_resolved_ip") or payload.get("replica_source_host") or "").strip().lower()
        port = payload.get("replica_source_port")
        if not host or port in (None, ""):
            return None
        return f"{host}:{int(port)}"

    downstream_source_keys = {_payload_source_key(payload_by_instance.get(ins.id) or {}) for ins in instance_rows}

    for cluster in mysql_clusters:
        ha_domain = (cluster.ha_domain or "").strip()
        if not ha_domain:
            continue

        resolved_ip = resolve_host(ha_domain) or ha_domain
        matched_instance = None
        matched_writable = False

        for ins in cluster_instances.get(cluster.id, []):
            host = (ins.resolved_ip or ins.host_input or "").strip()
            if host != resolved_ip:
                continue
            payload = payload_by_instance.get(ins.id) or {}
            matched_instance = ins
            role = str(payload.get("replication_role") or "").strip().lower()
            self_key = _instance_host_key(ins)
            has_downstream_replica = bool(self_key and self_key in downstream_source_keys)
            matched_writable = bool(
                payload.get("ping_ok") is True
                and (role in {"master", "master_slave"} or (role == "slave" and has_downstream_replica))
                and payload.get("effective_read_only") is False
            )
            break

        status = {
            "ha_domain": ha_domain,
            "resolved_ip": resolved_ip,
            "ok": bool(matched_instance and matched_writable),
            "matched_instance_id": matched_instance.id if matched_instance else None,
            "matched_instance_name": matched_instance.name if matched_instance else None,
            "matched_writable": matched_writable,
            "checked_at": datetime.now().isoformat(),
            "reason": None,
        }
        if not matched_instance:
            status["reason"] = "resolved ip not found in cluster"
        elif not matched_writable:
            status["reason"] = "target instance is not writable master"

        cluster.ha_status_json = status


def _refresh_cluster_topology_history(instances, payload_by_instance):
    """基于本次采集结果，对 MongoDB / Redis / MySQL 集群进行拓扑指纹去重后写入变更历史。单条集群异常不影响其他集群。"""
    try:
        target_db_types = {"mongodb", "redis", "mysql"}
        instance_rows = [
            item for item in instances
            if item.db_type in target_db_types and item.enabled and item.cluster_id
        ]
        if not instance_rows:
            return

        grouped = {}
        for ins in instance_rows:
            grouped.setdefault((ins.db_type, ins.cluster_id), []).append(ins)

        cluster_ids = sorted({cid for _, cid in grouped.keys()})
        cluster_map = {
            row.id: row
            for row in DatabaseCluster.query.filter(DatabaseCluster.id.in_(cluster_ids)).all()
        } if cluster_ids else {}

        for (db_type, cluster_id), ins_list in grouped.items():
            cluster = cluster_map.get(cluster_id)
            if not cluster or cluster.db_type != db_type:
                continue
            try:
                payload_items = [
                    {
                        "instance_id": ins.id,
                        "instance_name": ins.name,
                        "host": ins.resolved_ip or ins.host_input,
                        "port": ins.port,
                        "payload": payload_by_instance.get(ins.id) or {},
                    }
                    for ins in ins_list
                ]
                if db_type == "mongodb":
                    topology = extract_mongo_topology(payload_items)
                elif db_type == "redis":
                    topology = extract_redis_topology(payload_items)
                else:
                    topology = extract_mysql_topology(payload_items, ha_domain=cluster.ha_domain)
                record_topology_change_if_diff(cluster, topology)
            except Exception as exc:
                current_app.logger.warning(
                    "topology history refresh failed: cluster_id=%s db_type=%s err=%s",
                    cluster_id, db_type, exc,
                )
    except Exception as exc:
        current_app.logger.warning("topology history refresh skipped: %s", exc)


def job_monitor_collect(app):
    app = _resolve_app(app) or app
    if app is None:
        current_app.logger.error("monitor collect job missing app context")
        return
    with app.app_context():
        try:
            instances = DatabaseInstance.query.filter_by(enabled=True).all()
            if not instances:
                current_app.logger.info("monitor_collect tick: no enabled instances")
                return

            instance_map = {item.id: item for item in instances}
            cfg_workers = int(current_app.config.get("MONITOR_COLLECT_WORKERS", 8))
            max_workers = max(1, min(cfg_workers, len(instances)))
            work_items = []
            ok_count = 0
            fail_count = 0
            payload_by_instance = {}

            for instance in instances:
                try:
                    password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
                except Exception as exc:
                    payload = {"ok": False, "error": f"decrypt failed: {exc}", "collected_at": datetime.now().isoformat()}
                    instance.running_status = "error"
                    fail_count += 1
                    snapshot_model = snapshot_model_for_instance(instance)
                    db.session.add(
                        snapshot_model(
                            instance_id=instance.id,
                            metric_type="status",
                            payload_json=payload,
                            collected_at=datetime.now(),
                        )
                    )
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

            future_map = {}
            with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="monitor-collect") as pool:
                for instance_id, instance_data, password in work_items:
                    future = pool.submit(_collect_instance_snapshot, instance_id, instance_data, password)
                    future_map[future] = instance_id

                completed = set()
                status_cfg = get_or_create_instance_status_config()
                collect_timeout_seconds = float(status_cfg.metric_refresh_timeout_seconds or 8)
                if collect_timeout_seconds < 1:
                    collect_timeout_seconds = 1
                try:
                    for future in as_completed(future_map.keys(), timeout=collect_timeout_seconds):
                        completed.add(future)
                        instance_id, payload, running_status = future.result()

                        instance = instance_map.get(instance_id)
                        if not instance:
                            continue
                        if running_status != "running":
                            current_app.logger.warning(
                                "monitor_collect payload: instance_id=%s ok=%s ping_ok=%s error=%s keys=%s",
                                instance_id,
                                payload.get("ok"),
                                payload.get("ping_ok"),
                                payload.get("error"),
                                list(payload.keys()),
                            )

                        instance.running_status = running_status
                        payload_by_instance[instance_id] = payload
                        if running_status == "running":
                            ok_count += 1
                        else:
                            fail_count += 1
                        snapshot_model = snapshot_model_for_instance(instance)
                        db.session.add(
                            snapshot_model(
                                instance_id=instance.id,
                                metric_type="status",
                                payload_json=payload,
                                collected_at=datetime.now(),
                            )
                        )
                except FuturesTimeoutError:
                    current_app.logger.warning(
                        "monitor_collect tick timeout: not all instances finished within %ss",
                        collect_timeout_seconds,
                    )

                pending = set(future_map.keys()) - completed
                for future in pending:
                    instance_id = future_map[future]
                    future.cancel()
                    instance = instance_map.get(instance_id)
                    if not instance:
                        continue
                    instance.running_status = "error"
                    payload_by_instance[instance_id] = {"ok": False, "error": f"collect timeout (>{collect_timeout_seconds}s)"}
                    fail_count += 1
                    current_app.logger.warning("monitor_collect timeout: instance_id=%s", instance_id)
                    snapshot_model = snapshot_model_for_instance(instance)
                    db.session.add(
                        snapshot_model(
                            instance_id=instance.id,
                            metric_type="status",
                            payload_json={
                                "ok": False,
                                "error": f"collect timeout (>{collect_timeout_seconds}s)",
                                "collected_at": datetime.now().isoformat(),
                            },
                            collected_at=datetime.now(),
                        )
                    )

            _refresh_mysql_cluster_ha(instances, payload_by_instance)
            _refresh_cluster_topology_history(instances, payload_by_instance)
            db.session.commit()
            current_app.logger.info(
                "monitor_collect tick: total=%s ok=%s fail=%s",
                len(instances),
                ok_count,
                fail_count,
            )
        except Exception as exc:
            db.session.rollback()
            current_app.logger.exception(f"monitor_collect tick failed: {exc}")


def job_monitor_snapshot_cleanup(app, retain_days: int = 3):
    app = _resolve_app(app) or app
    if app is None:
        current_app.logger.error("monitor snapshot cleanup job missing app context")
        return
    with app.app_context():
        try:
            cutoff = datetime.now() - timedelta(days=max(1, int(retain_days)))
            deleted_total = 0
            detail = {}
            for db_type, model in SNAPSHOT_MODEL_BY_DB_TYPE.items():
                deleted = (
                    model.query
                    .filter(model.collected_at < cutoff)
                    .delete(synchronize_session=False)
                )
                deleted_total += deleted
                detail[db_type] = deleted
            db.session.commit()
            current_app.logger.info(
                "monitor snapshot cleanup finished: cutoff=%s total_deleted=%s detail=%s",
                cutoff.isoformat(),
                deleted_total,
                detail,
            )
        except Exception as exc:
            db.session.rollback()
            current_app.logger.exception(f"monitor snapshot cleanup failed: {exc}")
