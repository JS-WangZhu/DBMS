from datetime import datetime

from app.extensions import db
from app.models.backup import BackupLog, BackupPolicy
from app.models.backup_agent import BackupAgent
from app.models.db_asset import DatabaseInstance
from app.services.backup_agent_client import BackupAgentError
from app.services import remote_backup_service


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
