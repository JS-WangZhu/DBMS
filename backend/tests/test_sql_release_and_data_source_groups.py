from app.extensions import db
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.models.backup_agent import BackupAgent
from app.models.sql_release import SqlRelease, SqlReleaseRollbackBackup
from app.models.user import User
from app.models.user_permission import UserClusterPermission, UserMenuPermission
from app.models.user_permission import DataSourceGroupClusterPermission, UserDataSourceGroup
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable
from types import SimpleNamespace
from datetime import datetime
import re

import pytest
from flask import g
from app.utils.crypto import decrypt_secret, encrypt_secret

from app.services.sql_release_service import (
    PartialRollbackExecutionError,
    _analyze_dml,
    _analyze_postgresql_dml,
    execute_mongodb_with_partial_rollback,
    execute_mysql_with_partial_rollback,
    execute_postgresql_with_partial_rollback,
    validate_mongo_release_statement,
)
from app.services.sql_release_review import run_sql_release_review


def _login(client, username, password):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['data']['access_token']}"}


def _assets(app):
    with app.app_context():
        user = User(username="release-user", role="user", status="active", auth_source="local")
        user.set_password("password123")
        cluster = DatabaseCluster(name="mysql-release", db_type="mysql", business_line="billing", environment="test")
        db.session.add_all([user, cluster])
        db.session.flush()
        instance = DatabaseInstance(name="mysql-primary", db_type="mysql", host_input="127.0.0.1", port=3306, username="root", cluster_id=cluster.id)
        db.session.add(instance)
        db.session.commit()
        return user.id, cluster.id, instance.id


def test_rejected_release_can_be_force_submitted_by_applicant(app, client):
    user_id, cluster_id, instance_id = _assets(app)
    with app.app_context():
        db.session.add_all([
            UserMenuPermission(user_id=user_id, menu_key="sql_release_apply"),
            UserClusterPermission(user_id=user_id, cluster_id=cluster_id, can_change=True),
        ])
        release = SqlRelease(
            title="known risk", applicant_id=user_id, cluster_id=cluster_id, instance_id=instance_id,
            db_type="mysql", database_name="billing", sql_text="UPDATE orders SET status='paid' WHERE id=1;",
            status="review_rejected", ai_passed=False, force_submitted=False,
            review_json=[{"line": 1, "sql": "UPDATE orders", "passed": False, "status": "completed"}],
        )
        db.session.add(release)
        db.session.commit()
        release_id = release.id

    response = client.post(
        f"/api/v1/sql-releases/{release_id}/force-submit",
        headers=_login(client, "release-user", "password123"),
    )
    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "pending"
    assert response.get_json()["data"]["force_submitted"] is True


def test_agent_bound_release_executes_through_agent_as_current_dbms_user(app, client, monkeypatch):
    with app.app_context():
        admin = User.query.filter_by(username="admin").one()
        cluster = DatabaseCluster(name="agent-release", db_type="mysql", business_line="billing", environment="test")
        agent = BackupAgent(name="release-agent", url="http://agent.example", enabled=True)
        db.session.add_all([cluster, agent])
        db.session.flush()
        instance = DatabaseInstance(
            name="agent-primary", db_type="mysql", host_input="10.0.0.10", port=3306,
            username="dbms", cluster_id=cluster.id, access_mode="agent", probe_agent_id=agent.id,
        )
        db.session.add(instance)
        db.session.flush()
        release = SqlRelease(
            title="agent execute", applicant_id=admin.id, cluster_id=cluster.id, instance_id=instance.id,
            db_type="mysql", database_name="billing", sql_text="UPDATE orders SET status='paid' WHERE id=1;",
            status="pending", ai_passed=True, force_submitted=False, review_json=[],
        )
        db.session.add(release)
        db.session.commit()
        release_id = release.id

    called = {}
    def fake_agent_execute(instance, database, statements, db_type, seed_nodes=None):
        called.update(instance_id=instance.id, database=database, statements=statements, db_type=db_type, database_user=instance.username)
        return {"affected_rows": 1, "statement_count": 1, "statements": [{
            "line": 1, "sql": statements[0], "status": "success", "affected_rows": 1, "backup_rows": 0,
        }]}

    monkeypatch.setattr("app.api.routes.sql_releases.execute_sql_release_on_agent", fake_agent_execute)
    response = client.post(
        f"/api/v1/sql-releases/{release_id}/execute",
        headers=_login(client, "admin", "admin123"),
    )
    assert response.status_code == 200, response.get_json()
    assert called["database_user"] == "dbms"
    assert response.get_json()["data"]["execution_mode"] == "agent"
    assert response.get_json()["data"]["execution_agent_name"] == "release-agent"
    assert response.get_json()["data"]["execution_result"]["execution_source"] == "agent"


def test_review_release_calls_ai_and_reports_progress_per_statement(app, monkeypatch):
    from app.models.ai_config import AIModelConfig
    import app.services.sql_release_service as release_service

    _, _, instance_id = _assets(app)
    calls = []
    progress = []

    def fake_post(_url, headers, json, timeout):
        calls.append(json["messages"][1]["content"])
        line = len(calls)
        content = (
            f'{{"summary":"第 {line} 条完成","items":['
            f'{{"line":{line},"passed":true,"risk_level":"low","reason":"安全","suggestion":""}}]}}'
        )
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"choices": [{"message": {"content": content}}]},
        )

    monkeypatch.setattr(release_service, "get_mysql_metadata", lambda *_args: {"tables": []})
    monkeypatch.setattr("requests.post", fake_post)
    with app.app_context():
        db.session.add(AIModelConfig(
            name="release-review", api_url="http://ai.example/v1", api_key="test",
            model_name="test-model", is_default=True, enabled=True,
        ))
        db.session.commit()
        instance = DatabaseInstance.query.get(instance_id)
        reviews, summary = release_service.review_release(
            instance,
            "billing",
            ["UPDATE orders SET status='paid' WHERE id=1", "DELETE FROM orders WHERE id=2"],
            progress_callback=lambda item, total: progress.append((item["line"], total)),
        )

    assert len(calls) == 2
    assert progress == [(1, 2), (2, 2)]
    assert [item["status"] for item in reviews] == ["completed", "completed"]
    assert summary == "AI 初审完成：2/2 条通过"


def test_data_source_group_and_direct_permissions_include_execute(app, client):
    user_id, cluster_id, _ = _assets(app)
    admin_headers = _login(client, "admin", "admin123")
    created = client.post(
        "/api/v1/data-source-permissions/groups",
        headers=admin_headers,
        json={"name": "billing-writers", "permissions": [{"cluster_id": cluster_id, "can_change": True}]},
    )
    assert created.status_code == 201
    group_id = created.get_json()["data"]["id"]
    updated = client.put(
        f"/api/v1/data-source-permissions/users/{user_id}",
        headers=admin_headers,
        json={
            "group_ids": [group_id],
            "direct_permissions": [{"cluster_id": cluster_id, "can_execute": True}],
        },
    )
    assert updated.status_code == 200
    detail = client.get(f"/api/v1/data-source-permissions/users/{user_id}", headers=admin_headers).get_json()["data"]
    effective = {row["cluster_id"]: row for row in detail["effective_permissions"]}
    assert effective[cluster_id]["can_change"] is True
    assert effective[cluster_id]["can_query"] is False
    assert effective[cluster_id]["can_execute"] is True


def test_submit_is_immediate_and_async_rejection_requires_execution_confirmation(app, client, monkeypatch):
    user_id, cluster_id, instance_id = _assets(app)
    with app.app_context():
        db.session.add_all([
            UserMenuPermission(user_id=user_id, menu_key="sql_release_apply"),
            UserMenuPermission(user_id=user_id, menu_key="sql_release_history"),
            UserClusterPermission(user_id=user_id, cluster_id=cluster_id, can_change=True),
        ])
        db.session.commit()

    import app.api.routes.sql_releases as routes
    monkeypatch.setattr(routes, "pick_instance", lambda *args, **kwargs: DatabaseInstance.query.get(instance_id))
    monkeypatch.setattr(routes, "list_mysql_objects", lambda *args, **kwargs: {
        "database": "billing",
        "tables": [{"name": "orders", "row_count": 12, "size_bytes": 4096}],
        "views": [{"name": "paid_orders"}],
        "procedures": [], "functions": [], "triggers": [], "events": [],
    })
    monkeypatch.setattr(routes, "list_mysql_table_columns", lambda *args, **kwargs: [{
        "name": "id", "data_type": "bigint", "column_type": "bigint", "column_key": "PRI",
        "nullable": False, "default": None, "comment": "订单ID", "position": 1,
    }])
    dispatched = []
    monkeypatch.setattr(routes, "dispatch_sql_release_review", lambda _app, release_id: dispatched.append(release_id))
    import app.services.sql_release_review as review_worker
    monkeypatch.setattr(review_worker, "review_release", lambda *args: ([{
        "line": 1, "sql": "DELETE FROM orders", "passed": False, "risk_level": "high",
        "reason": "缺少 WHERE 条件", "suggestion": "增加精确 WHERE 条件",
    }], "存在高风险语句"))
    monkeypatch.setattr(
        routes,
        "execute_mysql_with_partial_rollback",
        lambda *_args, **_kwargs: ({"affected_rows": 1}, "/tmp/release-rollback.sql"),
    )
    user_headers = _login(client, "release-user", "password123")
    overview = client.get(
        "/api/v1/sql-releases/mysql/objects",
        headers=user_headers,
        query_string={"cluster_id": cluster_id, "database": "billing"},
    )
    assert overview.status_code == 200
    assert overview.get_json()["data"]["tables"][0]["name"] == "orders"
    columns = client.get(
        "/api/v1/sql-releases/mysql/columns",
        headers=user_headers,
        query_string={"cluster_id": cluster_id, "database": "billing", "table": "orders"},
    )
    assert columns.status_code == 200
    assert columns.get_json()["data"]["columns"][0]["name"] == "id"
    payload = {"title": "危险删除", "cluster_id": cluster_id, "database": "billing", "sql": "DELETE FROM orders;"}
    mismatched = client.post(
        "/api/v1/sql-releases",
        headers=user_headers,
        json={**payload, "project": "another-project", "db_type": "mysql"},
    )
    assert mismatched.status_code == 400
    assert "project does not match cluster" in mismatched.get_json()["message"]
    mismatched_environment = client.post(
        "/api/v1/sql-releases",
        headers=user_headers,
        json={**payload, "project": "billing", "db_type": "mysql", "environment": "prod"},
    )
    assert mismatched_environment.status_code == 400
    assert "environment does not match cluster" in mismatched_environment.get_json()["message"]
    submitted = client.post("/api/v1/sql-releases", headers=user_headers, json=payload)
    assert submitted.status_code == 201
    assert submitted.get_json()["data"]["status"] == "reviewing"
    release_id = submitted.get_json()["data"]["id"]
    assert dispatched == [release_id]
    assert submitted.get_json()["data"]["reviews"][0]["status"] == "pending"
    assert submitted.get_json()["data"]["review_progress"] == {"completed": 0, "total": 1, "percent": 0}
    progress = client.get(
        f"/api/v1/sql-releases/{release_id}/review-progress",
        headers=user_headers,
    )
    assert progress.status_code == 200

    run_sql_release_review(app, release_id)
    with app.app_context():
        release = SqlRelease.query.get(release_id)
        assert release.status == "review_rejected"
        assert release.review_json[0]["passed"] is False

    history = client.get("/api/v1/sql-releases", headers=user_headers)
    assert history.status_code == 200
    assert [row["applicant_id"] for row in history.get_json()["data"]["items"]] == [user_id]
    g.pop("current_user", None)
    admin_headers = _login(client, "admin", "admin123")
    without_confirmation = client.post(f"/api/v1/sql-releases/{release_id}/execute", headers=admin_headers)
    assert without_confirmation.status_code == 409
    confirmed = client.post(
        f"/api/v1/sql-releases/{release_id}/execute",
        headers=admin_headers,
        json={"confirm_risk": True},
    )
    assert confirmed.status_code == 200
    with app.app_context():
        assert SqlRelease.query.get(release_id).force_submitted is True


def test_personal_execute_permission_scopes_history_and_execution(app, client, monkeypatch):
    applicant_id, cluster_id, instance_id = _assets(app)
    with app.app_context():
        executor = User(username="release-executor", role="user", status="active", auth_source="local")
        executor.set_password("password123")
        outsider = User(username="release-outsider", role="user", status="active", auth_source="local")
        outsider.set_password("password123")
        unauthorized_cluster = DatabaseCluster(
            name="mysql-unauthorized",
            db_type="mysql",
            business_line="other",
            environment="test",
        )
        db.session.add_all([executor, outsider, unauthorized_cluster])
        db.session.flush()
        unauthorized_instance = DatabaseInstance(
            name="mysql-unauthorized-primary",
            db_type="mysql",
            host_input="127.0.0.2",
            port=3306,
            username="root",
            cluster_id=unauthorized_cluster.id,
        )
        db.session.add(unauthorized_instance)
        db.session.flush()
        db.session.add_all([
            UserMenuPermission(user_id=applicant_id, menu_key="sql_release_history"),
            UserMenuPermission(user_id=executor.id, menu_key="sql_release_history"),
            UserClusterPermission(user_id=executor.id, cluster_id=cluster_id, can_execute=True),
            SqlRelease(
                title="execute permission",
                applicant_id=applicant_id,
                cluster_id=cluster_id,
                instance_id=instance_id,
                database_name="billing",
                sql_text="UPDATE orders SET status='paid' WHERE id=1;",
                status="pending",
                ai_passed=True,
                force_submitted=False,
                review_json=[{"line": 1, "sql": "UPDATE orders", "passed": True}],
            ),
            SqlRelease(
                title="unauthorized release",
                applicant_id=outsider.id,
                cluster_id=unauthorized_cluster.id,
                instance_id=unauthorized_instance.id,
                database_name="other_db",
                sql_text="UPDATE records SET status='done' WHERE id=1;",
                status="pending",
                ai_passed=True,
                force_submitted=False,
                review_json=[{"line": 1, "sql": "UPDATE records", "passed": True}],
            ),
        ])
        db.session.commit()
        release_id = SqlRelease.query.filter_by(title="execute permission").first().id
        unauthorized_release_id = SqlRelease.query.filter_by(title="unauthorized release").first().id

    import app.api.routes.sql_releases as routes
    monkeypatch.setattr(
        routes,
        "execute_mysql_with_partial_rollback",
        lambda *_args, **_kwargs: ({"affected_rows": 1}, None),
    )
    applicant_headers = _login(client, "release-user", "password123")
    denied = client.post(f"/api/v1/sql-releases/{release_id}/execute", headers=applicant_headers)
    assert denied.status_code == 403

    g.pop("current_user", None)
    executor_headers = _login(client, "release-executor", "password123")
    history = client.get("/api/v1/sql-releases", headers=executor_headers)
    assert history.status_code == 200
    assert [item["id"] for item in history.get_json()["data"]["items"]] == [release_id]
    assert history.get_json()["data"]["items"][0]["can_execute"] is True
    unauthorized_detail = client.get(
        f"/api/v1/sql-releases/{unauthorized_release_id}",
        headers=executor_headers,
    )
    assert unauthorized_detail.status_code == 403
    executed = client.post(f"/api/v1/sql-releases/{release_id}/execute", headers=executor_headers)
    assert executed.status_code == 200

    g.pop("current_user", None)
    admin_headers = _login(client, "admin", "admin123")
    admin_history = client.get("/api/v1/sql-releases", headers=admin_headers)
    assert admin_history.status_code == 200
    assert {item["id"] for item in admin_history.get_json()["data"]["items"]} == {
        release_id,
        unauthorized_release_id,
    }


def test_sql_release_history_supports_filters_and_title_search(app, client):
    with app.app_context():
        applicant = User(
            username="filter-applicant", display_name="筛选申请人",
            role="user", status="active", auth_source="local",
        )
        another_applicant = User(
            username="another-applicant", display_name="其他申请人",
            role="user", status="active", auth_source="local",
        )
        mysql_cluster = DatabaseCluster(
            name="filter-mysql", db_type="mysql", business_line="filter", environment="test",
        )
        mongo_cluster = DatabaseCluster(
            name="filter-mongo", db_type="mongodb", business_line="filter", environment="test",
        )
        db.session.add_all([applicant, another_applicant, mysql_cluster, mongo_cluster])
        db.session.flush()
        releases = [
            SqlRelease(
                title="核心订单发布", applicant_id=applicant.id, cluster_id=mysql_cluster.id,
                db_type="mysql", database_name="billing", sql_text="SELECT 1", status="success",
                ai_passed=True, review_json=[], created_at=datetime(2026, 8, 2, 10, 0, 0),
            ),
            SqlRelease(
                title="归档任务", applicant_id=another_applicant.id, cluster_id=mongo_cluster.id,
                db_type="mongodb", database_name="archive", sql_text="{}", status="pending",
                ai_passed=True, review_json=[], created_at=datetime(2026, 8, 5, 10, 0, 0),
            ),
            SqlRelease(
                title="核心历史失败", applicant_id=another_applicant.id, cluster_id=mysql_cluster.id,
                db_type="mysql", database_name="billing", sql_text="SELECT 2", status="failed",
                ai_passed=True, review_json=[], created_at=datetime(2026, 7, 1, 10, 0, 0),
            ),
        ]
        db.session.add_all(releases)
        db.session.commit()
        target_id, mongo_id, failed_id = [item.id for item in releases]

    headers = _login(client, "admin", "admin123")

    def ids_for(**params):
        response = client.get("/api/v1/sql-releases", headers=headers, query_string=params)
        assert response.status_code == 200
        return [item["id"] for item in response.get_json()["data"]["items"]]

    assert ids_for(db_type="mongodb") == [mongo_id]
    assert ids_for(applicant="筛选申请") == [target_id]
    assert ids_for(status="failed") == [failed_id]
    assert ids_for(start_time="2026-08-01 00:00:00", end_time="2026-08-31 23:59:59") == [mongo_id, target_id]
    assert ids_for(title_keyword="核心") == [failed_id, target_id]
    assert ids_for(
        db_type="mysql", applicant="filter-applicant", status="success",
        start_time="2026-08-02 10:00:00", end_time="2026-08-02 10:00:00",
        title_keyword="订单",
    ) == [target_id]

    invalid_range = client.get(
        "/api/v1/sql-releases", headers=headers,
        query_string={"start_time": "2026-08-03", "end_time": "2026-08-02"},
    )
    assert invalid_range.status_code == 400


def test_partial_rollback_generation_failure_prevents_execution(app, client, monkeypatch):
    user_id, cluster_id, instance_id = _assets(app)
    with app.app_context():
        release = SqlRelease(
            title="update order", applicant_id=user_id, cluster_id=cluster_id, instance_id=instance_id,
            database_name="billing", sql_text="UPDATE orders SET status='paid' WHERE id=1;",
            status="pending", ai_passed=True, force_submitted=False, review_json=[],
        )
        db.session.add(release)
        db.session.commit()
        release_id = release.id
    import app.api.routes.sql_releases as routes
    called = []
    def fail_before_execute(*args, **kwargs):
        called.append("partial-backup")
        raise RuntimeError("partial rollback generation failed")
    monkeypatch.setattr(routes, "execute_mysql_with_partial_rollback", fail_before_execute)
    response = client.post(f"/api/v1/sql-releases/{release_id}/execute", headers=_login(client, "admin", "admin123"))
    assert response.status_code == 500
    assert called == ["partial-backup"]
    with app.app_context():
        assert SqlRelease.query.get(release_id).status == "failed"


def test_new_mysql_foreign_keys_match_production_bigint_ids():
    release_ddl = str(CreateTable(SqlRelease.__table__).compile(dialect=mysql.dialect()))
    rollback_backup_ddl = str(CreateTable(SqlReleaseRollbackBackup.__table__).compile(dialect=mysql.dialect()))
    group_cluster_ddl = str(CreateTable(DataSourceGroupClusterPermission.__table__).compile(dialect=mysql.dialect()))
    user_group_ddl = str(CreateTable(UserDataSourceGroup.__table__).compile(dialect=mysql.dialect()))

    assert "applicant_id BIGINT NOT NULL" in release_ddl
    assert "cluster_id BIGINT NOT NULL" in release_ddl
    assert "instance_id BIGINT" in release_ddl
    assert "executed_by BIGINT" in release_ddl
    assert "cluster_id BIGINT NOT NULL" in group_cluster_ddl
    assert "user_id BIGINT NOT NULL" in user_group_ddl
    assert "db_type VARCHAR(32) NOT NULL" in release_ddl
    assert "release_id INTEGER NOT NULL" in rollback_backup_ddl
    assert (
        SqlRelease.__table__.c.id.type.compile(dialect=mysql.dialect())
        == SqlReleaseRollbackBackup.__table__.c.release_id.type.compile(dialect=mysql.dialect())
    )
    assert "rows_encrypted LONGTEXT NOT NULL" in rollback_backup_ddl
    assert "rollback_sql_encrypted LONGTEXT NOT NULL" in rollback_backup_ddl


class _FakeRollbackCursor:
    def __init__(self, connection, existing_rows, backup_dir, fail_dml=False):
        self.connection = connection
        self.existing_rows = existing_rows
        self.backup_dir = backup_dir
        self.mode = None
        self.rowcount = 0
        self.fail_dml = fail_dml

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql):
        self.connection.executed.append(sql)
        normalized = sql.strip().upper()
        if normalized.startswith("SHOW KEYS"):
            self.mode = "keys"
        elif normalized.startswith("SELECT *"):
            self.mode = "select"
        else:
            rollback_files = list(self.backup_dir.glob("*_rollback.sql"))
            assert rollback_files, "DML executed before rollback SQL file was written"
            if self.fail_dml:
                raise RuntimeError("database execution failed")
            self.mode = "execute"
            self.rowcount = 1

    def fetchall(self):
        return [{"Column_name": "id"}] if self.mode == "keys" else []

    def fetchmany(self, _size):
        return list(self.existing_rows) if self.mode == "select" else []


class _FakeRollbackConnection:
    def __init__(self, existing_rows, backup_dir, fail_dml=False):
        self.executed = []
        self.committed = False
        self.rolled_back = False
        self._cursor = _FakeRollbackCursor(self, existing_rows, backup_dir, fail_dml=fail_dml)

    def cursor(self):
        return self._cursor

    def escape(self, value):
        if value is None:
            return "NULL"
        if isinstance(value, (int, float)):
            return str(value)
        return "'" + str(value).replace("'", "\\'") + "'"

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


@pytest.mark.parametrize(
    ("statement", "existing_rows", "expected_sql"),
    [
        ("UPDATE orders SET status='paid' WHERE id=1", [{"id": 1, "status": "pending"}], "ON DUPLICATE KEY UPDATE"),
        ("DELETE FROM orders WHERE id=1", [{"id": 1, "status": "pending"}], "ON DUPLICATE KEY UPDATE"),
        ("INSERT INTO orders (id,status) VALUES (2,'new')", [], "DELETE FROM `billing`.`orders`"),
        ("REPLACE INTO orders (id,status) VALUES (1,'new')", [{"id": 1, "status": "pending"}], "DELETE FROM `billing`.`orders`"),
    ],
)
def test_partial_rollback_sql_is_written_before_each_dml(app, monkeypatch, tmp_path, statement, existing_rows, expected_sql):
    import pymysql

    connection = _FakeRollbackConnection(existing_rows, tmp_path)
    monkeypatch.setattr(pymysql, "connect", lambda **_kwargs: connection)
    instance = SimpleNamespace(resolved_ip=None, host_input="127.0.0.1", port=3306, username="root", password_encrypted=None)
    with app.app_context():
        app.config["SQL_RELEASE_BACKUP_DIR"] = str(tmp_path)
        result, rollback_path = execute_mysql_with_partial_rollback(instance, "billing", [statement], 99)

    assert connection.committed is True
    assert result["statements"][0]["backup_rows"] == (len(existing_rows) if existing_rows else 1)
    content = open(rollback_path, encoding="utf-8").read()
    assert expected_sql in content
    assert "START TRANSACTION;" in content


class _FakeImmediateMysqlCursor(_FakeRollbackCursor):
    def __init__(self, connection, backup_dir):
        super().__init__(connection, [], backup_dir)
        self.columns = ["id", "name"]

    def execute(self, sql):
        self.connection.executed.append(sql)
        normalized = sql.strip().upper()
        if normalized.startswith("SHOW KEYS"):
            self.mode = "keys"
            return
        if normalized.startswith("SHOW COLUMNS"):
            self.mode = "columns"
            return
        if normalized.startswith("SELECT *"):
            self.mode = "select"
            return
        assert list(self.backup_dir.glob("*_rollback.sql")), "SQL executed before its rollback content was written"
        match = re.match(
            r"^\s*ALTER\s+TABLE\s+\S+\s+ADD\s+(?:COLUMN\s+)?(?:`([^`]+)`|([A-Za-z_][A-Za-z0-9_$]*))",
            sql,
            flags=re.I,
        )
        if match:
            self.columns.append(match.group(1) or match.group(2))
        self.mode = "execute"
        self.rowcount = 1

    def fetchall(self):
        if self.mode == "keys":
            return [{"Column_name": "id"}]
        if self.mode == "columns":
            return [{"Field": item} for item in self.columns]
        return []


class _FakeImmediateMysqlConnection(_FakeRollbackConnection):
    def __init__(self, backup_dir):
        super().__init__([], backup_dir)
        self._cursor = _FakeImmediateMysqlCursor(self, backup_dir)


def test_mysql_rollback_uses_immediate_columns_after_add_column(app, monkeypatch, tmp_path):
    import pymysql

    connection = _FakeImmediateMysqlConnection(tmp_path)
    monkeypatch.setattr(pymysql, "connect", lambda **_kwargs: connection)
    instance = SimpleNamespace(
        resolved_ip=None, host_input="127.0.0.1", port=3306,
        username="root", password_encrypted=None,
    )
    statements = [
        "ALTER TABLE test ADD COLUMN tta varchar(20)",
        "ALTER TABLE test ADD COLUMN ttb varchar(20)",
        "INSERT INTO test VALUES (10,'a','b','c')",
    ]
    with app.app_context():
        app.config["SQL_RELEASE_BACKUP_DIR"] = str(tmp_path)
        result, rollback_path = execute_mysql_with_partial_rollback(
            instance, "app", statements, 104
        )

    rollback_sql = open(rollback_path, encoding="utf-8").read()
    assert connection.committed is True
    assert [item["line"] for item in result["statements"]] == [1, 2, 3]
    assert connection._cursor.columns == ["id", "name", "tta", "ttb"]
    assert "-- rollback for statement #3" in rollback_sql
    assert "DELETE FROM `app`.`test` WHERE (`id` <=> 10);" in rollback_sql
    assert "ALTER TABLE `app`.`test` DROP COLUMN `ttb`;" in rollback_sql
    assert "ALTER TABLE `app`.`test` DROP COLUMN `tta`;" in rollback_sql


def test_unsafe_dml_shapes_are_rejected_before_execution():
    with pytest.raises(ValueError, match="缺少 WHERE"):
        _analyze_dml("UPDATE orders SET status='paid'", "billing")
    with pytest.raises(ValueError, match="TRUNCATE"):
        _analyze_dml("TRUNCATE TABLE orders", "billing")
    with pytest.raises(ValueError, match="WITH DML"):
        _analyze_dml("WITH ids AS (SELECT 1) DELETE FROM orders WHERE id IN (SELECT * FROM ids)", "billing")


def test_execution_failure_keeps_generated_rollback_file(app, monkeypatch, tmp_path):
    import pymysql

    connection = _FakeRollbackConnection([{"id": 1, "status": "pending"}], tmp_path, fail_dml=True)
    monkeypatch.setattr(pymysql, "connect", lambda **_kwargs: connection)
    instance = SimpleNamespace(resolved_ip=None, host_input="127.0.0.1", port=3306, username="root", password_encrypted=None)
    with app.app_context():
        app.config["SQL_RELEASE_BACKUP_DIR"] = str(tmp_path)
        with pytest.raises(PartialRollbackExecutionError) as caught:
            execute_mysql_with_partial_rollback(
                instance,
                "billing",
                ["UPDATE orders SET status='paid' WHERE id=1"],
                100,
            )

    assert connection.rolled_back is True
    assert caught.value.rollback_path
    assert "ON DUPLICATE KEY UPDATE" in open(caught.value.rollback_path, encoding="utf-8").read()


class _FakeNoPrimaryKeyRollbackCursor(_FakeRollbackCursor):
    def fetchall(self):
        if self.mode == "keys":
            return []
        if self.mode == "select":
            return list(self.existing_rows)
        return super().fetchall()


class _FakeNoPrimaryKeyRollbackConnection(_FakeRollbackConnection):
    def __init__(self, existing_rows, backup_dir):
        super().__init__(existing_rows, backup_dir)
        self._cursor = _FakeNoPrimaryKeyRollbackCursor(self, existing_rows, backup_dir)


def test_mysql_without_primary_key_backs_up_rows_in_database(app, monkeypatch, tmp_path):
    import json
    import pymysql

    user_id, cluster_id, instance_id = _assets(app)
    with app.app_context():
        release = SqlRelease(
            title="no primary key", applicant_id=user_id, cluster_id=cluster_id,
            instance_id=instance_id, db_type="mysql", database_name="billing",
            sql_text="UPDATE orders SET status='paid' WHERE account='A';",
            status="pending", ai_passed=True, review_json=[],
        )
        db.session.add(release)
        db.session.commit()
        release_id = release.id

        connection = _FakeNoPrimaryKeyRollbackConnection(
            [{"account": "A", "status": "pending"}], tmp_path
        )
        monkeypatch.setattr(pymysql, "connect", lambda **_kwargs: connection)
        app.config["SQL_RELEASE_BACKUP_DIR"] = str(tmp_path)
        instance = SimpleNamespace(
            resolved_ip=None, host_input="127.0.0.1", port=3306,
            username="root", password_encrypted=None,
        )
        result, rollback_path = execute_mysql_with_partial_rollback(
            instance, "billing",
            ["UPDATE orders SET status='paid' WHERE account='A'"],
            release_id,
        )
        backup = SqlReleaseRollbackBackup.query.filter_by(
            release_id=release_id, statement_line=1
        ).one()
        stored_rows = json.loads(decrypt_secret(backup.rows_encrypted))

    rollback_sql = open(rollback_path, encoding="utf-8").read()
    assert result["statements"][0]["backup_rows"] == 1
    assert backup.row_count == 1
    assert stored_rows == [{"account": "A", "status": "pending"}]
    assert "pending" not in backup.rows_encrypted
    assert "DELETE FROM `billing`.`orders` WHERE (`account` <=> 'A') LIMIT 1;" in rollback_sql
    assert "INSERT INTO `billing`.`orders` (`account`, `status`) VALUES ('A', 'pending');" in rollback_sql
    assert "ON DUPLICATE KEY UPDATE" not in rollback_sql


class _FakePostgresqlCursor:
    def __init__(self, backup_dir):
        self.backup_dir = backup_dir
        self.mode = None
        self.rowcount = 1
        self.columns = ["id", "name"]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, _params=None):
        normalized = str(sql).strip().upper()
        if normalized.startswith("SELECT A.ATTNAME") and "FROM PG_INDEX" in normalized:
            self.mode = "keys"
        elif normalized.startswith("SELECT A.ATTNAME") and "FROM PG_CLASS" in normalized:
            self.mode = "columns"
        elif normalized.startswith("SELECT *"):
            self.mode = "select"
        else:
            assert list(self.backup_dir.glob("*_postgresql_rollback.sql"))
            self.mode = "execute"

    def fetchall(self):
        if self.mode == "keys":
            return [{"attname": "id"}]
        if self.mode == "columns":
            return [{"attname": item} for item in self.columns]
        return []

    def fetchmany(self, _size):
        return [{"id": 1, "status": "new"}] if self.mode == "select" else []

    def mogrify(self, _sql, values):
        return ("(" + ",".join(str(value) if isinstance(value, int) else "'" + str(value) + "'" for value in values) + ")").encode()


class _FakePostgresqlConnection:
    def __init__(self, backup_dir):
        self.cursor_instance = _FakePostgresqlCursor(backup_dir)
        self.committed = False

    def cursor(self, **_kwargs):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        pass


class _FakePostgresqlReleaseCursor(_FakePostgresqlCursor):
    def __init__(self, backup_dir):
        super().__init__(backup_dir)
        self.select_count = 0

    def execute(self, sql, _params=None):
        super().execute(sql, _params)
        match = re.match(
            r'^\s*ALTER\s+TABLE\s+\S+\s+ADD\s+(?:COLUMN\s+)?(?:"([^"]+)"|([A-Za-z_][A-Za-z0-9_$]*))',
            str(sql),
            flags=re.I,
        )
        if match:
            self.columns.append(match.group(1) or match.group(2))

    def fetchmany(self, _size):
        if self.mode != "select":
            return []
        self.select_count += 1
        if self.select_count <= 2:
            return []
        return [{"id": 11, "name": "d", "tta": "e", "ttb": "f"}]


class _FakePostgresqlReleaseConnection(_FakePostgresqlConnection):
    def __init__(self, backup_dir):
        self.cursor_instance = _FakePostgresqlReleaseCursor(backup_dir)
        self.committed = False


class _FakePostgresqlNoPrimaryKeyCursor(_FakePostgresqlCursor):
    def fetchall(self):
        if self.mode == "keys":
            return []
        if self.mode == "select":
            return [{"id": 1, "status": "new"}]
        return super().fetchall()


class _FakePostgresqlNoPrimaryKeyConnection(_FakePostgresqlConnection):
    def __init__(self, backup_dir):
        self.cursor_instance = _FakePostgresqlNoPrimaryKeyCursor(backup_dir)
        self.committed = False


def test_postgresql_rollback_is_written_before_update(app, monkeypatch, tmp_path):
    import psycopg2

    connection = _FakePostgresqlConnection(tmp_path)
    monkeypatch.setattr(psycopg2, "connect", lambda **_kwargs: connection)
    instance = SimpleNamespace(resolved_ip=None, host_input="127.0.0.1", port=5432, username="postgres", password_encrypted=None, extra_json={})
    with app.app_context():
        app.config["SQL_RELEASE_BACKUP_DIR"] = str(tmp_path)
        result, rollback_path = execute_postgresql_with_partial_rollback(
            instance, "billing", ["UPDATE public.orders SET status='paid' WHERE id=1"], 101
        )
    assert connection.committed is True
    assert result["statements"][0]["backup_rows"] == 1
    assert "ON CONFLICT" in open(rollback_path, encoding="utf-8").read()


def test_postgresql_without_primary_key_uses_backed_up_row_values(app, monkeypatch, tmp_path):
    import psycopg2

    connection = _FakePostgresqlNoPrimaryKeyConnection(tmp_path)
    monkeypatch.setattr(psycopg2, "connect", lambda **_kwargs: connection)
    instance = SimpleNamespace(
        resolved_ip=None, host_input="127.0.0.1", port=5432,
        username="postgres", password_encrypted=None, extra_json={},
    )
    with app.app_context():
        app.config["SQL_RELEASE_BACKUP_DIR"] = str(tmp_path)
        result, rollback_path = execute_postgresql_with_partial_rollback(
            instance, "billing",
            ["UPDATE public.orders SET status='paid' WHERE id=1"], 105,
        )

    rollback_sql = open(rollback_path, encoding="utf-8").read()
    assert result["statements"][0]["backup_rows"] == 1
    assert "WHERE ctid IN" in rollback_sql
    assert 'INSERT INTO "public"."orders" ("id", "status")' in rollback_sql
    assert "ON CONFLICT" not in rollback_sql


def test_postgresql_rollback_supports_implicit_insert_columns_after_add_column(app, monkeypatch, tmp_path):
    import psycopg2

    parsed = _analyze_postgresql_dml("INSERT INTO public.test VALUES (10,'a','b','c')")
    assert parsed["columns"] is None
    connection = _FakePostgresqlReleaseConnection(tmp_path)
    monkeypatch.setattr(psycopg2, "connect", lambda **_kwargs: connection)
    instance = SimpleNamespace(
        resolved_ip=None, host_input="127.0.0.1", port=5432,
        username="postgres", password_encrypted=None, extra_json={},
    )
    statements = [
        "ALTER TABLE public.test ADD COLUMN tta varchar(20)",
        "ALTER TABLE public.test ADD COLUMN ttb varchar(20)",
        "INSERT INTO public.test VALUES (10,'a','b','c')",
        "INSERT INTO public.test VALUES (11,'d','e','f')",
        "DELETE FROM public.test WHERE id=11",
    ]
    with app.app_context():
        app.config["SQL_RELEASE_BACKUP_DIR"] = str(tmp_path)
        result, rollback_path = execute_postgresql_with_partial_rollback(
            instance, "app", statements, 103
        )

    rollback_sql = open(rollback_path, encoding="utf-8").read()
    assert connection.committed is True
    assert result["statement_count"] == 5
    assert [item["line"] for item in result["statements"]] == [1, 2, 3, 4, 5]
    assert "-- rollback for statement #5" in rollback_sql
    assert 'DELETE FROM "public"."test" WHERE ("id" IS NOT DISTINCT FROM 10);' in rollback_sql
    assert 'ALTER TABLE "public"."test" DROP COLUMN "ttb";' in rollback_sql
    assert 'ALTER TABLE "public"."test" DROP COLUMN "tta";' in rollback_sql


def test_failed_postgresql_release_cannot_repeat_successful_statements(app, client, monkeypatch):
    with app.app_context():
        admin = User.query.filter_by(username="admin").one()
        cluster = DatabaseCluster(
            name="postgresql-retry", db_type="postgresql",
            business_line="billing", environment="test",
        )
        db.session.add(cluster)
        db.session.flush()
        instance = DatabaseInstance(
            name="postgresql-retry-primary", db_type="postgresql",
            host_input="127.0.0.1", port=5432, username="postgres",
            cluster_id=cluster.id,
        )
        db.session.add(instance)
        db.session.flush()
        release = SqlRelease(
            title="retry postgres release", applicant_id=admin.id,
            cluster_id=cluster.id, instance_id=instance.id,
            db_type="postgresql", database_name="app",
            sql_text="INSERT INTO public.test VALUES (10,'a');",
            status="failed", ai_passed=True, force_submitted=False,
            ai_summary="通过", review_json=[], rollback_backup_path=None,
            execution_result_json={"error": "rollback generation failed"},
        )
        db.session.add(release)
        db.session.commit()
        release_id = release.id

    response = client.post(
        f"/api/v1/sql-releases/{release_id}/execute",
        headers=_login(client, "admin", "admin123"),
    )
    assert response.status_code == 409


class _FakeMongoCursor:
    def __init__(self, rows):
        self.rows = rows

    def limit(self, size):
        return iter(self.rows[:size])


class _FakeMongoCollection:
    def __init__(self, backup_dir):
        self.backup_dir = backup_dir

    def find(self, _filter):
        raise AssertionError("MongoDB execution must not read old documents for backup")

    def update_one(self, *_args, **_kwargs):
        assert not list(self.backup_dir.glob("*_mongodb_rollback.js"))
        return SimpleNamespace(modified_count=1, raw_result={"nModified": 1})


class _FakeMongoDatabase:
    def __init__(self, backup_dir):
        self.backup_dir = backup_dir

    def get_collection(self, _name):
        return _FakeMongoCollection(self.backup_dir)


class _FakeMongoClient:
    def __init__(self, backup_dir):
        self.backup_dir = backup_dir

    def get_database(self, _name):
        return _FakeMongoDatabase(self.backup_dir)

    def close(self):
        pass


def test_mongodb_executes_without_backup(app, monkeypatch, tmp_path):
    import pymongo

    monkeypatch.setattr(pymongo, "MongoClient", lambda *_args, **_kwargs: _FakeMongoClient(tmp_path))
    instance = SimpleNamespace(resolved_ip=None, host_input="127.0.0.1", port=27017, username="root", password_encrypted=None)
    statement = 'db.orders.updateOne({_id: 1}, {$set: {status: "paid"}})'
    assert validate_mongo_release_statement(statement) == (True, None)
    with app.app_context():
        app.config["SQL_RELEASE_BACKUP_DIR"] = str(tmp_path)
        result, rollback_path = execute_mongodb_with_partial_rollback(instance, "billing", [statement], 102)
    assert result["affected_rows"] == 1
    assert result["statements"][0]["line"] == 1
    assert result["statements"][0]["backup_rows"] == 0
    assert rollback_path is None
    assert not list(tmp_path.glob("*_mongodb_rollback.js"))


def test_postgresql_unsafe_dml_is_rejected():
    with pytest.raises(ValueError, match="缺少 WHERE"):
        _analyze_postgresql_dml("UPDATE public.orders SET status='paid'")
    with pytest.raises(ValueError, match="单列 ALTER TABLE"):
        _analyze_postgresql_dml("ALTER TABLE public.orders ADD COLUMN IF NOT EXISTS note text")


@pytest.mark.parametrize(
    ("db_type", "statement", "executor_name"),
    [
        ("mongodb", 'db.orders.updateOne({_id: 1}, {$set: {status: "paid"}})', "execute_mongodb_with_partial_rollback"),
        ("postgresql", "UPDATE public.orders SET status='paid' WHERE id=1", "execute_postgresql_with_partial_rollback"),
    ],
)
def test_release_submit_and_execute_dispatches_by_database_type(app, client, monkeypatch, db_type, statement, executor_name):
    with app.app_context():
        user = User(username=f"release-{db_type}", role="user", status="active", auth_source="local")
        user.set_password("password123")
        cluster = DatabaseCluster(name=f"{db_type}-release", db_type=db_type, business_line="billing", environment="test")
        db.session.add_all([user, cluster])
        db.session.flush()
        instance = DatabaseInstance(
            name=f"{db_type}-primary", db_type=db_type, host_input="127.0.0.1",
            port=27017 if db_type == "mongodb" else 5432, username="root", cluster_id=cluster.id,
        )
        db.session.add(instance)
        db.session.flush()
        db.session.add_all([
            UserMenuPermission(user_id=user.id, menu_key="sql_release_apply"),
            UserMenuPermission(user_id=user.id, menu_key="sql_release_history"),
            UserClusterPermission(user_id=user.id, cluster_id=cluster.id, can_change=True),
        ])
        db.session.commit()
        user_id, cluster_id, instance_id = user.id, cluster.id, instance.id

    import app.api.routes.sql_releases as routes
    monkeypatch.setattr(routes, "pick_instance", lambda *args, **kwargs: DatabaseInstance.query.get(instance_id))
    if db_type == "mongodb":
        monkeypatch.setattr(routes, "list_mongo_databases", lambda *_args, **_kwargs: ["billing"])
        monkeypatch.setattr(routes, "list_mongo_collections", lambda *_args, **_kwargs: {
            "database": "billing", "collections": [{"name": "orders"}], "views": [],
        })
        monkeypatch.setattr(routes, "describe_mongo_collection", lambda *_args, **_kwargs: {
            "sample_fields": [{"name": "_id", "type": "int"}], "indexes": [],
        })
    else:
        monkeypatch.setattr(routes, "list_postgresql_databases", lambda *_args: ["billing"])
        monkeypatch.setattr(routes, "list_postgresql_objects", lambda *_args: {
            "database": "billing", "tables": [{"name": "public.orders"}], "views": [],
            "procedures": [], "functions": [], "triggers": [], "events": [],
        })
        monkeypatch.setattr(routes, "list_postgresql_table_columns", lambda *_args: [{
            "name": "id", "data_type": "bigint", "column_key": "PRI",
        }])
    monkeypatch.setattr(routes, "dispatch_sql_release_review", lambda *_args: None)
    import app.services.sql_release_review as review_worker
    monkeypatch.setattr(review_worker, "review_release", lambda *_args: ([{
        "line": 1, "sql": statement, "passed": True, "risk_level": "low", "reason": "ok", "suggestion": "",
    }], "通过"))
    called = []
    monkeypatch.setattr(routes, executor_name, lambda *_args, **_kwargs: (called.append(db_type) or {"affected_rows": 1}, None))
    payload = {
        "title": f"{db_type} release", "project": "billing", "environment": "test",
        "db_type": db_type, "cluster_id": cluster_id, "database": "billing", "sql": statement + ";",
    }
    user_headers = _login(client, f"release-{db_type}", "password123")
    databases_response = client.get(
        "/api/v1/sql-releases/databases", headers=user_headers,
        query_string={"cluster_id": cluster_id, "db_type": db_type},
    )
    assert databases_response.status_code == 200
    assert databases_response.get_json()["data"]["databases"] == ["billing"]
    objects_response = client.get(
        "/api/v1/sql-releases/objects", headers=user_headers,
        query_string={"cluster_id": cluster_id, "db_type": db_type, "database": "billing"},
    )
    assert objects_response.status_code == 200
    columns_response = client.get(
        "/api/v1/sql-releases/columns", headers=user_headers,
        query_string={"cluster_id": cluster_id, "db_type": db_type, "database": "billing", "table": "orders" if db_type == "mongodb" else "public.orders"},
    )
    assert columns_response.status_code == 200
    assert columns_response.get_json()["data"]["columns"][0]["name"] in {"_id", "id"}
    submitted = client.post("/api/v1/sql-releases", headers=user_headers, json=payload)
    assert submitted.status_code == 201
    assert submitted.get_json()["data"]["db_type"] == db_type
    assert submitted.get_json()["data"]["status"] == "reviewing"
    release_id = submitted.get_json()["data"]["id"]
    run_sql_release_review(app, release_id)
    with app.app_context():
        assert SqlRelease.query.get(release_id).status == "pending"
    admin_login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert admin_login.status_code == 200
    assert admin_login.get_json()["data"]["user"]["role"] == "admin"
    admin_headers = {"Authorization": f"Bearer {admin_login.get_json()['data']['access_token']}"}
    g.pop("current_user", None)
    executed = client.post(f"/api/v1/sql-releases/{release_id}/execute", headers=admin_headers)
    assert executed.status_code == 200, executed.get_json()
    assert called == [db_type]
    with app.app_context():
        assert SqlRelease.query.get(release_id).applicant_id == user_id


def test_release_can_partially_rollback_selected_successful_statement(app, client, monkeypatch):
    with app.app_context():
        admin = User.query.filter_by(username="admin").one()
        cluster = DatabaseCluster(
            name="mysql-partial-rollback", db_type="mysql",
            business_line="billing", environment="test",
        )
        db.session.add(cluster)
        db.session.flush()
        instance = DatabaseInstance(
            name="mysql-partial-rollback-primary", db_type="mysql",
            host_input="127.0.0.1", port=3306, username="root",
            cluster_id=cluster.id,
        )
        db.session.add(instance)
        db.session.flush()
        release = SqlRelease(
            title="partial rollback", applicant_id=admin.id,
            cluster_id=cluster.id, instance_id=instance.id,
            db_type="mysql", database_name="billing",
            sql_text="UPDATE orders SET status='paid' WHERE id=1;\nDELETE FROM logs WHERE id=2;",
            status="success", ai_passed=True, review_json=[],
            execution_result_json={"statements": [
                {"line": 1, "sql": "UPDATE orders SET status='paid' WHERE id=1", "status": "success"},
                {"line": 2, "sql": "DELETE FROM logs WHERE id=2", "status": "success"},
            ]},
        )
        db.session.add(release)
        db.session.flush()
        for line, table, rollback_sql in [
            (1, "orders", "UPDATE orders SET status='pending' WHERE id=1;"),
            (2, "logs", "INSERT INTO logs (id) VALUES (2);"),
        ]:
            db.session.add(SqlReleaseRollbackBackup(
                release_id=release.id, statement_line=line, db_type="mysql",
                database_name="billing", table_name=table, operation="update",
                row_count=1, rows_encrypted=encrypt_secret("[]"),
                rollback_sql_encrypted=encrypt_secret(rollback_sql),
            ))
        db.session.commit()
        release_id = release.id

    captured = {}

    def fake_rollback(_instance, _database, items, _db_type, target_release_id):
        captured["lines"] = [item["line"] for item in items]
        captured["sql"] = [item["rollback_sql"] for item in items]
        row = db.session.get(SqlRelease, target_release_id)
        payload = dict(row.execution_result_json)
        statements = [dict(item) for item in payload["statements"]]
        for item in statements:
            if item["line"] in captured["lines"]:
                item["status"] = "rolled_back"
        payload["statements"] = statements
        row.execution_result_json = payload
        db.session.commit()
        return {"rolled_back_count": len(items), "statements": []}

    monkeypatch.setattr("app.api.routes.sql_releases.execute_release_rollback", fake_rollback)
    response = client.post(
        f"/api/v1/sql-releases/{release_id}/rollback",
        headers=_login(client, "admin", "admin123"),
        json={"lines": [1]},
    )
    assert response.status_code == 200
    data = response.get_json()["data"]["release"]
    assert captured["lines"] == [1]
    assert captured["sql"] == ["UPDATE orders SET status='pending' WHERE id=1;"]
    assert data["status"] == "partial_rolled_back"
    assert [item["status"] for item in data["statement_executions"]] == ["rolled_back", "success"]
    assert data["can_rollback"] is True
