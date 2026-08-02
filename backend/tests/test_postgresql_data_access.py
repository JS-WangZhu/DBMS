from flask import g
from types import SimpleNamespace

from app.extensions import db
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.models.user import User
from app.models.user_permission import UserClusterPermission, UserMenuPermission
from app.services.data_access import execute_postgresql, validate_postgresql_query


def _login(client, username, password):
    response = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.get_json()['data']['access_token']}"}


def test_postgresql_data_query_change_and_metadata(app, client, monkeypatch):
    with app.app_context():
        user = User(username="pg-access-user", role="user", status="active", auth_source="local")
        user.set_password("password123")
        cluster = DatabaseCluster(name="pg-access", db_type="postgresql", business_line="billing", environment="test")
        db.session.add_all([user, cluster])
        db.session.flush()
        instance = DatabaseInstance(
            name="pg-primary", db_type="postgresql", host_input="127.0.0.1", port=5432,
            username="postgres", cluster_id=cluster.id,
        )
        db.session.add(instance)
        db.session.flush()
        db.session.add_all([
            UserMenuPermission(user_id=user.id, menu_key="data_query"),
            UserMenuPermission(user_id=user.id, menu_key="data_change"),
            UserClusterPermission(user_id=user.id, cluster_id=cluster.id, can_query=True, can_change=True),
        ])
        db.session.commit()
        cluster_id, instance_id = cluster.id, instance.id

    import app.api.routes.data_access as routes

    monkeypatch.setattr(routes, "pick_instance", lambda *_args, **_kwargs: DatabaseInstance.query.get(instance_id))
    monkeypatch.setattr(routes, "list_postgresql_databases", lambda *_args: ["billing"])
    monkeypatch.setattr(routes, "list_postgresql_objects", lambda *_args: {
        "database": "billing", "tables": [{"name": "public.orders"}], "views": [],
        "procedures": [], "functions": [], "triggers": [], "events": [],
    })
    monkeypatch.setattr(routes, "list_postgresql_table_columns", lambda *_args: [{
        "name": "id", "data_type": "bigint", "column_key": "PRI",
    }])
    executions = []

    def fake_execute(_instance, sql, _timeout, for_change, database=None, execution_id=None):
        executions.append({"sql": sql, "for_change": for_change, "database": database, "execution_id": execution_id})
        return {"columns": ["id"], "rows": [{"id": 1}], "affected_rows": 1}

    monkeypatch.setattr(routes, "execute_postgresql", fake_execute)
    headers = _login(client, "pg-access-user", "password123")
    databases = client.get(
        "/api/v1/data-access/postgresql/databases", headers=headers, query_string={"cluster_id": cluster_id},
    )
    assert databases.status_code == 200
    assert databases.get_json()["data"]["databases"] == ["billing"]
    objects = client.get(
        "/api/v1/data-access/postgresql/objects", headers=headers,
        query_string={"cluster_id": cluster_id, "database": "billing"},
    )
    assert objects.status_code == 200
    columns = client.get(
        "/api/v1/data-access/postgresql/columns", headers=headers,
        query_string={"cluster_id": cluster_id, "database": "billing", "table": "public.orders"},
    )
    assert columns.status_code == 200

    query = client.post("/api/v1/data-access/query", headers=headers, json={
        "db_type": "postgresql", "cluster_id": cluster_id, "business_line": "billing",
        "environment": "test", "database": "billing", "sql": "SELECT id FROM public.orders",
    })
    assert query.status_code == 200
    assert query.get_json()["data"]["result"]["rows"] == [{"id": 1}]
    change = client.post("/api/v1/data-access/change", headers=headers, json={
        "db_type": "postgresql", "cluster_id": cluster_id, "business_line": "billing",
        "environment": "test", "database": "billing", "sql": "UPDATE public.orders SET status='paid' WHERE id=1",
    })
    assert change.status_code == 200
    assert [item["for_change"] for item in executions] == [False, True]
    assert all(item["database"] == "billing" for item in executions)

    g.pop("current_user", None)


def test_postgresql_query_rejects_write_statements():
    assert validate_postgresql_query("SELECT 1") == (True, None)
    ok, reason = validate_postgresql_query("UPDATE public.orders SET status='paid'")
    assert ok is False
    assert "仅允许" in reason
    ok, reason = validate_postgresql_query("WITH changed AS (DELETE FROM orders RETURNING *) SELECT * FROM changed")
    assert ok is False
    assert "WITH DML" in reason


class _FakePgCursor:
    def __init__(self):
        self.description = None
        self.rowcount = 0
        self.sql = ""

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql):
        self.sql = sql
        if str(sql).strip().upper().startswith("SELECT"):
            self.description = [SimpleNamespace(name="id")]
            self.rowcount = 1
        else:
            self.description = None
            self.rowcount = 2

    def fetchmany(self, _size):
        return [{"id": 1}]


class _FakePgConnection:
    def __init__(self):
        self.autocommit = False
        self.committed = False
        self.rolled_back = False
        self.cursor_instance = _FakePgCursor()

    def cursor(self, **_kwargs):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def cancel(self):
        pass

    def close(self):
        pass


def test_execute_postgresql_returns_rows_and_commits_changes(monkeypatch):
    import psycopg2

    connections = []

    def connect(**_kwargs):
        connection = _FakePgConnection()
        connections.append(connection)
        return connection

    monkeypatch.setattr(psycopg2, "connect", connect)
    instance = SimpleNamespace(
        resolved_ip=None, host_input="127.0.0.1", port=5432, username="postgres",
        password_encrypted=None, extra_json={},
    )
    query_result = execute_postgresql(instance, "SELECT 1 AS id", 30, False, database="billing")
    assert query_result["columns"] == ["id"]
    assert query_result["rows"] == [{"id": 1}]
    assert connections[0].autocommit is True

    change_result = execute_postgresql(instance, "UPDATE orders SET status='paid' WHERE id IN (1,2)", 30, True, database="billing")
    assert change_result["affected_rows"] == 2
    assert connections[1].committed is True
