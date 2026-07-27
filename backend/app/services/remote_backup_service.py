import uuid
import threading
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
from app.services.redis_cache import get_backup_agent_task, set_backup_agent_task


_REMOTE_BACKUP_RECONCILE_LOCK = threading.Lock()


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
        if data.get("recovery_managed") is True:
            extra["recovery_managed"] = True
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
    if "retention_deleted" in result:
        extra["retention_deleted"] = result["retention_deleted"]
    extra.pop("last_poll_error", None)

    log.finished_at = datetime.utcnow()
    log.file_path = result.get("output_file")
    log.size_bytes = result.get("file_size")
    log.status = "cancelled" if cancelled else ("success" if succeeded else "failed")
    log.error_message = None if succeeded else (result.get("message") or "remote backup failed")
    notification = None
    if not succeeded and not cancelled:
        # Do not query notification targets or perform network I/O before the
        # terminal status is committed. Query-invoked autoflush used to acquire
        # the backup_logs row lock and hold it for the whole notification timeout.
        extra["notify"] = {"ok": False, "message": "pending"}
        notification = {
            "log_id": log.id,
            "policy_id": policy.id,
            "instance_id": policy.target_id,
            "error_message": log.error_message,
            "command": result.get("command", []),
        }
    log.extra_json = extra
    return notification


def _deliver_failure_notifications(items):
    """Send notifications only after terminal backup rows have been committed."""
    for item in items:
        policy = BackupPolicy.query.get(item["policy_id"])
        log = BackupLog.query.get(item["log_id"])
        if not policy or not log:
            continue
        instance = DatabaseInstance.query.get(item["instance_id"])
        try:
            notify_result = notify_backup_failure(
                policy=policy,
                instance=instance,
                error_message=item["error_message"],
                command=item.get("command") or [],
            )
        except Exception as exc:
            notify_result = {"ok": False, "message": str(exc)}
        extra = dict(log.extra_json or {})
        extra["notify"] = notify_result
        log.extra_json = extra
        db.session.commit()


def _running_remote_rows_for_agent(agent_id: int):
    rows = (
        db.session.query(BackupLog, BackupPolicy)
        .join(BackupPolicy, BackupLog.policy_id == BackupPolicy.id)
        .filter(BackupLog.status == "running")
        .order_by(BackupLog.id.desc())
        .all()
    )
    result = []
    for log, policy in rows:
        extra = log.extra_json if isinstance(log.extra_json, dict) else {}
        assigned_agent_id = extra.get("agent_id") or policy.backup_agent_id
        if extra.get("remote") and assigned_agent_id and int(assigned_agent_id) == int(agent_id):
            result.append((log, policy))
    return result


def checkpoint_remote_backup(agent_id: int, payload: dict):
    with _REMOTE_BACKUP_RECONCILE_LOCK:
        log, notification = _checkpoint_remote_backup(agent_id, payload)
    if notification:
        _deliver_failure_notifications([notification])
    return log


def _checkpoint_remote_backup(agent_id: int, payload: dict):
    """Persist checkpoints only for upgraded agents that opt into recovery."""
    task_id = str(payload.get("task_id") or "").strip()
    if not task_id:
        return None, None
    matched = None
    for log, policy in _running_remote_rows_for_agent(agent_id):
        extra = log.extra_json if isinstance(log.extra_json, dict) else {}
        if str(extra.get("remote_task_id") or "") == task_id:
            matched = (log, policy)
            break
    if not matched:
        return None, None

    log, policy = matched
    status = str(payload.get("status") or "running").strip().lower()
    phase = str(payload.get("phase") or status or "dumping").strip().lower()
    recovery = {
        "phase": phase,
        "status": status,
        "pid": payload.get("pid"),
        "process_start_ticks": payload.get("process_start_ticks"),
        "process_command_hash": payload.get("process_command_hash"),
        "agent_boot_id": payload.get("agent_boot_id"),
        "started_at": payload.get("started_at"),
        "finished_at": payload.get("finished_at"),
        "checkpoint_at": datetime.utcnow().isoformat() + "Z",
    }
    extra = dict(log.extra_json or {})
    extra.update({
        "recovery_managed": True,
        "remote_status": status if status in {"success", "failed", "cancelled"} else phase,
        "recovery": recovery,
    })
    log.extra_json = extra

    notification = None
    if status in {"success", "failed", "cancelled"}:
        notification = _finish_remote_log(
            log,
            policy,
            {
                "status": status,
                "result": payload.get("result") if isinstance(payload.get("result"), dict) else {},
            },
        )
    db.session.commit()
    set_backup_agent_task(agent_id, task_id, {
        "task_id": task_id,
        "backup_log_id": log.id,
        **recovery,
    })
    return log, notification


def recoverable_remote_backups(agent_id: int):
    """Return only tasks previously claimed by a recovery-capable Agent."""
    tasks = []
    for log, _policy in _running_remote_rows_for_agent(agent_id):
        extra = log.extra_json if isinstance(log.extra_json, dict) else {}
        if not extra.get("recovery_managed"):
            continue
        recovery = extra.get("recovery") if isinstance(extra.get("recovery"), dict) else {}
        if not recovery:
            cached = get_backup_agent_task(agent_id, str(extra.get("remote_task_id") or ""))
            recovery = cached if isinstance(cached, dict) else {}
        tasks.append({
            "task_id": str(extra.get("remote_task_id") or ""),
            "backup_log_id": log.id,
            "phase": recovery.get("phase") or extra.get("remote_status") or "dumping",
            "status": recovery.get("status") or "running",
            "pid": recovery.get("pid"),
            "process_start_ticks": recovery.get("process_start_ticks"),
            "process_command_hash": recovery.get("process_command_hash"),
            "agent_boot_id": recovery.get("agent_boot_id"),
        })
    return tasks


def sync_running_remote_backups(limit: int = 200) -> int:
    """Run one reconciliation at a time; page refreshes skip an active run."""
    if not _REMOTE_BACKUP_RECONCILE_LOCK.acquire(blocking=False):
        return 0
    try:
        updated, notifications = _sync_running_remote_backups(limit=limit)
    finally:
        _REMOTE_BACKUP_RECONCILE_LOCK.release()
    if notifications:
        _deliver_failure_notifications(notifications)
    return updated


def _sync_running_remote_backups(limit: int = 200) -> int:
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
    notifications = []
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
            db.session.commit()
            continue

        tasks = payload.get("tasks") if isinstance(payload.get("tasks"), dict) else {}
        missing = set(payload.get("missing") or [])
        for log, policy, task_id in items:
            task = tasks.get(task_id)
            if task:
                status = task.get("status")
                if status in {"success", "failed"}:
                    notification = _finish_remote_log(log, policy, task)
                    if notification:
                        notifications.append(notification)
                    updated += 1
                else:
                    extra = dict(log.extra_json or {})
                    extra["remote_status"] = status or "running"
                    if task.get("recovery_managed") is True:
                        extra["recovery_managed"] = True
                        extra["recovery"] = {
                            "phase": task.get("phase") or status or "dumping",
                            "status": status or "running",
                            "pid": task.get("pid"),
                            "process_start_ticks": task.get("process_start_ticks"),
                            "process_command_hash": task.get("process_command_hash"),
                            "agent_boot_id": task.get("agent_boot_id"),
                            "started_at": task.get("started_at"),
                            "finished_at": task.get("finished_at"),
                            "checkpoint_at": datetime.utcnow().isoformat() + "Z",
                        }
                    extra["last_poll_at"] = datetime.utcnow().isoformat() + "Z"
                    extra.pop("last_poll_error", None)
                    log.extra_json = extra
            elif task_id in missing:
                extra = dict(log.extra_json or {})
                if extra.get("recovery_managed"):
                    extra["remote_status"] = "recovering"
                    extra["last_poll_at"] = datetime.utcnow().isoformat() + "Z"
                    log.extra_json = extra
                    continue
                notification = _finish_remote_log(
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
                if notification:
                    notifications.append(notification)
                updated += 1

        # Keep the row-lock window bounded to one Agent. In particular, never
        # retain dirty backup rows while polling another remote endpoint.
        db.session.commit()

    return updated, notifications
