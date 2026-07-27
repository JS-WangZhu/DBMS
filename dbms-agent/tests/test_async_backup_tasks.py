import json
import threading

import pytest

from app import create_app
from app.api.routes import agent as agent_routes
from app.services.backup_task_worker import main as run_backup_worker


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

    def fake_backup(_policy, _instance, _dry_run, task_id=None):
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


class FakeProcess:
    def __init__(self):
        self.terminated = False
        self.returncode = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15


def test_task_process_registration_tracks_and_removes_processes():
    proc = FakeProcess()
    with agent_routes._backup_tasks_lock:
        agent_routes._backup_tasks["task-processes"] = {"processes": []}

    agent_routes._register_task_process("task-processes", proc)
    with agent_routes._backup_tasks_lock:
        assert agent_routes._backup_tasks["task-processes"]["processes"] == [proc]

    agent_routes._unregister_task_process("task-processes", proc)
    with agent_routes._backup_tasks_lock:
        assert agent_routes._backup_tasks["task-processes"]["processes"] == []


def test_retention_cleanup_removes_only_server_selected_files_under_storage_path(tmp_path):
    storage = tmp_path / "backups"
    storage.mkdir()
    expired = storage / "expired.sql.gz"
    expired.write_text("old", encoding="utf-8")
    outside = tmp_path / "must-keep.sql.gz"
    outside.write_text("keep", encoding="utf-8")

    deleted = agent_routes._cleanup_retention_files({
        "storage_path": str(storage),
        "retention": {"expired_file_paths": [str(expired), str(outside)]},
    })

    assert deleted == 1
    assert not expired.exists()
    assert outside.exists()


def test_cancel_terminates_all_registered_processes_and_hides_them_from_snapshot(client):
    first = FakeProcess()
    second = FakeProcess()
    with agent_routes._backup_tasks_lock:
        agent_routes._backup_tasks["cancel-task"] = {
            "task_id": "cancel-task",
            "status": "running",
            "processes": [first, second],
            "result": None,
        }

    response = client.post("/api/agent/tasks/cancel-task/cancel")

    assert response.status_code == 202
    assert first.terminated and second.terminated
    snapshot = response.get_json()["data"]
    assert snapshot["status"] == "cancelled"
    assert "processes" not in snapshot


def test_startup_recovery_fails_lost_dump_without_restarting(tmp_path, monkeypatch):
    app = create_app(TestConfig)
    app.config.update({
        "AGENT_RECOVERY_ENABLED": True,
        "DBMS_SERVER_URL": "http://server",
        "DBMS_AGENT_ID": "7",
        "AGENT_TASK_STATE_DIR": str(tmp_path),
        "AGENT_API_KEY": "secret",
    })
    task_id = "lost-dump-task"
    task_dir = tmp_path / task_id
    task_dir.mkdir()
    agent_routes._write_json_atomic(
        task_dir / "state.json",
        {
            "task_id": task_id,
            "status": "running",
            "phase": "dumping",
            "pid": 999999,
            "process_start_ticks": "1",
            "process_command_hash": "missing",
        },
    )

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": {"tasks": [{"task_id": task_id, "phase": "dumping"}]}}

    checkpoints = []
    monkeypatch.setattr(agent_routes.requests, "post", lambda *_args, **_kwargs: Response())
    monkeypatch.setattr(agent_routes, "_checkpoint_recovery_task", lambda _app, task: checkpoints.append(task) or True)

    agent_routes.recover_backup_tasks_on_startup(app)

    with agent_routes._backup_tasks_lock:
        recovered = dict(agent_routes._backup_tasks[task_id])
        agent_routes._backup_tasks.clear()
    assert recovered["status"] == "failed"
    assert recovered["result"]["message"] == "dump process lost after agent restart"
    assert checkpoints[-1]["status"] == "failed"


def test_recovery_execution_is_opt_in_and_keeps_existing_api(client, tmp_path, monkeypatch):
    client.application.config.update({
        "AGENT_RECOVERY_ENABLED": True,
        "DBMS_SERVER_URL": "http://server",
        "DBMS_AGENT_ID": "7",
        "AGENT_TASK_STATE_DIR": str(tmp_path),
    })
    started = []
    monkeypatch.setattr(
        agent_routes,
        "_start_recovery_worker",
        lambda _app, task_id, policy, instance: started.append((task_id, policy, instance)),
    )

    response = client.post(
        "/api/agent/execute",
        json={
            "task_id": "recoverable-task",
            "policy": {"db_type": "mysql"},
            "instance": {"name": "mysql-1"},
        },
    )

    assert response.status_code == 202
    assert response.get_json()["data"] == {
        "task_id": "recoverable-task",
        "status": "submitted",
        "recovery_managed": True,
    }
    assert started == [("recoverable-task", {"db_type": "mysql"}, {"name": "mysql-1"})]


def test_detached_worker_persists_terminal_result(tmp_path):
    task_dir = tmp_path / "worker-task"
    task_dir.mkdir()
    (task_dir / "input.json").write_text(
        json.dumps({"policy": {"db_type": "unsupported"}, "instance": {"name": "db-1"}}),
        encoding="utf-8",
    )

    assert run_backup_worker(str(task_dir)) == 1
    payload = json.loads((task_dir / "result.json").read_text(encoding="utf-8"))
    assert payload["task_id"] == "worker-task"
    assert payload["result"] == {"ok": False, "message": "unsupported db_type: unsupported"}
