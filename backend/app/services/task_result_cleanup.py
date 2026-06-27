from datetime import datetime, timedelta

from app.extensions import db
from app.models.backup import BackupLog
from app.models.task_management import ScheduledTaskRun


def cleanup_expired_task_results(retain_days: int = 30, now: datetime = None) -> dict:
    retain_days = max(1, int(retain_days or 30))
    cutoff = (now or datetime.utcnow()) - timedelta(days=retain_days)
    backup_deleted = (
        BackupLog.query
        .filter(BackupLog.started_at < cutoff)
        .delete(synchronize_session=False)
    )
    task_deleted = (
        ScheduledTaskRun.query
        .filter(ScheduledTaskRun.started_at < cutoff)
        .delete(synchronize_session=False)
    )
    db.session.commit()
    return {
        "retain_days": retain_days,
        "cutoff": cutoff.isoformat(),
        "backup_results_deleted": backup_deleted,
        "task_results_deleted": task_deleted,
        "total_deleted": backup_deleted + task_deleted,
    }
