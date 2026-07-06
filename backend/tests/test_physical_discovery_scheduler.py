from app.extensions import db
from app.models.physical_discovery import PhysicalDiscoveryConfig


class FakeScheduler:
    def __init__(self):
        self.jobs = {}

    def get_job(self, job_id):
        return self.jobs.get(job_id)

    def remove_job(self, job_id):
        self.jobs.pop(job_id, None)

    def add_job(self, **kwargs):
        self.jobs[kwargs["id"]] = kwargs


def test_sync_discovery_job_obeys_global_switch_and_interval(app):
    from app.tasks.scheduler import sync_physical_discovery_job

    scheduler = FakeScheduler()
    with app.app_context():
        config = PhysicalDiscoveryConfig(enabled=False, poll_interval_minutes=12)
        db.session.add(config)
        db.session.commit()

        sync_physical_discovery_job(scheduler, app)
        assert scheduler.get_job("physical_host_discovery") is None

        config.enabled = True
        db.session.commit()
        sync_physical_discovery_job(scheduler, app)
        job = scheduler.get_job("physical_host_discovery")
        assert job["minutes"] == 12
        assert job["max_instances"] == 1
        assert job["coalesce"] is True
