import os
import threading
from datetime import datetime, timedelta

from apscheduler.triggers.cron import CronTrigger
from flask import Blueprint, current_app, request, send_file, Response, stream_with_context

from app.api.routes.common import active_user_required, admin_required
from app.extensions import db, scheduler
from app.models.backup_agent import BackupAgent
from app.models.backup import BackupLog, BackupPolicy, _utc_isoformat
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.models.notify_target import BackupNotifyTarget
from app.models.s3_storage_config import S3StorageConfig
from app.services.audit import log_audit
from app.services.backup_executor import run_backup_policy
from app.services.backup_agent_client import BackupAgentError, download_backup_file_from_agent
from app.services.remote_backup_service import submit_remote_backup, sync_running_remote_backups
from app.services.monitor_snapshot_service import latest_payload_by_instance_ids
from app.services.notifier import test_notify_target, notify_backup_failure
from app.services.s3_storage import upload_file_to_s3, generate_presigned_download_url
from app.tasks.scheduler import sync_backup_jobs
from app.utils.response import error_response, ok_response

bp = Blueprint("backups", __name__, url_prefix="/backups")


CRON_ALIAS_MAP = {
    "@every_minute": "* * * * *",
    "@hourly": "0 * * * *",
    "@daily": "0 0 * * *",
    "@weekly": "0 0 * * 0",
    "@monthly": "0 0 1 * *",
}
S3_DOWNLOAD_LIFECYCLE_DAYS = 30


def _parse_datetime(value: str):
    if not value:
        return None
    text = value.strip().replace("Z", "")
    try:
        return datetime.fromisoformat(text)
    except Exception:
        return None


def _validate_cron_expr(expr: str):
    normalized = CRON_ALIAS_MAP.get((expr or "").strip(), (expr or "").strip())
    if not normalized:
        return False
    try:
        CronTrigger.from_crontab(normalized)
        return True
    except Exception:
        return False


def _to_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _normalize_extra_json(extra_json):
    extra = extra_json or {}
    notify_cfg = extra.get("notify") or {}

    ids = notify_cfg.get("target_ids") or []
    target_ids = []
    for item in ids:
        try:
            target_ids.append(int(item))
        except Exception:
            continue

    channels = notify_cfg.get("channels") or []
    if not isinstance(channels, list):
        channels = []

    extra["notify"] = {
        "on_failure": _to_bool(notify_cfg.get("on_failure", True), default=True),
        "channels": channels,
        "target_ids": target_ids,
    }

    s3_cfg = extra.get("s3") if isinstance(extra.get("s3"), dict) else {}
    upload_mode = str(s3_cfg.get("upload_mode") or "native").strip().lower()
    if upload_mode not in {"native", "us3"}:
        upload_mode = "native"
    extra["s3"] = {
        "enabled": _to_bool(s3_cfg.get("enabled", False), default=False),
        "upload_mode": upload_mode,
        "us3_cli_path": (s3_cfg.get("us3_cli_path") or "").strip() or "/data/us3cli-linux64",
    }

    compress_method = str(extra.get("compress_method") or "").strip().lower()
    if compress_method not in {"none", "gzip", "zstd"}:
        compress_flag = extra.get("compress")
        compress_method = "none" if compress_flag is False else "gzip"
    extra["compress_method"] = compress_method

    return extra


def _validate_target_binding(target_type, target_id, db_type):
    if target_type != "instance":
        return "backup currently supports instance target only"

    instance = DatabaseInstance.query.get(int(target_id))
    if not instance:
        return "target instance not found"
    if instance.db_type != db_type:
        return f"target instance db_type mismatch: expected {db_type}, got {instance.db_type}"

    return None


def _validate_backup_tool_binding(db_type, backup_tool_config_id, backup_agent_id):
    if backup_tool_config_id in (None, ""):
        return None
    from app.models.backup_tool_config import BackupToolConfig

    tool = BackupToolConfig.query.get(int(backup_tool_config_id))
    if not tool:
        return "backup_tool_config not found"
    if tool.db_type != db_type:
        return f"backup tool db_type mismatch: expected {db_type}, got {tool.db_type}"
    if backup_agent_id in (None, ""):
        if tool.backup_agent_id is not None:
            return "local backup policy can only use local backup tool"
        return None
    if tool.backup_agent_id != int(backup_agent_id):
        return "selected backup tool does not belong to selected agent"
    return None


def _apply_policy_fields(policy: BackupPolicy, payload: dict, is_create: bool = False):
    if is_create:
        required = ["name", "target_type", "target_id", "db_type", "tool_name", "cron_expr", "storage_path"]
        missing = [key for key in required if payload.get(key) in (None, "")]
        if missing:
            return f"missing fields: {', '.join(missing)}"

    if "db_type" in payload and payload["db_type"] not in {"mysql", "mongodb"}:
        return "backup currently supports mysql and mongodb"

    if "target_type" in payload and payload["target_type"] not in {"instance", "cluster"}:
        return "invalid target_type"

    if is_create or "cron_expr" in payload:
        cron_expr = payload.get("cron_expr", policy.cron_expr)
        if cron_expr and not _validate_cron_expr(cron_expr):
            return "invalid cron_expr, expected standard crontab format like '0 2 * * *'"

    effective_target_type = payload.get("target_type", policy.target_type)
    effective_target_id = payload.get("target_id", policy.target_id)
    effective_db_type = payload.get("db_type", policy.db_type)
    effective_agent_id = payload.get("backup_agent_id", policy.backup_agent_id)
    if "backup_agent_id" in payload and payload.get("backup_agent_id") is None:
        effective_agent_id = None
    effective_tool_id = payload.get("backup_tool_config_id", policy.backup_tool_config_id)
    if "backup_tool_config_id" in payload and payload.get("backup_tool_config_id") is None:
        effective_tool_id = None

    if effective_target_type and effective_db_type and effective_target_id not in (None, ""):
        err = _validate_target_binding(effective_target_type, effective_target_id, effective_db_type)
        if err:
            return err
    tool_err = _validate_backup_tool_binding(effective_db_type, effective_tool_id, effective_agent_id)
    if tool_err:
        return tool_err

    for field in ["name", "target_type", "db_type", "backup_type", "tool_name", "cron_expr", "storage_path"]:
        if field in payload:
            setattr(policy, field, payload[field])

    for field in ["target_id", "retain_days", "s3_storage_config_id", "backup_tool_config_id", "backup_agent_id"]:
        if field in payload and payload[field] is not None:
            setattr(policy, field, int(payload[field]))

    if "s3_storage_config_id" in payload and payload["s3_storage_config_id"] is None:
        policy.s3_storage_config_id = None

    if "backup_tool_config_id" in payload and payload["backup_tool_config_id"] is None:
        policy.backup_tool_config_id = None

    # Handle backup_agent_id None case (clear agent assignment)
    if "backup_agent_id" in payload and payload["backup_agent_id"] is None:
        policy.backup_agent_id = None

    for field in ["compress", "enabled"]:
        if field in payload:
            setattr(policy, field, bool(payload[field]))

    requested_compress_method = None
    if "compress_method" in payload:
        requested_compress_method = str(payload.get("compress_method") or "").strip().lower()
        if requested_compress_method not in {"none", "gzip", "zstd"}:
            return "invalid compress_method, allowed: none/gzip/zstd"

    if "extra_json" in payload:
        policy.extra_json = _normalize_extra_json(payload.get("extra_json") or {})

    if requested_compress_method is not None:
        extra = _normalize_extra_json(policy.extra_json or {})
        extra["compress_method"] = requested_compress_method
        policy.extra_json = extra
        policy.compress = requested_compress_method != "none"
    elif "extra_json" in payload:
        method = policy.extra_json.get("compress_method")
        if method in {"none", "gzip", "zstd"}:
            policy.compress = method != "none"

    return None


def _validate_notify_target(channel, address):
    if channel not in {"wecom", "email"}:
        return "invalid channel"
    if not address:
        return "address is required"
    if channel == "wecom" and not str(address).startswith(("http://", "https://")):
        return "wecom webhook must be a valid http/https url"
    if channel == "email" and "@" not in str(address):
        return "email address is invalid"
    return None


def _extract_s3_key(log: BackupLog):
    extra = log.extra_json or {}
    s3_info = extra.get("s3") if isinstance(extra, dict) else None
    if not isinstance(s3_info, dict):
        return None, None
    if not s3_info.get("ok"):
        return None, None
    bucket = s3_info.get("bucket")
    key = s3_info.get("key")
    if not bucket or not key:
        return None, None
    return bucket, key


def _get_log_base_time(log: BackupLog):
    return log.finished_at or log.started_at


def _is_s3_download_allowed(log: BackupLog):
    base_time = _get_log_base_time(log)
    if not base_time:
        return True, None
    expires_at = base_time + timedelta(days=S3_DOWNLOAD_LIFECYCLE_DAYS)
    return datetime.utcnow() <= expires_at, expires_at


def _is_local_download_allowed(log: BackupLog, policy: BackupPolicy):
    if not log.file_path or not os.path.exists(log.file_path):
        return False
    if not policy or not policy.retain_days or policy.retain_days <= 0:
        return True
    base_time = _get_log_base_time(log)
    if not base_time:
        return True
    return datetime.utcnow() <= (base_time + timedelta(days=policy.retain_days))


def _resolve_remote_agent_id(log: BackupLog):
    extra = log.extra_json if isinstance(log.extra_json, dict) else {}
    if not extra.get("remote"):
        return None
    agent_id = extra.get("agent_id")
    try:
        return int(agent_id) if agent_id is not None else None
    except Exception:
        return None


def _is_remote_download_available(log: BackupLog):
    return bool(_resolve_remote_agent_id(log) and log.file_path)


def _infer_mysql_replication_role(payload: dict):
    role = payload.get("replication_role")
    if role:
        return role

    io_running = payload.get("replica_io_running")
    sql_running = payload.get("replica_sql_running")
    lag = payload.get("seconds_behind_master")
    effective_read_only = payload.get("effective_read_only")
    read_only = payload.get("read_only")

    if io_running is True or sql_running is True or lag is not None:
        return "slave"
    if effective_read_only is True:
        return "read_only"
    if effective_read_only is False:
        return "master"
    if read_only is True:
        return "read_only"
    if read_only is False:
        return "master"
    return "unknown"


def _mysql_role_text(role: str):
    if role == "dual":
        return "主库/从库"
    if role == "master_slave":
        return "主库/从库"
    if role == "slave":
        return "从库"
    if role == "master":
        return "主库"
    if role == "read_only":
        return "只读"
    return "未知"


def _instance_key(item: DatabaseInstance):
    host = (item.resolved_ip or item.host_input or "").strip().lower()
    if not host:
        return None
    return f"{host}:{item.port}"


def _source_key(payload: dict):
    host = (payload.get("replica_source_resolved_ip") or payload.get("replica_source_host") or "").strip().lower()
    port = payload.get("replica_source_port")
    if not host or port in (None, ""):
        return None
    return f"{host}:{port}"


def _infer_mysql_dual_role(item: DatabaseInstance, rows_by_cluster: dict, payload_by_instance: dict):
    if not item.cluster_id:
        return None

    self_payload = payload_by_instance.get(item.id) or {}
    self_source = _source_key(self_payload)
    self_key = _instance_key(item)
    if not self_source or not self_key:
        return None

    peers = [row for row in rows_by_cluster.get(item.cluster_id, []) if row.id != item.id]
    upstream = next((row for row in peers if _instance_key(row) == self_source), None)
    if not upstream:
        return None

    peer_payload = payload_by_instance.get(upstream.id) or {}
    peer_source = _source_key(peer_payload)
    if peer_source == self_key:
        return "dual"
    return None


@bp.get("/managed-instances")
@active_user_required
def list_managed_instances():
    db_type = request.args.get("db_type")
    query = DatabaseInstance.query.filter_by(enabled=True)
    if db_type:
        query = query.filter_by(db_type=db_type)
    else:
        query = query.filter(DatabaseInstance.db_type.in_(["mysql", "mongodb"]))

    rows = query.order_by(DatabaseInstance.db_type.asc(), DatabaseInstance.id.asc()).all()
    payload_by_instance = {}
    rows_by_type = {}
    for row in rows:
        rows_by_type.setdefault(row.db_type, []).append(row.id)
    for db_type, ids in rows_by_type.items():
        payload_by_instance.update(latest_payload_by_instance_ids(db_type=db_type, instance_ids=ids))

    rows_by_cluster = {}
    for row in rows:
        if row.cluster_id:
            rows_by_cluster.setdefault(row.cluster_id, []).append(row)

    items = []
    for item in rows:
        data = item.to_dict()
        if item.db_type == "mysql":
            payload = payload_by_instance.get(item.id) or {}
            role = _infer_mysql_dual_role(item, rows_by_cluster, payload_by_instance) or _infer_mysql_replication_role(payload)
            role_text = _mysql_role_text(role)
        elif item.db_type == "mongodb":
            payload = payload_by_instance.get(item.id) or {}
            mongo_role = payload.get("mongo_role")
            if not mongo_role:
                repl = payload.get("repl") if isinstance(payload.get("repl"), dict) else {}
                state = repl.get("myState")
                if state == 1:
                    mongo_role = "primary"
                elif state == 2:
                    mongo_role = "secondary"
                elif state == 7:
                    mongo_role = "arbiter"
            if mongo_role == "primary":
                role_text = "主库"
            elif mongo_role == "secondary":
                role_text = "从库"
            elif mongo_role == "arbiter":
                role_text = "仲裁"
            elif mongo_role == "mongos":
                role_text = "Mongos"
            elif mongo_role == "configsvr":
                role_text = "配置节点"
            elif mongo_role == "shard":
                role_text = "分片节点"
            elif item.role_label:
                role_text = item.role_label
            else:
                role_text = "未知"
        elif item.role_label:
            role_text = item.role_label
        elif item.is_read_only:
            role_text = "只读"
        else:
            role_text = "未知"
        data["label"] = f"{item.name} [{role_text}] ({item.host_input}:{item.port})"
        items.append(data)

    return ok_response(data=items)


@bp.get("/notify-targets")
@active_user_required
def list_notify_targets():
    channel = request.args.get("channel")
    enabled = request.args.get("enabled")

    query = BackupNotifyTarget.query
    if channel:
        query = query.filter_by(channel=channel)
    if enabled is not None:
        query = query.filter_by(enabled=(enabled.lower() == "true"))

    rows = query.order_by(BackupNotifyTarget.id.desc()).all()
    return ok_response(data=[item.to_dict() for item in rows])


@bp.get("/s3-storage-configs")
@active_user_required
def list_s3_storage_configs():
    enabled = request.args.get("enabled")
    from app.models.s3_storage_config import S3StorageConfig

    query = S3StorageConfig.query
    if enabled is not None:
        query = query.filter_by(enabled=(enabled.lower() == "true"))

    rows = query.order_by(S3StorageConfig.id.desc()).all()
    return ok_response(data=[item.to_dict() for item in rows])


@bp.get("/tool-configs")
@active_user_required
def list_tool_configs():
    """获取备份工具配置列表"""
    from app.models.backup_tool_config import BackupToolConfig

    db_type = request.args.get("db_type")
    enabled = request.args.get("enabled")
    backup_agent_id = request.args.get("backup_agent_id")

    query = BackupToolConfig.query
    if db_type:
        query = query.filter_by(db_type=db_type)
    if enabled is not None:
        query = query.filter_by(enabled=(enabled.lower() == "true"))
    if backup_agent_id is not None:
        if backup_agent_id == "":
            query = query.filter(BackupToolConfig.backup_agent_id.is_(None))
        else:
            query = query.filter_by(backup_agent_id=int(backup_agent_id))

    rows = query.order_by(BackupToolConfig.id.desc()).all()
    return ok_response(data=[item.to_dict() for item in rows])


@bp.post("/notify-targets")
@admin_required
def create_notify_target():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    channel = payload.get("channel")
    address = (payload.get("address") or "").strip()

    if not name:
        return error_response("name is required", code=400)

    err = _validate_notify_target(channel, address)
    if err:
        return error_response(err, code=400)

    item = BackupNotifyTarget(
        name=name,
        channel=channel,
        address=address,
        enabled=bool(payload.get("enabled", True)),
        extra_json=payload.get("extra_json") or {},
    )
    db.session.add(item)
    db.session.commit()

    log_audit(user_id=None, action="backup.notify_target.create", target_type="notify_target", target_id=str(item.id), detail=payload)
    return ok_response(data=item.to_dict(), code=201)


@bp.patch("/notify-targets/<int:target_id>")
@admin_required
def update_notify_target(target_id):
    payload = request.get_json(silent=True) or {}
    item = BackupNotifyTarget.query.get_or_404(target_id)

    channel = payload.get("channel", item.channel)
    address = payload.get("address", item.address)
    err = _validate_notify_target(channel, address)
    if err:
        return error_response(err, code=400)

    for field in ["name", "channel", "address", "enabled"]:
        if field in payload:
            setattr(item, field, payload[field])

    if "extra_json" in payload:
        item.extra_json = payload.get("extra_json") or {}

    db.session.commit()
    log_audit(user_id=None, action="backup.notify_target.update", target_type="notify_target", target_id=str(item.id), detail=payload)
    return ok_response(data=item.to_dict())


@bp.post("/notify-targets/<int:target_id>/test")
@admin_required
def test_notify_target_api(target_id):
    target = BackupNotifyTarget.query.get_or_404(target_id)
    result = test_notify_target(target)
    ok = result.get("result", {}).get("ok")
    if not ok:
        return error_response(result.get("result", {}).get("message", "send failed"), code=502)
    return ok_response(data=result)


@bp.delete("/notify-targets/<int:target_id>")
@admin_required
def delete_notify_target(target_id):
    item = BackupNotifyTarget.query.get_or_404(target_id)
    db.session.delete(item)
    db.session.commit()
    log_audit(user_id=None, action="backup.notify_target.delete", target_type="notify_target", target_id=str(target_id))
    return ok_response(message="deleted")


@bp.get("/policies")
@active_user_required
def list_policies():
    db_type = request.args.get("db_type")
    query = BackupPolicy.query
    if db_type:
        query = query.filter_by(db_type=db_type)
    items = query.order_by(BackupPolicy.id.desc()).all()
    return ok_response(data=[item.to_dict() for item in items])


@bp.post("/policies")
@active_user_required
def create_policy():
    payload = request.get_json(silent=True) or {}

    policy = BackupPolicy()
    err = _apply_policy_fields(policy, payload, is_create=True)
    if err:
        return error_response(err, code=400)

    if not policy.backup_type:
        policy.backup_type = "full"
    if policy.retain_days is None:
        policy.retain_days = 7
    if policy.compress is None:
        policy.compress = True
    if policy.enabled is None:
        policy.enabled = True

    if policy.extra_json is None:
        policy.extra_json = _normalize_extra_json({})
    if "compress_method" not in policy.extra_json:
        policy.extra_json["compress_method"] = "gzip" if policy.compress else "none"

    db.session.add(policy)
    db.session.commit()

    if current_app.config.get("ENABLE_SCHEDULER"):
        sync_backup_jobs(scheduler=scheduler, app=current_app)

    log_audit(user_id=None, action="backup.policy.create", target_type="backup_policy", target_id=str(policy.id), detail=payload)
    return ok_response(data=policy.to_dict(), code=201)


@bp.patch("/policies/<int:policy_id>")
@active_user_required
def update_policy(policy_id):
    payload = request.get_json(silent=True) or {}
    policy = BackupPolicy.query.get_or_404(policy_id)

    err = _apply_policy_fields(policy, payload, is_create=False)
    if err:
        return error_response(err, code=400)

    if policy.extra_json is None:
        policy.extra_json = _normalize_extra_json({})

    db.session.commit()
    if current_app.config.get("ENABLE_SCHEDULER"):
        sync_backup_jobs(scheduler=scheduler, app=current_app)

    log_audit(user_id=None, action="backup.policy.update", target_type="backup_policy", target_id=str(policy.id), detail=payload)
    return ok_response(data=policy.to_dict())


@bp.post("/run/<int:policy_id>")
@active_user_required
def run_policy(policy_id):
    dry_run = request.args.get("dry_run", "false").lower() == "true"
    policy = BackupPolicy.query.get_or_404(policy_id)
    agent_id = policy.backup_agent_id

    if dry_run:
        result, status_code = _execute_policy_once(policy_id=policy_id, dry_run=True)
        log_audit(
            user_id=None,
            action="backup.run.manual",
            target_type="backup_policy",
            target_id=str(policy_id),
            detail={"dry_run": True, "ok": result.get("ok"), "message": result.get("message"), "agent_id": agent_id},
        )
        if result.get("ok"):
            return ok_response(data=result, code=status_code)
        return error_response(result.get("message", "backup failed"), code=status_code, data=result)

    app = current_app._get_current_object()
    worker = threading.Thread(target=_run_policy_async, args=(app, policy_id), daemon=True)
    worker.start()

    log_audit(
        user_id=None,
        action="backup.run.manual",
        target_type="backup_policy",
        target_id=str(policy_id),
        detail={"dry_run": False, "ok": True, "message": "submitted", "agent_id": agent_id},
    )
    return ok_response(data={"ok": True, "status": "submitted", "policy_id": policy_id}, code=202)


def _run_policy_async(app, policy_id: int):
    with app.app_context():
        try:
            _execute_policy_once(policy_id=policy_id, dry_run=False)
        except Exception:
            current_app.logger.exception("backup async execute failed: policy_id=%s", policy_id)


def _execute_policy_once(policy_id: int, dry_run: bool = False):
    policy = BackupPolicy.query.get(policy_id)
    if not policy:
        return {"ok": False, "message": "policy not found"}, 404

    agent_id = policy.backup_agent_id
    if not agent_id:
        result = run_backup_policy(policy_id=policy_id, dry_run=dry_run)
        status_code = 200 if result.get("ok") else 500
        return result, status_code

    return submit_remote_backup(policy, dry_run=dry_run)


@bp.get("/logs")
@active_user_required
def list_logs():
    # User refresh is the reconciliation trigger. Only logs still marked
    # running are queried; terminal results are never requested again.
    sync_running_remote_backups()

    policy_id = request.args.get("policy_id")
    status = request.args.get("status")
    db_type = request.args.get("db_type")
    keyword = request.args.get("keyword")
    start_at = _parse_datetime(request.args.get("start_at", ""))
    end_at = _parse_datetime(request.args.get("end_at", ""))
    page = max(int(request.args.get("page", "1")), 1)
    page_size = min(max(int(request.args.get('page_size', '10')), 1), 200)

    query = db.session.query(BackupLog, BackupPolicy).join(BackupPolicy, BackupLog.policy_id == BackupPolicy.id)

    if policy_id:
        query = query.filter(BackupLog.policy_id == int(policy_id))
    if status:
        query = query.filter(BackupLog.status == status)
    if db_type:
        query = query.filter(BackupPolicy.db_type == db_type)
    if keyword:
        query = query.filter(BackupPolicy.name.like(f"%{keyword}%"))
    if start_at:
        query = query.filter(BackupLog.started_at >= start_at)
    if end_at:
        query = query.filter(BackupLog.started_at <= end_at)

    total = query.count()
    rows = (
        query.order_by(BackupLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    remote_agent_ids = set()
    for log, _policy in rows:
        extra = log.extra_json if isinstance(log.extra_json, dict) else {}
        if extra.get("remote") and extra.get("agent_id"):
            try:
                remote_agent_ids.add(int(extra.get("agent_id")))
            except Exception:
                continue
    agent_name_map = {}
    if remote_agent_ids:
        agents = BackupAgent.query.filter(BackupAgent.id.in_(list(remote_agent_ids))).all()
        agent_name_map = {agent.id: agent.name for agent in agents}

    items = []
    for log, policy in rows:
        item = log.to_dict()
        extra = item.get("extra_json") if isinstance(item.get("extra_json"), dict) else {}
        agent_name = "本地备份"
        if extra.get("remote"):
            agent_id = extra.get("agent_id")
            try:
                agent_id = int(agent_id) if agent_id is not None else None
            except Exception:
                agent_id = None
            if agent_id and agent_id in agent_name_map:
                agent_name = agent_name_map[agent_id]
            elif policy.agent and policy.agent.name:
                agent_name = policy.agent.name
            else:
                agent_name = "远程备份"
        item["policy_name"] = policy.name
        item["db_type"] = policy.db_type
        item["cron_expr"] = policy.cron_expr
        item["retain_days"] = policy.retain_days
        policy_method = (policy.extra_json or {}).get("compress_method") if isinstance(policy.extra_json, dict) else None
        item["compress_method"] = item.get("compress_method") or policy_method or ("gzip" if policy.compress else "none")
        item["compress"] = item["compress_method"] != "none"
        item["agent_name"] = agent_name
        items.append(item)

    return ok_response(
        data={
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@bp.get("/logs/<int:log_id>/download-url")
@active_user_required
def get_download_url(log_id):
    log = BackupLog.query.get_or_404(log_id)
    policy = BackupPolicy.query.get(log.policy_id)
    local_available = _is_local_download_allowed(log, policy)
    available_modes = []
    if local_available:
        available_modes.append("local")

    s3_allowed, s3_expires_at = _is_s3_download_allowed(log)
    s3_available = False
    s3_url = None
    unavailable_reason = ""
    agent_available = _is_remote_download_available(log)
    bucket, key = _extract_s3_key(log)
    if s3_allowed and bucket and key and policy and policy.s3_storage_config_id:
        s3_config = S3StorageConfig.query.get(policy.s3_storage_config_id)
        if s3_config and s3_config.enabled:
            s3_url = generate_presigned_download_url(bucket, key, s3_config.to_s3_config())
            if s3_url:
                s3_available = True
                available_modes.append("s3")
        else:
            unavailable_reason = "s3 storage config is disabled"
    elif bucket and key and not s3_allowed:
        unavailable_reason = "s3 file expired by lifecycle policy"
    elif bucket and key and policy and not policy.s3_storage_config_id:
        unavailable_reason = "s3 storage config is not set"
    elif bucket and key and policy and policy.s3_storage_config_id and not s3_available:
        unavailable_reason = "s3 download url generation failed"
    elif not local_available:
        unavailable_reason = "backup file not found"
    if agent_available:
        available_modes.append("agent")

    data = {
        "available_modes": available_modes,
        "local": {"available": local_available},
        "s3": {
            "available": s3_available,
            "url": s3_url,
            "lifecycle_days": S3_DOWNLOAD_LIFECYCLE_DAYS,
            "expired": bool(bucket and key and not s3_allowed),
            "available_until": s3_expires_at.isoformat() if s3_expires_at else None,
        },
        "agent": {
            "available": agent_available,
            "url": f"/api/v1/backups/logs/{log_id}/download-agent" if agent_available else None,
        },
        "message": unavailable_reason if not available_modes else "",
    }
    if len(available_modes) == 1:
        data["mode"] = available_modes[0]
        if data["mode"] == "s3":
            data["url"] = s3_url

    return ok_response(data=data)


@bp.get("/logs/<int:log_id>/download")
@active_user_required
def download_log_file(log_id):
    log = BackupLog.query.get_or_404(log_id)
    policy = BackupPolicy.query.get(log.policy_id)
    if not _is_local_download_allowed(log, policy):
        return error_response("backup file not found", code=404)

    filename = os.path.basename(log.file_path)
    return send_file(log.file_path, as_attachment=True, download_name=filename)


@bp.get("/logs/<int:log_id>/download-agent")
@active_user_required
def download_log_file_via_agent(log_id):
    log = BackupLog.query.get_or_404(log_id)
    agent_id = _resolve_remote_agent_id(log)
    if not agent_id or not log.file_path:
        return error_response("backup file not found on agent", code=404)
    try:
        agent_resp = download_backup_file_from_agent(agent_id=agent_id, file_path=log.file_path)
    except BackupAgentError as e:
        return error_response(str(e), code=502)
    filename = os.path.basename(log.file_path)

    def generate():
        for chunk in agent_resp.iter_content(chunk_size=1024 * 1024):
            if chunk:
                yield chunk

    return Response(
        stream_with_context(generate()),
        headers={
            "Content-Type": "application/octet-stream",
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@bp.delete("/logs/<int:log_id>")
@admin_required
def delete_log(log_id):
    delete_file = request.args.get("delete_file", "false").lower() == "true"
    item = BackupLog.query.get_or_404(log_id)

    file_deleted = False
    if delete_file and item.file_path and os.path.exists(item.file_path):
        try:
            os.remove(item.file_path)
            file_deleted = True
        except Exception:
            file_deleted = False

    db.session.delete(item)
    db.session.commit()

    log_audit(
        user_id=None,
        action="backup.log.delete",
        target_type="backup_log",
        target_id=str(log_id),
        detail={"delete_file": delete_file, "file_deleted": file_deleted},
    )

    return ok_response(data={"deleted": True, "file_deleted": file_deleted})


@bp.delete("/policies/<int:policy_id>")
@admin_required
def delete_policy(policy_id):
    policy = BackupPolicy.query.get_or_404(policy_id)
    
    # 鍒犻櫎鐩稿叧鐨勫浠芥棩蹇?    from app.models.backup import BackupLog
    BackupLog.query.filter_by(policy_id=policy_id).delete()
    
    db.session.delete(policy)
    db.session.commit()
    log_audit(user_id=None, action="backup.policy.delete", target_type="backup_policy", target_id=str(policy_id))
    return ok_response(message="deleted")


@bp.get("/overview")
@active_user_required
def backup_overview():
    # Reconcile remote jobs before aggregating, matching the records endpoint.
    # Otherwise the overview can remain stale until the records page is opened.
    sync_running_remote_backups()

    hours = int(request.args.get("hours", "24"))
    hours = max(1, min(hours, 168))
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    clusters = DatabaseCluster.query.order_by(DatabaseCluster.name.asc(), DatabaseCluster.id.asc()).all()
    instances = DatabaseInstance.query.filter(DatabaseInstance.cluster_id.isnot(None)).all()
    instance_map = {item.id: item for item in instances}

    log_rows = (
        db.session.query(BackupLog, BackupPolicy)
        .join(BackupPolicy, BackupLog.policy_id == BackupPolicy.id)
        .filter(BackupLog.started_at >= cutoff)
        .order_by(BackupLog.started_at.desc(), BackupLog.id.desc())
        .all()
    )

    logs_by_cluster = {}
    for log, policy in log_rows:
        if policy.target_type != "instance":
            continue
        instance = instance_map.get(policy.target_id)
        if not instance or not instance.cluster_id:
            continue
        logs_by_cluster.setdefault(instance.cluster_id, []).append((log, policy, instance))

    items = []
    normal_count = 0
    for cluster in clusters:
        cluster_logs = logs_by_cluster.get(cluster.id, [])
        is_normal = any(log.status == "success" for log, _, _ in cluster_logs)
        if is_normal:
            normal_count += 1

        latest_backup = None
        if cluster_logs:
            log, policy, instance = cluster_logs[0]
            latest_backup = {
                "log_id": log.id,
                "policy_id": policy.id,
                "policy_name": policy.name,
                "instance_id": instance.id,
                "instance_name": instance.name,
                "status": log.status,
                "started_at": _utc_isoformat(log.started_at),
                "finished_at": _utc_isoformat(log.finished_at),
                "error_message": log.error_message,
            }

        items.append(
            {
                "cluster_id": cluster.id,
                "cluster_name": cluster.name,
                "db_type": cluster.db_type,
                "business_line": cluster.business_line or cluster.namespace,
                "environment": cluster.environment,
                "backup_status": "normal" if is_normal else "abnormal",
                "successful_backup_count": sum(
                    1 for log, _, _ in cluster_logs if log.status == "success"
                ),
                "latest_backup": latest_backup,
            }
        )

    total = len(clusters)
    summary = {
        "time_window_hours": hours,
        "total_clusters": total,
        "normal_backup_sets": normal_count,
        "abnormal_backup_sets": total - normal_count,
        "normal_ratio": round(normal_count * 100 / total, 2) if total else 0,
        "items": items,
    }

    return ok_response(data=summary)
