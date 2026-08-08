from datetime import datetime, timedelta

from app.extensions import db
from app.models.db_asset import DatabaseInstance
from app.models.inspection import InspectionAlert
from app.services import inspection_service
from app.tasks import scheduler as task_scheduler


def _admin_headers(client):
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['data']['access_token']}"}


def test_alert_can_be_muted_and_unmuted(client, app):
    with app.app_context():
        alert = InspectionAlert(
            instance_id=1,
            db_type="mysql",
            issue_key="connectivity",
            issue_name="连通性异常",
            status="open",
        )
        db.session.add(alert)
        db.session.commit()
        alert_id = alert.id

    headers = _admin_headers(client)
    response = client.put(
        f"/api/v1/inspection/alerts/{alert_id}/mute",
        json={"duration_minutes": 120},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["is_muted"] is True

    response = client.put(
        f"/api/v1/inspection/alerts/{alert_id}/mute",
        json={"duration_minutes": 0},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["is_muted"] is False


def test_open_alert_repeats_after_interval_and_respects_mute(app, monkeypatch):
    sent = []

    def fake_collect(instance_id, instance_data, password):
        return instance_id, {"ok": False, "error": "unreachable", "collected_at": datetime.now().isoformat()}, "error"

    monkeypatch.setattr(inspection_service, "_collect_instance", fake_collect)
    monkeypatch.setattr(
        inspection_service,
        "_send_event_notification",
        lambda event_type, cfg, instance, cluster, issue: sent.append(event_type) or {"ok": True},
    )
    monkeypatch.setattr(inspection_service, "enqueue_snapshot_flush", lambda **kwargs: None)

    with app.app_context():
        instance = DatabaseInstance(
            name="mysql-alert-test",
            db_type="mysql",
            host_input="127.0.0.1",
            port=3306,
            enabled=True,
        )
        db.session.add(instance)
        cfg = inspection_service.get_or_create_inspection_config()
        cfg.notify_enabled = True
        cfg.notify_target_ids_json = [1]
        cfg.extra_json = {**(cfg.extra_json or {}), "notify_repeat_seconds": 3600}
        db.session.commit()

        assert inspection_service.run_inspection_cycle(force=True)["ok"] is True
        alert = InspectionAlert.query.filter_by(instance_id=instance.id, issue_key="connectivity").one()
        assert alert.notify_count == 1

        assert inspection_service.run_inspection_cycle(force=True)["ok"] is True
        db.session.refresh(alert)
        assert alert.notify_count == 1

        alert.last_notified_at = datetime.now() - timedelta(seconds=3601)
        db.session.commit()
        assert inspection_service.run_inspection_cycle(force=True)["ok"] is True
        db.session.refresh(alert)
        assert alert.notify_count == 2

        alert.last_notified_at = datetime.now() - timedelta(seconds=3601)
        alert.muted_at = datetime.now()
        alert.muted_until = datetime.now() + timedelta(hours=1)
        db.session.commit()
        assert inspection_service.run_inspection_cycle(force=True)["ok"] is True
        db.session.refresh(alert)
        assert alert.notify_count == 2
        assert sent.count("alert") == 2


def test_failed_recovery_notification_is_retried(app, monkeypatch):
    results = iter([
        {"ok": False, "error": "request timeout"},
        {"ok": True, "ping_ok": True},
        {"ok": True, "ping_ok": True},
    ])
    sent = []

    monkeypatch.setattr(inspection_service, "_collect_instance", lambda instance_id, *_args: (instance_id, next(results), "running"))
    monkeypatch.setattr(inspection_service, "enqueue_snapshot_flush", lambda **kwargs: None)

    def fake_notify(event_type, *_args):
        sent.append(event_type)
        if event_type == "recovery" and sent.count("recovery") == 1:
            return {"ok": False, "message": "webhook timeout"}
        return {"ok": True}

    monkeypatch.setattr(inspection_service, "_send_event_notification", fake_notify)

    with app.app_context():
        instance = DatabaseInstance(name="recovery-retry", db_type="mysql", host_input="127.0.0.1", port=3306, enabled=True)
        db.session.add(instance)
        cfg = inspection_service.get_or_create_inspection_config()
        cfg.notify_enabled = True
        cfg.notify_recovery = True
        cfg.notify_target_ids_json = [1]
        db.session.commit()

        inspection_service.run_inspection_cycle(force=True)
        inspection_service.run_inspection_cycle(force=True)
        alert = InspectionAlert.query.filter_by(instance_id=instance.id, issue_key="connectivity").one()
        assert alert.status == "recovered"
        assert alert.recovery_notified_at is None

        inspection_service.run_inspection_cycle(force=True)
        db.session.refresh(alert)
        assert alert.recovery_notified_at is not None
        assert sent.count("recovery") == 2


def test_alert_lifecycle_is_committed_before_recovery_notification(app, monkeypatch):
    results = iter([
        {"ok": False, "error": "request timeout"},
        {"ok": True, "ping_ok": True},
    ])
    dirty_alerts_at_notification = []

    monkeypatch.setattr(
        inspection_service,
        "_collect_instance",
        lambda instance_id, *_args: (instance_id, next(results), "running"),
    )
    monkeypatch.setattr(inspection_service, "enqueue_snapshot_flush", lambda **kwargs: None)

    def fake_notify(event_type, *_args):
        if event_type == "recovery":
            dirty_alerts_at_notification.extend(
                row for row in db.session.dirty if isinstance(row, InspectionAlert)
            )
        return {"ok": True}

    monkeypatch.setattr(inspection_service, "_send_event_notification", fake_notify)

    with app.app_context():
        instance = DatabaseInstance(
            name="recovery-commit-boundary",
            db_type="mysql",
            host_input="127.0.0.1",
            port=3306,
            enabled=True,
        )
        db.session.add(instance)
        cfg = inspection_service.get_or_create_inspection_config()
        cfg.notify_enabled = True
        cfg.notify_recovery = True
        cfg.notify_target_ids_json = [1]
        db.session.commit()

        assert inspection_service.run_inspection_cycle(force=True)["ok"] is True
        assert inspection_service.run_inspection_cycle(force=True)["ok"] is True
        assert dirty_alerts_at_notification == []


def test_full_inspection_does_not_recover_status_probe_alert(app, monkeypatch):
    monkeypatch.setattr(
        inspection_service,
        "_collect_instance",
        lambda instance_id, *_args: (
            instance_id,
            {"ok": True, "ping_ok": True, "collected_at": datetime.now().isoformat()},
            "running",
        ),
    )
    monkeypatch.setattr(inspection_service, "enqueue_snapshot_flush", lambda **kwargs: None)

    with app.app_context():
        instance = DatabaseInstance(
            name="status-alert-owner",
            db_type="mysql",
            host_input="127.0.0.1",
            port=3306,
            enabled=True,
        )
        db.session.add(instance)
        db.session.flush()
        alert = InspectionAlert(
            instance_id=instance.id,
            db_type="mysql",
            issue_key="instance_status_probe",
            issue_name="实例状态异常",
            status="open",
            first_seen_at=datetime.now(),
            last_seen_at=datetime.now(),
        )
        db.session.add(alert)
        db.session.commit()

        result = inspection_service.run_inspection_cycle(force=True)
        db.session.refresh(alert)

        assert result["ok"] is True
        assert alert.status == "open"
        assert alert.recovered_at is None


def test_instance_status_probe_alert_opens_and_recovers(app, monkeypatch):
    sent = []
    dirty_alerts_at_notification = []

    def fake_notify(event_type, *_args):
        sent.append(event_type)
        if event_type == "recovery":
            dirty_alerts_at_notification.extend(
                row for row in db.session.dirty if isinstance(row, InspectionAlert)
            )
        return {"ok": True}

    monkeypatch.setattr(inspection_service, "_send_event_notification", fake_notify)

    with app.app_context():
        instance = DatabaseInstance(
            name="status-probe-alert",
            db_type="mysql",
            host_input="127.0.0.1",
            port=3306,
            enabled=True,
        )
        db.session.add(instance)
        cfg = inspection_service.get_or_create_inspection_config()
        cfg.notify_enabled = True
        cfg.notify_recovery = True
        cfg.notify_target_ids_json = [1]
        db.session.commit()

        result = inspection_service.reconcile_instance_status_alerts(
            [instance],
            {instance.id: {"ok": False, "error": "connect timeout"}},
            cfg,
        )
        db.session.commit()
        alert = InspectionAlert.query.filter_by(
            instance_id=instance.id,
            issue_key="instance_status_probe",
        ).one()
        assert result["opened"] == 1
        assert alert.status == "open"
        assert alert.message == "connect timeout"
        assert alert.notify_count == 1
        assert sent == ["alert"]

        result = inspection_service.reconcile_instance_status_alerts(
            [instance],
            {instance.id: {"ok": True, "ping_ok": True}},
            cfg,
        )
        db.session.commit()
        db.session.refresh(alert)
        assert result["recovered"] == 1
        assert alert.status == "recovered"
        assert alert.recovered_at is not None
        assert alert.recovery_notified_at is not None
        assert sent == ["alert", "recovery"]
        assert dirty_alerts_at_notification == []


def test_instance_status_probe_missing_result_is_an_alert(app, monkeypatch):
    monkeypatch.setattr(
        inspection_service,
        "_send_event_notification",
        lambda *_args: {"ok": False},
    )

    with app.app_context():
        instance = DatabaseInstance(
            name="status-probe-missing",
            db_type="redis",
            host_input="127.0.0.1",
            port=6379,
            enabled=True,
        )
        db.session.add(instance)
        db.session.commit()

        result = inspection_service.reconcile_instance_status_alerts([instance], {})
        db.session.commit()
        alert = InspectionAlert.query.filter_by(
            instance_id=instance.id,
            issue_key="instance_status_probe",
        ).one()
        assert result["opened"] == 1
        assert alert.status == "open"
        assert alert.message == "instance status probe returned no result"


def test_monitor_collect_drives_status_alert_and_recovery(app, monkeypatch):
    probe_results = iter([
        {"ok": False, "error": "network timeout"},
        {"ok": True, "ping_ok": True},
    ])
    monkeypatch.setattr(
        task_scheduler,
        "_collect_instance_snapshot",
        lambda instance_id, *_args: (
            instance_id,
            (payload := next(probe_results)),
            "running" if payload.get("ok") and payload.get("ping_ok") else "error",
        ),
    )
    monkeypatch.setattr(task_scheduler, "_cache_and_flush_monitor_snapshot", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(task_scheduler, "_refresh_mysql_cluster_ha", lambda *_args: None)
    monkeypatch.setattr(task_scheduler, "_refresh_cluster_topology_history", lambda *_args: None)
    monkeypatch.setattr(task_scheduler, "warm_instance_list_cache", lambda: None)
    monkeypatch.setattr(
        inspection_service,
        "_send_event_notification",
        lambda *_args: {"ok": True},
    )

    with app.app_context():
        instance = DatabaseInstance(
            name="monitor-alert-integration",
            db_type="redis",
            host_input="127.0.0.1",
            port=6379,
            enabled=True,
        )
        db.session.add(instance)
        cfg = inspection_service.get_or_create_inspection_config()
        cfg.notify_enabled = True
        cfg.notify_recovery = True
        cfg.notify_target_ids_json = [1]
        db.session.commit()

        task_scheduler.job_monitor_collect(app)
        alert = InspectionAlert.query.filter_by(
            instance_id=instance.id,
            issue_key="instance_status_probe",
        ).one()
        assert alert.status == "open"
        assert alert.message == "network timeout"

        task_scheduler.job_monitor_collect(app)
        db.session.refresh(alert)
        assert alert.status == "recovered"
        assert alert.recovery_notified_at is not None
