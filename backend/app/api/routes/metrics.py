from flask import Blueprint, Response
from datetime import datetime, timedelta

from app.extensions import db, scheduler
from app.models.backup import BackupLog, BackupPolicy
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.models.notify_target import BackupNotifyTarget
from app.models.s3_storage_config import S3StorageConfig

bp = Blueprint("metrics", __name__, url_prefix="/metrics")


def _count(query):
    try:
        return int(query.count())
    except Exception:
        return 0


@bp.get("")
def metrics():
    instance_total = _count(DatabaseInstance.query)
    instance_enabled = _count(DatabaseInstance.query.filter_by(enabled=True))
    cluster_total = _count(DatabaseCluster.query)
    policy_total = _count(BackupPolicy.query)
    policy_enabled = _count(BackupPolicy.query.filter_by(enabled=True))
    now_utc = datetime.utcnow()
    now_beijing = now_utc + timedelta(hours=8)
    beijing_day_start = datetime(now_beijing.year, now_beijing.month, now_beijing.day)
    backup_window_start_utc = beijing_day_start - timedelta(hours=8)
    backup_window_end_utc = backup_window_start_utc + timedelta(days=1)
    backup_today_query = BackupLog.query.filter(
        BackupLog.started_at >= backup_window_start_utc,
        BackupLog.started_at < backup_window_end_utc,
    )
    backup_log_total = _count(backup_today_query)
    backup_success_total = _count(backup_today_query.filter(BackupLog.status == "success"))
    backup_failed_total = _count(backup_today_query.filter(BackupLog.status == "failed"))
    backup_running_total = _count(backup_today_query.filter(BackupLog.status == "running"))

    mysql_instance_total = _count(DatabaseInstance.query.filter(DatabaseInstance.db_type == "mysql"))
    mysql_instance_running_total = _count(
        DatabaseInstance.query.filter(DatabaseInstance.db_type == "mysql", DatabaseInstance.running_status == "running")
    )
    mongodb_instance_total = _count(DatabaseInstance.query.filter(DatabaseInstance.db_type == "mongodb"))
    mongodb_instance_running_total = _count(
        DatabaseInstance.query.filter(DatabaseInstance.db_type == "mongodb", DatabaseInstance.running_status == "running")
    )
    redis_instance_total = _count(DatabaseInstance.query.filter(DatabaseInstance.db_type == "redis"))
    redis_instance_running_total = _count(
        DatabaseInstance.query.filter(DatabaseInstance.db_type == "redis", DatabaseInstance.running_status == "running")
    )
    postgresql_instance_total = _count(DatabaseInstance.query.filter(DatabaseInstance.db_type == "postgresql"))
    postgresql_instance_running_total = _count(
        DatabaseInstance.query.filter(DatabaseInstance.db_type == "postgresql", DatabaseInstance.running_status == "running")
    )
    doris_instance_total = _count(DatabaseInstance.query.filter(DatabaseInstance.db_type == "doris"))
    doris_instance_running_total = _count(
        DatabaseInstance.query.filter(DatabaseInstance.db_type == "doris", DatabaseInstance.running_status == "running")
    )
    notify_target_total = _count(BackupNotifyTarget.query)
    s3_config_total = _count(S3StorageConfig.query)
    db_ok = 1
    try:
        db.session.execute(db.text("SELECT 1"))
    except Exception:
        db_ok = 0
    scheduler_running = 1 if scheduler.running else 0

    lines = [
        "# HELP dbms_up DBMS service health status.",
        "# TYPE dbms_up gauge",
        f"dbms_up {db_ok}",
        "# HELP dbms_scheduler_running Scheduler running status.",
        "# TYPE dbms_scheduler_running gauge",
        f"dbms_scheduler_running {scheduler_running}",
        "# HELP dbms_instances_total Total number of instances.",
        "# TYPE dbms_instances_total gauge",
        f"dbms_instances_total {instance_total}",
        "# HELP dbms_instances_enabled Total number of enabled instances.",
        "# TYPE dbms_instances_enabled gauge",
        f"dbms_instances_enabled {instance_enabled}",
        "# HELP dbms_clusters_total Total number of clusters.",
        "# TYPE dbms_clusters_total gauge",
        f"dbms_clusters_total {cluster_total}",
        "# HELP dbms_backup_policies_total Total number of backup policies.",
        "# TYPE dbms_backup_policies_total gauge",
        f"dbms_backup_policies_total {policy_total}",
        "# HELP dbms_backup_policies_enabled Total number of enabled backup policies.",
        "# TYPE dbms_backup_policies_enabled gauge",
        f"dbms_backup_policies_enabled {policy_enabled}",
        "# HELP dbms_backup_logs_total Total number of backup logs for current Beijing day.",
        "# TYPE dbms_backup_logs_total counter",
        f"dbms_backup_logs_total {backup_log_total}",
        "# HELP dbms_backup_logs_success_total Total number of successful backup logs for current Beijing day.",
        "# TYPE dbms_backup_logs_success_total counter",
        f"dbms_backup_logs_success_total {backup_success_total}",
        "# HELP dbms_backup_logs_failed_total Total number of failed backup logs for current Beijing day.",
        "# TYPE dbms_backup_logs_failed_total counter",
        f"dbms_backup_logs_failed_total {backup_failed_total}",
        "# HELP dbms_backup_logs_running_total Total number of running backup logs for current Beijing day.",
        "# TYPE dbms_backup_logs_running_total gauge",
        f"dbms_backup_logs_running_total {backup_running_total}",
        "# HELP dbms_instances_by_type_total Total number of instances by database type.",
        "# TYPE dbms_instances_by_type_total gauge",
        f'dbms_instances_by_type_total{{db_type="mysql"}} {mysql_instance_total}',
        f'dbms_instances_by_type_total{{db_type="mongodb"}} {mongodb_instance_total}',
        f'dbms_instances_by_type_total{{db_type="redis"}} {redis_instance_total}',
        f'dbms_instances_by_type_total{{db_type="postgresql"}} {postgresql_instance_total}',
        f'dbms_instances_by_type_total{{db_type="doris"}} {doris_instance_total}',
        "# HELP dbms_instances_running_by_type_total Total number of running instances by database type.",
        "# TYPE dbms_instances_running_by_type_total gauge",
        f'dbms_instances_running_by_type_total{{db_type="mysql"}} {mysql_instance_running_total}',
        f'dbms_instances_running_by_type_total{{db_type="mongodb"}} {mongodb_instance_running_total}',
        f'dbms_instances_running_by_type_total{{db_type="redis"}} {redis_instance_running_total}',
        f'dbms_instances_running_by_type_total{{db_type="postgresql"}} {postgresql_instance_running_total}',
        f'dbms_instances_running_by_type_total{{db_type="doris"}} {doris_instance_running_total}',
        "# HELP dbms_notify_targets_total Total number of notification targets.",
        "# TYPE dbms_notify_targets_total gauge",
        f"dbms_notify_targets_total {notify_target_total}",
        "# HELP dbms_s3_storage_configs_total Total number of S3 storage configs.",
        "# TYPE dbms_s3_storage_configs_total gauge",
        f"dbms_s3_storage_configs_total {s3_config_total}",
    ]
    return Response("\n".join(lines) + "\n", mimetype="text/plain; version=0.0.4; charset=utf-8")
