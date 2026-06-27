from datetime import datetime, timedelta

from app.extensions import db
from app.models.backup import BackupLog, BackupPolicy
from app.models.task_management import ScheduledTask, ScheduledTaskRun
from app.services.task_result_cleanup import cleanup_expired_task_results


def test_cleanup_expired_backup_and_scheduled_task_results(app):
    now = datetime(2026, 6, 27, 2, 0, 0)
    old_time = now - timedelta(days=31)
    recent_time = now - timedelta(days=29)
    with app.app_context():
        policy = BackupPolicy(
            name="cleanup-test",
            target_type="instance",
            target_id=1,
            db_type="mysql",
            backup_type="full",
            tool_name="mysqldump",
            cron_expr="0 1 * * *",
            storage_path="/tmp",
        )
        task = ScheduledTask(
            name="cleanup-test",
            task_type="shell",
            cron_expr="0 1 * * *",
        )
        db.session.add_all([policy, task])
        db.session.flush()
        db.session.add_all([
            BackupLog(policy_id=policy.id, started_at=old_time, status="failed"),
            BackupLog(policy_id=policy.id, started_at=recent_time, status="success"),
            ScheduledTaskRun(task_id=task.id, started_at=old_time, status="failed"),
            ScheduledTaskRun(task_id=task.id, started_at=recent_time, status="success"),
        ])
        db.session.commit()

        result = cleanup_expired_task_results(retain_days=30, now=now)

        assert result["backup_results_deleted"] == 1
        assert result["task_results_deleted"] == 1
        assert result["total_deleted"] == 2
        assert BackupLog.query.count() == 1
        assert ScheduledTaskRun.query.count() == 1

def test_cleanup_job_is_registered_for_2am(app, monkeypatch):
    from app.tasks import scheduler as scheduler_module

    class FakeScheduler:
        def __init__(self):
            self.jobs = {}

        def add_job(self, **kwargs):
            self.jobs[kwargs["id"]] = kwargs

    fake = FakeScheduler()
    for name in (
        "sync_monitor_collect_job",
        "sync_cache_warm_job",
        "sync_backup_jobs",
        "sync_inspection_job",
        "sync_scheduled_task_jobs",
    ):
        monkeypatch.setattr(scheduler_module, name, lambda **kwargs: None)

    scheduler_module.register_jobs(fake, app)

    job = fake.jobs["task_result_cleanup_daily"]
    assert "hour='2'" in str(job["trigger"])
    assert "minute='0'" in str(job["trigger"])
    assert job["kwargs"]["retain_days"] == 30

