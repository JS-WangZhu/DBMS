from datetime import datetime, timezone

from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.models.query_audit import QueryAuditOutbox
from app.models.user import User
from app.models.user_permission import UserMenuPermission
from app.services import query_audit


def _login(client, username="admin", password="admin123"):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['data']['access_token']}"}


def test_query_audit_event_keeps_full_statement_and_result(app):
    with app.app_context():
        user = User.query.filter_by(username="admin").first()
        statement = "SELECT '" + ("x" * 2500) + "'"
        event = query_audit.build_query_audit_event(user, {
            "db_type": "mysql",
            "cluster_id": 12,
            "database": "orders",
            "sql": statement,
        })
        query_audit.complete_query_audit_event(event, success=True, http_status=200, result={
            "columns": ["id"],
            "column_types": ["BIGINT"],
            "rows": [{"id": 1}, {"id": 2}],
            "truncated": True,
            "limit": 1000,
        })

        assert event["statement"] == statement
        assert event["result_row_count"] == 2
        assert event["result_truncated"] == 1
        assert '"column_types":["BIGINT"]' in event["result_json"]


def test_clickhouse_failure_uses_encrypted_outbox_and_retries(app, monkeypatch):
    with app.app_context():
        user = User.query.filter_by(username="admin").first()
        event = query_audit.build_query_audit_event(user, {"db_type": "redis", "query": {"command": "GET", "args": ["key"]}})
        query_audit.complete_query_audit_event(event, success=True, http_status=200, result={"rows": ["value"]})

        monkeypatch.setattr(query_audit, "insert_query_audit_event", lambda _event: (_ for _ in ()).throw(RuntimeError("offline")))
        assert query_audit.persist_query_audit_event(event) == "outbox"

        queued = QueryAuditOutbox.query.filter_by(event_id=event["event_id"]).one()
        assert b'"command"' not in queued.payload_blob
        decoded = query_audit._decode_outbox_payload(queued.payload_blob)
        assert decoded["statement"] == '{"command":"GET","args":["key"]}'
        assert decoded["result_row_count"] == 1

        inserted = []
        monkeypatch.setattr(query_audit, "insert_query_audit_event", lambda payload: inserted.append(payload))
        result = query_audit.flush_query_audit_outbox()
        assert result == {"processed": 1, "synced": 1, "failed": 0}
        assert inserted[0]["event_id"] == event["event_id"]
        assert QueryAuditOutbox.query.count() == 0


def test_query_route_audits_result_without_generic_audit_log(app, client, monkeypatch):
    with app.app_context():
        cluster = DatabaseCluster(name="audit-mysql", db_type="mysql", business_line="pay", environment="test")
        db.session.add(cluster)
        db.session.flush()
        instance = DatabaseInstance(
            name="audit-replica", db_type="mysql", host_input="127.0.0.1", port=3306,
            username="reader", cluster_id=cluster.id,
        )
        db.session.add(instance)
        db.session.commit()
        cluster_id, instance_id = cluster.id, instance.id

    import app.api.routes.data_access as routes

    monkeypatch.setattr(routes, "pick_instance", lambda *_args, **_kwargs: DatabaseInstance.query.get(instance_id))
    monkeypatch.setattr(routes, "_execute", lambda *_args, **_kwargs: (
        True,
        None,
        {"columns": ["id"], "column_types": ["BIGINT"], "rows": [{"id": 7}], "truncated": False, "limit": 1000},
    ))
    captured = []
    monkeypatch.setattr(routes, "persist_query_audit_event", lambda event: captured.append(dict(event)))

    statement = "SELECT '" + ("a" * 1500) + "' AS id"
    response = client.post("/api/v1/data-access/query", headers=_login(client), json={
        "db_type": "mysql",
        "cluster_id": cluster_id,
        "business_line": "pay",
        "environment": "test",
        "database": "orders",
        "sql": statement,
    })
    assert response.status_code == 200
    assert response.get_json()["data"]["result"]["rows"] == [{"id": 7}]
    assert captured[0]["statement"] == statement
    assert captured[0]["result_row_count"] == 1
    assert captured[0]["cluster_name"] == "audit-mysql"
    with app.app_context():
        assert AuditLog.query.filter_by(action="data_access.query").count() == 0


def test_authenticated_permission_failures_are_audited(app, client, monkeypatch):
    with app.app_context():
        user = User(username="no-query-menu", role="user", status="active", auth_source="local")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()

    import app.api.routes.data_access as routes

    captured = []
    monkeypatch.setattr(routes, "persist_query_audit_event", lambda event: captured.append(dict(event)))
    response = client.post("/api/v1/data-access/query", headers=_login(client, "no-query-menu", "password123"), json={
        "db_type": "mysql", "cluster_id": 999, "sql": "SELECT 1",
    })
    assert response.status_code == 403
    assert captured[0]["failure_stage"] == "menu_permission"
    assert captured[0]["statement"] == "SELECT 1"


def test_cluster_permission_and_validation_failures_are_audited(app, client, monkeypatch):
    with app.app_context():
        user = User(username="query-no-cluster", role="user", status="active", auth_source="local")
        user.set_password("password123")
        cluster = DatabaseCluster(name="denied-cluster", db_type="mysql", business_line="pay", environment="prod")
        db.session.add_all([user, cluster])
        db.session.flush()
        db.session.add(UserMenuPermission(user_id=user.id, menu_key="data_query"))
        db.session.commit()
        cluster_id = cluster.id

    import app.api.routes.data_access as routes

    captured = []
    monkeypatch.setattr(routes, "persist_query_audit_event", lambda event: captured.append(dict(event)))
    headers = _login(client, "query-no-cluster", "password123")
    denied = client.post("/api/v1/data-access/query", headers=headers, json={
        "db_type": "mysql", "cluster_id": cluster_id, "sql": "SELECT 1",
    })
    invalid = client.post("/api/v1/data-access/query", headers=headers, json={
        "db_type": "oracle", "cluster_id": cluster_id, "sql": "SELECT 2",
    })
    assert denied.status_code == 403
    assert invalid.status_code == 400
    assert [event["failure_stage"] for event in captured] == ["cluster_permission", "validation"]


def test_query_returns_503_when_clickhouse_and_outbox_both_fail(app, client, monkeypatch):
    import app.api.routes.data_access as routes

    def fail_persistence(_event):
        raise query_audit.QueryAuditUnavailable("查询审计暂时无法持久化")

    monkeypatch.setattr(routes, "persist_query_audit_event", fail_persistence)
    response = client.post("/api/v1/data-access/query", headers=_login(client), json={
        "db_type": "invalid", "sql": "SELECT 1",
    })
    assert response.status_code == 503
    assert "无法持久化" in response.get_json()["message"]


def test_clickhouse_schema_has_partition_ttl_and_insert_is_idempotent_ready(app, monkeypatch):
    class FakeClient:
        def __init__(self):
            self.commands = []
            self.inserts = []

        def command(self, sql):
            self.commands.append(sql)

        def insert(self, table, data, column_names):
            self.inserts.append((table, data, column_names))

    with app.app_context():
        app.config["CLICKHOUSE_AUDIT_HOST"] = "clickhouse.test"
        fake = FakeClient()
        monkeypatch.setattr(query_audit, "_get_client", lambda: fake)
        monkeypatch.setattr(query_audit, "_schema_key", None)
        query_audit.ensure_clickhouse_schema()
        ddl = "\n".join(fake.commands)
        assert "ReplacingMergeTree(version)" in ddl
        assert "PARTITION BY toYYYYMM(created_at)" in ddl
        assert "TTL created_at + INTERVAL 180 DAY DELETE" in ddl

        user = User.query.filter_by(username="admin").first()
        event = query_audit.build_query_audit_event(user, {"db_type": "mysql", "sql": "SELECT 1"})
        query_audit.complete_query_audit_event(event, success=True, http_status=200, result={"rows": [{"1": 1}]})
        query_audit.insert_query_audit_event(event)
        assert fake.inserts[0][0] == "`dbms_audit`.`query_audit_events`"
        assert fake.inserts[0][2] == query_audit.AUDIT_COLUMNS


def test_query_audit_outbox_job_is_registered_every_10_seconds(app, monkeypatch):
    from app.tasks import scheduler as scheduler_module

    for name in (
        "sync_monitor_collect_job", "sync_cache_warm_job", "sync_backup_jobs",
        "sync_inspection_job", "sync_scheduled_task_jobs", "sync_physical_discovery_job",
        "sync_parameter_collection_job",
    ):
        monkeypatch.setattr(scheduler_module, name, lambda **_kwargs: None)

    class FakeScheduler:
        def __init__(self):
            self.jobs = []

        def add_job(self, **kwargs):
            self.jobs.append(kwargs)

    fake = FakeScheduler()
    scheduler_module.register_jobs(fake, app)
    audit_job = next(job for job in fake.jobs if job["id"] == "query_audit_outbox_flush_10s")
    assert audit_job["trigger"] == "interval"
    assert audit_job["seconds"] == 10
    assert audit_job["max_instances"] == 1


def test_history_api_uses_clickhouse_service_and_detail_permission(app, client, monkeypatch):
    import app.api.routes.data_access as routes

    now = datetime.now(timezone.utc)
    item = {
        "event_id": "f9327f95-d82c-4333-bcc9-5c86545f4bf9",
        "username": "admin",
        "created_at": now.isoformat(),
        "created_at_cn": "2026-08-29 10:00:00",
        "statement": "SELECT 1",
        "success": True,
    }
    seen = {}

    def fake_list(user, page, page_size, filters):
        seen.update({"user": user.username, "page": page, "page_size": page_size, "filters": filters})
        return {"items": [item], "total": 1, "page": page, "page_size": page_size}

    monkeypatch.setattr(routes, "list_query_audits", fake_list)
    monkeypatch.setattr(routes, "get_query_audit", lambda user, event_id: {**item, "request": {}, "result": {"rows": [{"1": 1}]}})
    headers = _login(client)
    listed = client.get(
        "/api/v1/data-access/history/query",
        headers=headers,
        query_string={"keyword": "SELECT", "db_type": "mysql", "success": "true"},
    )
    assert listed.status_code == 200
    assert listed.get_json()["data"]["items"][0]["statement"] == "SELECT 1"
    assert seen["filters"]["success"] is True
    detail = client.get(f"/api/v1/data-access/history/query/{item['event_id']}", headers=headers)
    assert detail.status_code == 200
    assert detail.get_json()["data"]["result"]["rows"] == [{"1": 1}]


def test_history_filters_force_non_admin_to_own_records(app):
    with app.app_context():
        user = User(username="history-user", role="user", status="active", auth_source="local")
        user.set_password("password123")
        db.session.add(user)
        db.session.flush()
        db.session.add(UserMenuPermission(user_id=user.id, menu_key="data_history"))
        db.session.commit()

        where_sql, params = query_audit._history_filters({"user_id": 999, "success": False}, user)
        assert "current_user_id" in where_sql
        assert "user_id = {user_id" not in where_sql
        assert params["current_user_id"] == user.id
        assert params["success"] == 0

        admin = User.query.filter_by(username="admin").first()
        admin_where, admin_params = query_audit._history_filters({"username": "hist"}, admin)
        assert "positionCaseInsensitiveUTF8(username" in admin_where
        assert admin_params["username"] == "hist"
