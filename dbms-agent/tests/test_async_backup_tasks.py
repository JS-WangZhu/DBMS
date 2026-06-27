import threading

import pytest

from app import create_app
from app.api.routes import agent as agent_routes


class TestConfig:
    TESTING = True
    AGENT_API_KEY = ""


@pytest.fixture
def client():
    with agent_routes._backup_tasks_lock:
        agent_routes._backup_tasks.clear()
    app = create_app(TestConfig)
    yield app.test_client()
    with agent_routes._backup_tasks_lock:
        agent_routes._backup_tasks.clear()


def test_execute_returns_immediately_and_result_can_be_refreshed(client, monkeypatch):
    started = threading.Event()
    release = threading.Event()
    calls = []

    def fake_backup(_policy, _instance, _dry_run):
        calls.append(True)
        started.set()
        assert release.wait(timeout=2)
        return {
            "ok": True,
            "message": "backup completed",
            "output_file": "/backup/result.sql",
            "file_size": 42,
        }

    monkeypatch.setattr(agent_routes, "_run_backup", fake_backup)
    payload = {
        "task_id": "task-1",
        "policy": {"db_type": "mysql"},
        "instance": {"name": "mysql-1"},
    }

    response = client.post("/api/agent/execute", json=payload)
    assert response.status_code == 202
    assert response.get_json()["data"]["task_id"] == "task-1"
    assert started.wait(timeout=1)

    running = client.get("/api/agent/tasks/task-1").get_json()["data"]
    assert running["status"] == "running"

    duplicate = client.post("/api/agent/execute", json=payload)
    assert duplicate.status_code == 202
    assert len(calls) == 1

    release.set()
    for _ in range(100):
        task = client.get("/api/agent/tasks/task-1").get_json()["data"]
        if task["status"] == "success":
            break
        threading.Event().wait(0.01)

    assert task["status"] == "success"
    assert task["result"]["file_size"] == 42

    batch = client.post("/api/agent/tasks/status", json={"task_ids": ["task-1", "missing"]})
    data = batch.get_json()["data"]
    assert data["tasks"]["task-1"]["status"] == "success"
    assert data["missing"] == ["missing"]
