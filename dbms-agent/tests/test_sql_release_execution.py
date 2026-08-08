import pytest
import werkzeug

if not hasattr(werkzeug, "__version__"):
    werkzeug.__version__ = "3"

from app import create_app


class TestConfig:
    TESTING = True
    AGENT_API_KEY = "agent-secret"
    AGENT_DEBUG = False
    AGENT_RECOVERY_ENABLED = False


@pytest.fixture()
def client():
    return create_app(TestConfig).test_client()


def test_sql_release_endpoint_requires_agent_key(client):
    response = client.post("/api/agent/sql-releases/execute", json={})
    assert response.status_code == 401


def test_sql_release_endpoint_dispatches_database_user(client, monkeypatch):
    captured = {}

    def fake_execute(instance, database, statements, db_type, timeout_seconds):
        captured.update(instance=instance, database=database, statements=statements, db_type=db_type)
        return {"affected_rows": 1, "statement_count": 1, "statements": [{
            "line": 1, "sql": statements[0], "status": "success", "affected_rows": 1,
        }]}

    monkeypatch.setattr("app.services.sql_release_executor.execute_sql_release", fake_execute)
    response = client.post(
        "/api/agent/sql-releases/execute",
        headers={"X-Agent-API-Key": "agent-secret"},
        json={
            "db_type": "mysql", "database": "billing", "statements": ["UPDATE orders SET status='paid' WHERE id=1"],
            "instance": {"host_input": "127.0.0.1", "port": 3306, "username": "dbms", "password": "secret"},
        },
    )
    assert response.status_code == 200
    assert captured["instance"]["username"] == "dbms"
    assert response.get_json()["data"]["execution_source"] == "agent"


def test_sql_release_endpoint_returns_partial_statement_results(client, monkeypatch):
    from app.services.sql_release_executor import SqlReleaseExecutionError

    def fail_after_first(*_args, **_kwargs):
        raise SqlReleaseExecutionError("second statement failed", {
            "affected_rows": 1,
            "statement_count": 2,
            "statements": [
                {"line": 1, "sql": "UPDATE first", "status": "success", "affected_rows": 1},
                {"line": 2, "sql": "UPDATE second", "status": "failed", "error": "boom"},
            ],
        })

    monkeypatch.setattr("app.services.sql_release_executor.execute_sql_release", fail_after_first)
    response = client.post(
        "/api/agent/sql-releases/execute",
        headers={"X-Agent-API-Key": "agent-secret"},
        json={
            "db_type": "mysql", "database": "billing", "statements": ["UPDATE first", "UPDATE second"],
            "instance": {"host_input": "127.0.0.1", "port": 3306, "username": "dbms", "password": "secret"},
        },
    )
    assert response.status_code == 502
    assert [item["status"] for item in response.get_json()["data"]["statements"]] == ["success", "failed"]
