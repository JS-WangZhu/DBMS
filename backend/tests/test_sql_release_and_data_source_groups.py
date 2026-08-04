from app.extensions import db
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.models.sql_release import SqlRelease
from app.models.user import User
from app.models.user_permission import UserClusterPermission, UserMenuPermission
from app.models.user_permission import DataSourceGroupClusterPermission, UserDataSourceGroup
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable
from types import SimpleNamespace

import pytest
from flask import g

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
    group_cluster_ddl = str(CreateTable(DataSourceGroupClusterPermission.__table__).compile(dialect=mysql.dialect()))
    user_group_ddl = str(CreateTable(UserDataSourceGroup.__table__).compile(dialect=mysql.dialect()))

    assert "applicant_id BIGINT NOT NULL" in release_ddl
    assert "cluster_id BIGINT NOT NULL" in release_ddl
    assert "instance_id BIGINT" in release_ddl
    assert "executed_by BIGINT" in release_ddl
    assert "cluster_id BIGINT NOT NULL" in group_cluster_ddl
    assert "user_id BIGINT NOT NULL" in user_group_ddl
    assert "db_type VARCHAR(32) NOT NULL" in release_ddl


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


class _FakePostgresqlCursor:
    def __init__(self, backup_dir):
        self.backup_dir = backup_dir
        self.mode = None
        self.rowcount = 1

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, _params=None):
        normalized = str(sql).strip().upper()
        if normalized.startswith("SELECT A.ATTNAME"):
            self.mode = "keys"
        elif normalized.startswith("SELECT *"):
            self.mode = "select"
        else:
            assert list(self.backup_dir.glob("*_postgresql_rollback.sql"))
            self.mode = "execute"

    def fetchall(self):
        return [{"attname": "id"}] if self.mode == "keys" else []

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


class _FakeMongoCursor:
    def __init__(self, rows):
        self.rows = rows

    def limit(self, size):
        return iter(self.rows[:size])


class _FakeMongoCollection:
    def __init__(self, backup_dir):
        self.backup_dir = backup_dir

    def find(self, _filter):
        return _FakeMongoCursor([{"_id": 1, "status": "new"}])

    def update_one(self, *_args, **_kwargs):
        assert list(self.backup_dir.glob("*_mongodb_rollback.js"))
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


def test_mongodb_rollback_is_written_before_update(app, monkeypatch, tmp_path):
    import pymongo

    monkeypatch.setattr(pymongo, "MongoClient", lambda *_args, **_kwargs: _FakeMongoClient(tmp_path))
    instance = SimpleNamespace(resolved_ip=None, host_input="127.0.0.1", port=27017, username="root", password_encrypted=None)
    statement = 'db.orders.updateOne({_id: 1}, {$set: {status: "paid"}})'
    assert validate_mongo_release_statement(statement) == (True, None)
    with app.app_context():
        app.config["SQL_RELEASE_BACKUP_DIR"] = str(tmp_path)
        result, rollback_path = execute_mongodb_with_partial_rollback(instance, "billing", [statement], 102)
    assert result["affected_rows"] == 1
    assert "replaceOne" in open(rollback_path, encoding="utf-8").read()


def test_postgresql_unsafe_dml_is_rejected():
    with pytest.raises(ValueError, match="缺少 WHERE"):
        _analyze_postgresql_dml("UPDATE public.orders SET status='paid'")


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
