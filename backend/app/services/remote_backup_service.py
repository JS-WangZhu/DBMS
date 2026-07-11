import uuid
from collections import defaultdict
from datetime import datetime

from flask import current_app

from app.extensions import db
from app.models.backup import BackupLog, BackupPolicy
from app.models.db_asset import DatabaseInstance
from app.services.backup_agent_client import (
    BackupAgentError,
    execute_backup_on_agent,
    get_backup_tasks_on_agent,
)
from app.services.notifier import notify_backup_failure


def _compress_method(policy: BackupPolicy) -> str:
    extra = policy.extra_json if isinstance(policy.extra_json, dict) else {}
    method = extra.get("compress_method")
    if method not in {"none", "gzip", "zstd"}:
        method = "gzip" if policy.compress else "none"
    return method


def submit_remote_backup(policy: BackupPolicy, dry_run: bool = False):
    """Submit a remote backup without holding the request until it finishes."""
    if dry_run:
        result = execute_backup_on_agent(
            policy_id=policy.id,
            agent_id=policy.backup_agent_id,
            dry_run=True,
        )
        return result, (200 if result.get("ok") else 500)

    task_id = uuid.uuid4().hex
    log = BackupLog(
        policy_id=policy.id,
        started_at=datetime.utcnow(),
        status="running",
        extra_json={
            "remote": True,
            "agent_id": policy.backup_agent_id,
            "remote_task_id": task_id,
            "remote_status": "submitting",
            "command": [],
        },
    )
    db.session.add(log)
    db.session.commit()

    try:
        result = execute_backup_on_agent(
            policy_id=policy.id,
            agent_id=policy.backup_agent_id,
            dry_run=False,
            task_id=task_id,
        )
        data = result.get("data") or {}
        extra = dict(log.extra_json or {})
        extra["remote_status"] = data.get("status") or "submitted"
        extra.pop("submission_error", None)
        log.extra_json = extra
        db.session.commit()
        return {
            "ok": True,
            "message": "backup submitted",
            "data": {
                "status": extra["remote_status"],
                "task_id": task_id,
                "backup_log_id": log.id,
            },
        }, 202
    except BackupAgentError as exc:
        # A timeout or broken response does not prove submission failed. Keep the
        # durable log running: the next records refresh queries the known task id.
        extra = dict(log.extra_json or {})
        extra["remote_status"] = "submission_unknown"
        extra["submission_error"] = str(exc)
        log.extra_json = extra
        db.session.commit()
        return {
            "ok": True,
            "message": "backup submission awaiting confirmation",
            "data": {
                "status": "submission_unknown",
                "task_id": task_id,
                "backup_log_id": log.id,
            },
        }, 202


def _finish_remote_log(log: BackupLog, policy: BackupPolicy, task: dict):
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    cancelled = task.get("status") == "cancelled" or bool(result.get("cancelled"))
    succeeded = task.get("status") == "success" and bool(result.get("ok"))
    method = _compress_method(policy)
    extra = dict(log.extra_json or {})
    extra.update({
        "remote": True,
        "agent_id": extra.get("agent_id") or policy.backup_agent_id,
        "remote_status": task.get("status"),
        "command": result.get("command", []),
        "compress": method != "none",
        "compress_method": result.get("compress_method") or method,
        "encrypt": (
            (policy.extra_json or {}).get("encrypt")
            if isinstance(policy.extra_json, dict)
            else None
        ),
        "s3": {"ok": False, "message": "s3 upload disabled"},
    })
    if isinstance(result.get("encrypt"), dict):
        extra["encrypt"] = result["encrypt"]
    if isinstance(result.get("s3"), dict):
        extra["s3"] = result["s3"]
    extra.pop("last_poll_error", None)

    log.finished_at = datetime.utcnow()
    log.file_path = result.get("output_file")
    log.size_bytes = result.get("file_size")
    log.status = "cancelled" if cancelled else ("success" if succeeded else "failed")
    log.error_message = None if succeeded else (result.get("message") or "remote backup failed")
    if not succeeded and not cancelled:
        instance = DatabaseInstance.query.get(policy.target_id)
        extra["notify"] = notify_backup_failure(
            policy=policy,
            instance=instance,
            error_message=log.error_message,
            command=result.get("command", []),
        )
    log.extra_json = extra


def sync_running_remote_backups(limit: int = 200) -> int:
    """Refresh running remote logs in batches, once per agent.

    Terminal logs are not selected on future refreshes, so a successful backup
    is never queried from the agent again.
    """
    rows = (
        db.session.query(BackupLog, BackupPolicy)
        .join(BackupPolicy, BackupLog.policy_id == BackupPolicy.id)
        .filter(BackupLog.status == "running")
        .order_by(BackupLog.id.desc())
        .limit(limit)
        .all()
    )
    grouped = defaultdict(list)
    for log, policy in rows:
        extra = log.extra_json if isinstance(log.extra_json, dict) else {}
        if not extra.get("remote"):
            continue
        agent_id = extra.get("agent_id") or policy.backup_agent_id
        task_id = extra.get("remote_task_id")
        if agent_id and task_id:
            grouped[int(agent_id)].append((log, policy, str(task_id)))

    updated = 0
    for agent_id, items in grouped.items():
        task_ids = [item[2] for item in items]
        try:
            payload = get_backup_tasks_on_agent(agent_id, task_ids)
        except BackupAgentError as exc:
            for log, _policy, _task_id in items:
                extra = dict(log.extra_json or {})
                extra["last_poll_error"] = str(exc)
                extra["last_poll_at"] = datetime.utcnow().isoformat() + "Z"
                log.extra_json = extra
            current_app.logger.warning(
                "remote backup refresh failed: agent_id=%s error=%s", agent_id, exc
            )
            continue

        tasks = payload.get("tasks") if isinstance(payload.get("tasks"), dict) else {}
        missing = set(payload.get("missing") or [])
        for log, policy, task_id in items:
            task = tasks.get(task_id)
            if task:
                status = task.get("status")
                if status in {"success", "failed"}:
                    _finish_remote_log(log, policy, task)
                    updated += 1
                else:
                    extra = dict(log.extra_json or {})
                    extra["remote_status"] = status or "running"
                    extra["last_poll_at"] = datetime.utcnow().isoformat() + "Z"
                    extra.pop("last_poll_error", None)
                    log.extra_json = extra
            elif task_id in missing:
                _finish_remote_log(
                    log,
                    policy,
                    {
                        "status": "failed",
                        "result": {
                            "ok": False,
                            "message": "backup task result not found in agent memory",
                        },
                    },
                )
                updated += 1

    if grouped:
        db.session.commit()
    return updated
