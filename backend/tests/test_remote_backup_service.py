from datetime import datetime, timedelta

from app.extensions import db
from app.models.backup import BackupLog, BackupPolicy
from app.models.backup_agent import BackupAgent
from app.models.db_asset import DatabaseInstance
from app.services.backup_agent_client import BackupAgentError
from app.services import remote_backup_service
from app.services.backup_agent_client import _build_payload_from_policy


def _policy():
    instance = DatabaseInstance(
        name="mysql-1",
        db_type="mysql",
        host_input="127.0.0.1",
        port=3306,
        username="root",
    )
    agent = BackupAgent(name="dc-agent", url="http://agent:5001", enabled=True)
    db.session.add_all([instance, agent])
    db.session.flush()
    policy = BackupPolicy(
        name="daily",
        target_type="instance",
        target_id=instance.id,
        db_type="mysql",
        backup_type="full",
        tool_name="mysqldump",
        cron_expr="0 0 * * *",
        storage_path="/backup",
        retain_days=7,
        compress=True,
        enabled=True,
        backup_agent_id=agent.id,
    )
    db.session.add(policy)
    db.session.commit()
    return policy


def test_submission_timeout_keeps_reconcilable_running_log(app, monkeypatch):
    with app.app_context():
        policy = _policy()

        def timeout(**_kwargs):
            raise BackupAgentError("Agent request timeout: response lost")

        monkeypatch.setattr(remote_backup_service, "execute_backup_on_agent", timeout)
        result, status_code = remote_backup_service.submit_remote_backup(policy)

        log = BackupLog.query.one()
        assert status_code == 202
        assert result["ok"] is True
        assert log.status == "running"
        assert log.extra_json["remote_task_id"]
        assert log.extra_json["remote_status"] == "submission_unknown"


def test_agent_payload_contains_only_expired_files_for_its_policy(app):
    with app.app_context():
        policy = _policy()
        old_remote = BackupLog(
            policy_id=policy.id,
            started_at=datetime.utcnow() - timedelta(days=9),
            finished_at=datetime.utcnow() - timedelta(days=8),
            status="success",
            file_path="/backup/expired.sql.gz",
            extra_json={"remote": True, "agent_id": policy.backup_agent_id},
        )
        recent_remote = BackupLog(
            policy_id=policy.id,
            started_at=datetime.utcnow() - timedelta(days=2),
            finished_at=datetime.utcnow() - timedelta(days=1),
            status="success",
            file_path="/backup/recent.sql.gz",
            extra_json={"remote": True, "agent_id": policy.backup_agent_id},
        )
        old_local = BackupLog(
            policy_id=policy.id,
            started_at=datetime.utcnow() - timedelta(days=9),
            finished_at=datetime.utcnow() - timedelta(days=8),
            status="success",
            file_path="/backup/local.sql.gz",
            extra_json={},
        )
        db.session.add_all([old_remote, recent_remote, old_local])
        db.session.commit()

        payload = _build_payload_from_policy(policy, DatabaseInstance.query.get(policy.target_id))

        assert payload["policy"]["retention"] == {
            "retain_days": 7,
            "expired_file_paths": ["/backup/expired.sql.gz"],
        }


def test_success_is_persisted_and_never_queried_again(app, monkeypatch):
    with app.app_context():
        policy = _policy()
        log = BackupLog(
            policy_id=policy.id,
            started_at=datetime.utcnow(),
            status="running",
            extra_json={
                "remote": True,
                "agent_id": policy.backup_agent_id,
                "remote_task_id": "task-1",
            },
        )
        db.session.add(log)
        db.session.commit()
        calls = []

        def fetch(agent_id, task_ids):
            calls.append((agent_id, task_ids))
            return {
                "tasks": {
                    "task-1": {
                        "task_id": "task-1",
                        "status": "success",
                        "result": {
                            "ok": True,
                            "message": "backup completed",
                            "output_file": "/backup/mysql.sql.gz",
                            "file_size": 123,
                            "compress_method": "gzip",
                        },
                    }
                },
                "missing": [],
            }

        monkeypatch.setattr(remote_backup_service, "get_backup_tasks_on_agent", fetch)

        assert remote_backup_service.sync_running_remote_backups() == 1
        db.session.refresh(log)
        assert log.status == "success"
        assert log.file_path == "/backup/mysql.sql.gz"
        assert log.size_bytes == 123

        assert remote_backup_service.sync_running_remote_backups() == 0
        assert len(calls) == 1


def test_poll_network_error_does_not_fail_running_backup(app, monkeypatch):
    with app.app_context():
        policy = _policy()
        log = BackupLog(
            policy_id=policy.id,
            started_at=datetime.utcnow(),
            status="running",
            extra_json={
                "remote": True,
                "agent_id": policy.backup_agent_id,
                "remote_task_id": "task-2",
            },
        )
        db.session.add(log)
        db.session.commit()

        def unavailable(_agent_id, _task_ids):
            raise BackupAgentError("Failed to connect to agent")

        monkeypatch.setattr(remote_backup_service, "get_backup_tasks_on_agent", unavailable)

        assert remote_backup_service.sync_running_remote_backups() == 0
        db.session.refresh(log)
        assert log.status == "running"
        assert "Failed to connect" in log.extra_json["last_poll_error"]


def test_recovery_managed_missing_task_stays_running(app, monkeypatch):
    with app.app_context():
        policy = _policy()
        log = BackupLog(
            policy_id=policy.id,
            started_at=datetime.utcnow(),
            status="running",
            extra_json={
                "remote": True,
                "agent_id": policy.backup_agent_id,
                "remote_task_id": "recover-task-1",
                "recovery_managed": True,
            },
        )
        db.session.add(log)
        db.session.commit()

        monkeypatch.setattr(
            remote_backup_service,
            "get_backup_tasks_on_agent",
            lambda _agent_id, _task_ids: {"tasks": {}, "missing": ["recover-task-1"]},
        )

        assert remote_backup_service.sync_running_remote_backups() == 0
        db.session.refresh(log)
        assert log.status == "running"
        assert log.extra_json["remote_status"] == "recovering"


def test_checkpoint_enables_recovery_and_lost_dump_fails_without_retry(app, monkeypatch):
    with app.app_context():
        policy = _policy()
        log = BackupLog(
            policy_id=policy.id,
            started_at=datetime.utcnow(),
            status="running",
            extra_json={
                "remote": True,
                "agent_id": policy.backup_agent_id,
                "remote_task_id": "recover-task-2",
            },
        )
        db.session.add(log)
        db.session.commit()
        monkeypatch.setattr(remote_backup_service, "set_backup_agent_task", lambda *_args, **_kwargs: True)

        updated = remote_backup_service.checkpoint_remote_backup(
            policy.backup_agent_id,
            {
                "task_id": "recover-task-2",
                "status": "running",
                "phase": "dumping",
                "pid": 123,
                "process_start_ticks": "456",
                "process_command_hash": "hash",
            },
        )
        assert updated.id == log.id
        assert remote_backup_service.recoverable_remote_backups(policy.backup_agent_id) == [
            {
                "task_id": "recover-task-2",
                "backup_log_id": log.id,
                "phase": "dumping",
                "status": "running",
                "pid": 123,
                "process_start_ticks": "456",
                "process_command_hash": "hash",
                "agent_boot_id": None,
            }
        ]

        remote_backup_service.checkpoint_remote_backup(
            policy.backup_agent_id,
            {
                "task_id": "recover-task-2",
                "status": "failed",
                "phase": "failed",
                "result": {"ok": False, "message": "dump process lost after agent restart"},
            },
        )
        db.session.refresh(log)
        assert log.status == "failed"
        assert log.error_message == "dump process lost after agent restart"


def test_failed_remote_status_is_committed_before_notification(app, monkeypatch):
    with app.app_context():
        policy = _policy()
        log = BackupLog(
            policy_id=policy.id,
            started_at=datetime.utcnow(),
            status="running",
            extra_json={
                "remote": True,
                "agent_id": policy.backup_agent_id,
                "remote_task_id": "failed-task",
            },
        )
        db.session.add(log)
        db.session.commit()

        monkeypatch.setattr(
            remote_backup_service,
            "get_backup_tasks_on_agent",
            lambda _agent_id, _task_ids: {
                "tasks": {
                    "failed-task": {
                        "status": "failed",
                        "result": {"ok": False, "message": "dump failed", "command": ["mysqldump"]},
                    }
                },
                "missing": [],
            },
        )
        observed = []

        def notify(**_kwargs):
            observed.append({
                "dirty": list(db.session.dirty),
                "status": BackupLog.query.get(log.id).status,
            })
            return {"ok": True}

        monkeypatch.setattr(remote_backup_service, "notify_backup_failure", notify)

        assert remote_backup_service.sync_running_remote_backups() == 1
        db.session.refresh(log)
        assert observed == [{"dirty": [], "status": "failed"}]
        assert log.extra_json["notify"] == {"ok": True}


def test_concurrent_reconcile_is_skipped_without_waiting(app):
    with app.app_context():
        assert remote_backup_service._REMOTE_BACKUP_RECONCILE_LOCK.acquire(blocking=False)
        try:
            assert remote_backup_service.sync_running_remote_backups() == 0
        finally:
            remote_backup_service._REMOTE_BACKUP_RECONCILE_LOCK.release()
