from app.api.routes import agent as agent_routes


def test_build_partial_mongo_command_targets_one_database_and_excludes_collections(tmp_path):
    instance = {
        "resolved_ip": "10.0.0.8",
        "host_input": "mongo",
        "port": 27017,
        "username": "backup",
        "password": "secret",
    }
    output_file = str(tmp_path / "mongo.archive")

    command = agent_routes._build_partial_mongo_command(
        instance,
        output_file,
        True,
        "mongodump",
        "app",
        ["audit", "temporary_data"],
    )

    assert command[0] == "mongodump"
    assert f"--archive={output_file}" in command
    assert command.count("--db=app") == 1
    assert "--excludeCollection=audit" in command
    assert "--excludeCollection=temporary_data" in command
    assert "--gzip" in command
    assert all(isinstance(argument, str) for argument in command)


def test_mongodump_zstd_registers_both_processes_for_cancellation(monkeypatch, tmp_path):
    class Stream:
        def read(self):
            return b""
        def close(self):
            return None

    class Process:
        def __init__(self, name):
            self.stdout = Stream()
            self.stderr = Stream()
            self.returncode = 0
            self.name = name
        def poll(self):
            return self.returncode
        def terminate(self):
            self.returncode = -15
        def wait(self):
            return self.returncode
        def communicate(self):
            with agent_routes._backup_tasks_lock:
                observed.extend(agent_routes._backup_tasks["zstd-task"]["processes"])
            return b"", b""

    dump_process = Process("mongodump")
    compress_process = Process("zstd")
    pending = [dump_process, compress_process]
    observed = []
    monkeypatch.setattr(agent_routes.subprocess, "Popen", lambda *_args, **_kwargs: pending.pop(0))
    with agent_routes._backup_tasks_lock:
        agent_routes._backup_tasks["zstd-task"] = {"processes": []}

    agent_routes._run_mongodump_zstd(
        ["mongodump", "--archive=-"],
        str(tmp_path / "backup.zst"),
        task_id="zstd-task",
    )

    assert len(observed) == 2
    with agent_routes._backup_tasks_lock:
        assert agent_routes._backup_tasks["zstd-task"]["processes"] == []


def test_partial_mongo_dry_run_returns_one_command_without_database_discovery(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_routes, "_ensure_disk_space", lambda _path: True)
    policy = {
        "db_type": "mongodb",
        "tool_path": "mongodump",
        "storage_path": str(tmp_path),
        "compress_method": "gzip",
        "mongo_backup": {
            "mode": "partial",
            "database": "app",
            "excluded_collections": ["audit", "temporary_data"],
        },
    }
    instance = {"name": "mongo-1", "host_input": "mongo", "port": 27017}

    result = agent_routes._run_backup(policy, instance, True)

    assert result["ok"] is True
    assert result["command"].count("--db=app") == 1
    assert "--excludeCollection=audit" in result["command"]
    assert "--excludeCollection=temporary_data" in result["command"]
    assert all(isinstance(argument, str) for argument in result["command"])


def test_agent_backup_timeout_is_thirty_days():
    assert agent_routes.BACKUP_TIMEOUT_SECONDS == 2_592_000
