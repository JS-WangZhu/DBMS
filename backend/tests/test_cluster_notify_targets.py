from types import SimpleNamespace

from app.extensions import db
from app.models.db_asset import DatabaseCluster
from app.models.notify_target import BackupNotifyTarget
from app.services import notifier


def _admin_headers(client):
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    token = response.get_json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_cluster_notify_targets_default_empty_and_can_be_updated(app, client):
    target = BackupNotifyTarget(
        name="cluster-ops",
        channel="wecom",
        address="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test",
        enabled=True,
    )
    db.session.add(target)
    db.session.commit()

    headers = _admin_headers(client)
    created = client.post(
        "/api/v1/clusters",
        json={"name": "mysql-prod", "db_type": "mysql", "business_line": "billing"},
        headers=headers,
    )
    assert created.status_code == 201
    assert created.get_json()["data"]["notify_target_ids"] == []

    cluster_id = created.get_json()["data"]["id"]
    updated = client.patch(
        f"/api/v1/clusters/{cluster_id}",
        json={"notify_target_ids": [str(target.id), target.id]},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.get_json()["data"]["notify_target_ids"] == [target.id]


def test_cluster_rejects_unknown_notify_target(client):
    response = client.post(
        "/api/v1/clusters",
        json={
            "name": "mysql-prod",
            "db_type": "mysql",
            "business_line": "billing",
            "notify_target_ids": [999999],
        },
        headers=_admin_headers(client),
    )
    assert response.status_code == 400
    assert "notification targets not found" in response.get_json()["message"]


def test_ha_notification_prefers_cluster_targets(app, monkeypatch):
    cluster_target = BackupNotifyTarget(
        name="cluster-ops",
        channel="wecom",
        address="https://cluster.example/webhook",
        enabled=True,
    )
    config_target = BackupNotifyTarget(
        name="global-ops",
        channel="wecom",
        address="https://global.example/webhook",
        enabled=True,
    )
    db.session.add_all([cluster_target, config_target])
    db.session.flush()
    cluster = DatabaseCluster(
        name="mysql-prod",
        db_type="mysql",
        business_line="billing",
        environment="prod",
        notify_target_ids=[cluster_target.id],
    )
    db.session.add(cluster)
    db.session.commit()

    called = []
    monkeypatch.setattr(
        notifier,
        "_send_wecom_markdown",
        lambda content, webhook=None: called.append(webhook) or {"ok": True, "message": "sent"},
    )
    config = SimpleNamespace(get_notify_target_ids=lambda: [config_target.id])
    result = notifier.notify_ha_switch_completion(
        config=config,
        cluster=cluster,
        switch_type="normal",
        result={},
    )

    assert result["ok"] is True
    assert called == [cluster_target.address]
