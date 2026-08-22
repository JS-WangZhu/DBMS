import json
from datetime import datetime

from app.extensions import db
from app.models.backup import BackupLog, BackupPolicy
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.models.inspection import InspectionAlert, InspectionConfig
from app.models.user import User
from app.models.user_permission import ApiKey


def _seed_mcp_resources():
    cluster = DatabaseCluster(
        name="orders-prod",
        db_type="mysql",
        business_line="orders",
        environment="prod",
        ha_mode="dbms",
    )
    db.session.add(cluster)
    db.session.flush()
    instance = DatabaseInstance(
        name="orders-primary",
        db_type="mysql",
        host_input="db-orders.example.com",
        resolved_ip="10.0.0.8",
        port=3306,
        cluster_id=cluster.id,
        enabled=True,
        running_status="running",
    )
    db.session.add(instance)
    db.session.flush()
    policy = BackupPolicy(
        name="orders-full",
        target_type="instance",
        target_id=instance.id,
        db_type="mysql",
        backup_type="full",
        tool_name="mysqldump",
        cron_expr="0 2 * * *",
        storage_path="/secret/backup/path",
        retain_days=7,
        compress=True,
        enabled=True,
    )
    db.session.add(policy)
    db.session.flush()
    log = BackupLog(
        policy_id=policy.id,
        started_at=datetime.utcnow(),
        finished_at=datetime.utcnow(),
        file_path="/secret/backup/path/orders.sql.gz",
        size_bytes=1024,
        status="success",
        extra_json={},
    )
    alert = InspectionAlert(
        instance_id=instance.id,
        cluster_id=cluster.id,
        db_type="mysql",
        issue_key="mysql_connection_usage",
        issue_name="MySQL 连接使用率过高",
        severity="warning",
        status="open",
        message="连接使用率 95%",
        first_seen_at=datetime.utcnow(),
        last_seen_at=datetime.utcnow(),
    )
    config = InspectionConfig(
        enabled=True,
        interval_seconds=60,
        collect_timeout_seconds=8,
        notify_enabled=True,
        notify_recovery=True,
        extra_json={"thresholds": {"mysql_connection_usage_pct": 88}},
    )
    db.session.add_all([log, alert, config])
    db.session.commit()
    return cluster, instance, policy


def test_instance_status_supports_exact_instance_filters(app, monkeypatch):
    from app.services import mcp_status

    monkeypatch.setattr(mcp_status, "latest_snapshots_by_instance_ids", lambda *_args: {})
    with app.app_context():
        _cluster, instance, _policy = _seed_mcp_resources()
        other = DatabaseInstance(name="other", db_type="redis", host_input="10.0.0.9", port=6379)
        db.session.add(other)
        db.session.commit()

        result = mcp_status.build_mcp_instance_status({"instance_id": instance.id})
        assert result["summary"]["total"] == 1
        assert result["instances"][0]["id"] == instance.id

        result = mcp_status.build_mcp_instance_status({
            "instance_name": "orders-primary",
            "host": "db-orders.example.com",
            "port": 3306,
        })
        assert [row["id"] for row in result["instances"]] == [instance.id]


def test_mcp_resource_builders_return_safe_complete_views(app):
    from app.services.mcp_resources import (
        build_mcp_backup_status,
        build_mcp_cluster_instance_map,
        build_mcp_inspection_status,
    )

    with app.app_context():
        cluster, instance, _policy = _seed_mcp_resources()

        mapping = build_mcp_cluster_instance_map(allowed_cluster_ids=[cluster.id])
        assert mapping["summary"] == {"cluster_total": 1, "instance_total": 1, "unassigned_instance_total": 0}
        assert mapping["clusters"][0]["instances"][0]["id"] == instance.id
        assert "username" not in mapping["clusters"][0]["instances"][0]

        backup = build_mcp_backup_status(allowed_cluster_ids=[cluster.id])
        assert backup["summary"]["by_protection_status"] == {"healthy": 1}
        assert backup["instances"][0]["policies"][0]["latest_backup"]["status"] == "success"
        encoded_backup = json.dumps(backup, ensure_ascii=False)
        assert "/secret/backup/path" not in encoded_backup
        assert "file_path" not in encoded_backup

        inspection = build_mcp_inspection_status(allowed_cluster_ids=[cluster.id])
        assert inspection["summary"]["inspection_item_total"] == 25
        assert inspection["summary"]["open_alert_total"] == 1
        assert inspection["assets"][0]["inspection_status"] == "abnormal"
        threshold = next(row for row in inspection["inspection_items"] if row["issue_key"] == "mysql_connection_high")
        assert threshold["threshold"] == 88.0
        assert "last_payload_json" not in inspection["alerts"][0]


def test_streamable_http_lists_and_calls_all_mcp_tools(client, app, monkeypatch):
    from app.services import mcp_status

    monkeypatch.setattr(mcp_status, "latest_snapshots_by_instance_ids", lambda *_args: {})
    with app.app_context():
        _cluster, instance, _policy = _seed_mcp_resources()
        admin = User.query.filter_by(username="admin").first()
        key = ApiKey(
            user_id=admin.id,
            name="mcp-test",
            token="mcp_test_resource_tools",
            purpose="mcp",
            scopes=["instance_status:read"],
            status="active",
        )
        current_key = ApiKey(
            user_id=admin.id,
            name="mcp-current-scope-test",
            token="mcp_test_current_scope",
            purpose="mcp",
            scopes=["dbms:read"],
            status="active",
        )
        db.session.add_all([key, current_key])
        db.session.commit()
        instance_id = instance.id

    headers = {"X-API-Key": "mcp_test_resource_tools"}
    listed = client.post(
        "/api/v1/mcp",
        headers=headers,
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert listed.status_code == 200
    names = {row["name"] for row in listed.get_json()["result"]["tools"]}
    assert names == {
        "dbms_get_latest_instance_status",
        "dbms_get_cluster_instance_mapping",
        "dbms_get_database_backup_status",
        "dbms_get_inspection_status",
    }

    called = client.post(
        "/api/v1/mcp",
        headers=headers,
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "dbms_get_latest_instance_status", "arguments": {"instance_id": instance_id}},
        },
    )
    payload = json.loads(called.get_json()["result"]["content"][0]["text"])
    assert payload["summary"]["total"] == 1
    assert payload["instances"][0]["id"] == instance_id

    for tool_name, result_key in (
        ("dbms_get_cluster_instance_mapping", "clusters"),
        ("dbms_get_database_backup_status", "instances"),
        ("dbms_get_inspection_status", "inspection_items"),
    ):
        response = client.post(f"/api/v1/mcp/tools/{tool_name}", headers=headers, json={})
        assert response.status_code == 200
        assert result_key in response.get_json()["data"]

    current_scope_response = client.post(
        "/api/v1/mcp/tools/dbms_get_cluster_instance_mapping",
        headers={"X-API-Key": "mcp_test_current_scope"},
        json={},
    )
    assert current_scope_response.status_code == 200


def test_stdio_adapter_lists_and_forwards_all_mcp_tools(monkeypatch):
    import mcp_server

    names = {row["name"] for row in mcp_server._list_tools()["tools"]}
    assert names == {
        "dbms_get_latest_instance_status",
        "dbms_get_cluster_instance_mapping",
        "dbms_get_database_backup_status",
        "dbms_get_inspection_status",
    }

    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"ok": True, "data": {"summary": {"cluster_total": 1}}}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["kwargs"] = kwargs
        return Response()

    monkeypatch.setenv("DBMS_BASE_URL", "https://dbms.example")
    monkeypatch.setenv("DBMS_MCP_API_KEY", "mcp_test")
    monkeypatch.setattr(mcp_server.requests, "post", fake_post)

    result = mcp_server._call_tool("dbms_get_cluster_instance_mapping", {"enabled_only": True})
    assert result == {"summary": {"cluster_total": 1}}
    assert captured["url"] == "https://dbms.example/api/v1/mcp/tools/dbms_get_cluster_instance_mapping"
    assert captured["kwargs"]["json"] == {"enabled_only": True}
