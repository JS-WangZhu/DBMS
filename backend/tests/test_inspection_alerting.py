from datetime import datetime, timedelta

from app.extensions import db
from app.models.db_asset import DatabaseInstance
from app.models.inspection import InspectionAlert
from app.services import inspection_service


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
