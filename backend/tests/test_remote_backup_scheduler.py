def test_remote_backup_reconcile_job_is_registered_every_30_seconds(app, monkeypatch):
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

    job = fake.jobs["remote_backup_reconcile_30s"]
    assert job["trigger"] == "interval"
    assert job["seconds"] == 30
    assert job["max_instances"] == 1
    assert job["coalesce"] is True
    assert job["kwargs"] == {"app": app}


def test_remote_backup_reconcile_job_runs_sync_in_app_context(app, monkeypatch):
    from flask import current_app

    from app.tasks import scheduler as scheduler_module

    calls = []

    def sync_running_backups():
        calls.append(current_app._get_current_object())
        return 2

    monkeypatch.setattr(
        scheduler_module,
        "sync_running_remote_backups",
        sync_running_backups,
    )

    assert scheduler_module.job_reconcile_remote_backups(app) == 2
    assert calls == [app]
