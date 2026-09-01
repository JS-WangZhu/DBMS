import time
from types import SimpleNamespace

from app.extensions import db
from app.models.db_asset import DatabaseInstance
from app.tasks import scheduler as task_scheduler


def test_monitor_collect_timeout_is_applied_per_instance(app, monkeypatch):
    collected = []

    def slow_collect(instance_id, *_args):
        time.sleep(0.6)
        return instance_id, {"ok": True, "ping_ok": True}, "running"

    monkeypatch.setattr(task_scheduler, "_collect_instance_snapshot", slow_collect)
    monkeypatch.setattr(
        task_scheduler,
        "get_or_create_instance_status_config",
        lambda: SimpleNamespace(metric_refresh_timeout_seconds=1),
    )
    monkeypatch.setattr(
        task_scheduler,
        "_cache_and_flush_monitor_snapshot",
        lambda instance, payload, status: collected.append((instance.id, payload, status)),
    )
    monkeypatch.setattr(task_scheduler, "_refresh_mysql_cluster_ha", lambda *_args: None)
    monkeypatch.setattr(task_scheduler, "_refresh_cluster_topology_history", lambda *_args: None)
    monkeypatch.setattr(task_scheduler, "reconcile_instance_status_alerts", lambda *_args: {})
    monkeypatch.setattr(task_scheduler, "warm_instance_list_cache", lambda: None)

    with app.app_context():
        app.config["MONITOR_COLLECT_WORKERS"] = 1
        instances = [
            DatabaseInstance(
                name=f"per-instance-timeout-{index}",
                db_type="redis",
                host_input=f"127.0.0.{index}",
                port=6379,
                enabled=True,
            )
            for index in (1, 2)
        ]
        db.session.add_all(instances)
        db.session.commit()
        instance_ids = {item.id for item in instances}

        task_scheduler.job_monitor_collect(app)

        successful_ids = {
            instance_id
            for instance_id, payload, status in collected
            if instance_id in instance_ids and payload.get("ok") and status == "running"
        }
        assert successful_ids == instance_ids
