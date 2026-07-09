import logging
import os
import secrets
import shutil
import subprocess
import tempfile
import struct
import gzip
import threading
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from flask import Blueprint, request, current_app, send_file
from app.utils.response import error_response, ok_response

bp = Blueprint("agent", __name__, url_prefix="/api/agent")

AGENT_VERSION = "1.0.0"
MULTIPART_CHUNK_SIZE = 8 * 1024 * 1024
logger = logging.getLogger(__name__)

# The server owns the durable BackupLog. The agent only keeps live task state
# and results in memory, decoupling backup execution from the HTTP connection.
_backup_tasks = {}
_backup_tasks_lock = threading.RLock()
_MAX_BACKUP_TASKS = 1000


def _task_snapshot(task):
    return deepcopy(task)


def _prune_backup_tasks():
    """Bound memory while never evicting a task that is still running."""
    with _backup_tasks_lock:
        overflow = len(_backup_tasks) - _MAX_BACKUP_TASKS
        if overflow <= 0:
            return
        terminal = sorted(
            (item for item in _backup_tasks.values() if item.get("status") in {"success", "failed"}),
            key=lambda item: item.get("finished_at") or "",
        )
        for item in terminal[:overflow]:
            _backup_tasks.pop(item["task_id"], None)


def _verify_api_key():
    """Verify API key from request header"""
    api_key = request.headers.get("X-Agent-API-Key")
    expected_key = current_app.config.get("AGENT_API_KEY", "")
    
    if expected_key and api_key != expected_key:
        return False
    return True


def _require_api_key(f):
    """Decorator to require API key authentication"""
    from functools import wraps
    
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _verify_api_key():
            return error_response("invalid API key", code=401)
        return f(*args, **kwargs)
    return decorated


def _ensure_disk_space(path: str, required_bytes: int = 512 * 1024 * 1024):
    """Ensure sufficient disk space"""
    usage = shutil.disk_usage(path)
    return usage.free >= required_bytes


def _build_mysql_command(instance: dict, output_file: str, tool_path: str, include_result_file: bool = True):
    """Build mysqldump command"""
    command = [
        tool_path,
        f"--host={instance.get('resolved_ip') or instance.get('host_input')}",
        f"--port={instance.get('port')}",
        f"--user={instance.get('username') or ''}",
        "--default-character-set=utf8mb4",
        "--single-transaction",
        "--all-databases",
    ]
    if include_result_file:
        command.append(f"--result-file={output_file}")
    password = instance.get("password")
    if password:
        command.append(f"--password={password}")
    return command


def _build_mongo_command(instance: dict, output_file: str, compress: bool, tool_path: str, archive_to_stdout: bool = False):
    """Build mongodump command"""
    command = [
        tool_path,
        f"--host={instance.get('resolved_ip') or instance.get('host_input')}",
        f"--port={instance.get('port')}",
        "--nsExclude=local.*",
    ]
    if archive_to_stdout:
        command.append("--archive=-")
    else:
        command.append(f"--archive={output_file}")
    
    username = instance.get("username")
    password = instance.get("password")
    if username:
        command.extend(["--username", username])
    if password:
        command.extend(["--password", password])
    
    if compress:
        command.append("--gzip")
    
    return command


def _run_mysqldump_gzip(command, output_file):
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    with gzip.open(output_file, "wb") as gz:
        if proc.stdout:
            shutil.copyfileobj(proc.stdout, gz)
    stderr_data = proc.stderr.read() if proc.stderr else b""
    proc.wait(timeout=86400)
    if proc.returncode != 0:
        stderr_text = stderr_data.decode(errors="replace") if stderr_data else ""
        raise subprocess.CalledProcessError(proc.returncode, command, stderr=stderr_text)


def _run_mysqldump_zstd(command, output_file):
    dump_proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    zstd_proc = subprocess.Popen(
        ["zstd", "-q", "-f", "-T2", "--long=15", "-15", "-o", output_file],
        stdin=dump_proc.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if dump_proc.stdout:
        dump_proc.stdout.close()
    dump_err = dump_proc.stderr.read() if dump_proc.stderr else b""
    _, zstd_err = zstd_proc.communicate()
    dump_ret = dump_proc.wait()
    if dump_proc.stderr:
        dump_proc.stderr.close()

    if dump_ret != 0:
        raise subprocess.CalledProcessError(dump_ret, command, stderr=dump_err.decode(errors="replace"))
    if zstd_proc.returncode != 0:
        raise subprocess.CalledProcessError(zstd_proc.returncode, ["zstd"], stderr=zstd_err.decode(errors="replace"))


def _compress_with_zstd(source_file: str, target_file: str = None, remove_source: bool = False):
    target_file = target_file or f"{source_file}.zst"
    subprocess.run(
        ["zstd", "-f", "-q", source_file, "-o", target_file],
        check=True,
        capture_output=True,
        text=True,
    )
    if remove_source and source_file != target_file and os.path.exists(source_file):
        os.remove(source_file)
    return target_file


def _run_mongodump_zstd(command, output_file):
    dump_proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    zstd_proc = subprocess.Popen(
        ["zstd", "-q", "-f", "-T2", "--long=15", "-15", "-o", output_file],
        stdin=dump_proc.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if dump_proc.stdout:
        dump_proc.stdout.close()
    dump_err = dump_proc.stderr.read() if dump_proc.stderr else b""
    _, zstd_err = zstd_proc.communicate()
    dump_ret = dump_proc.wait()
    if dump_proc.stderr:
        dump_proc.stderr.close()

    if dump_ret != 0:
        raise subprocess.CalledProcessError(dump_ret, command, stderr=dump_err.decode(errors="replace"))
    if zstd_proc.returncode != 0:
        raise subprocess.CalledProcessError(zstd_proc.returncode, ["zstd"], stderr=zstd_err.decode(errors="replace"))


def _normalize_endpoint_url(endpoint_url: str):
    value = (endpoint_url or "").strip()
    if not value:
        return None
    if value.startswith("//"):
        return f"https:{value}"
    parsed = urlsplit(value)
    if parsed.scheme:
        return value
    return f"https://{value}"


def _build_transfer_config():
    from boto3.s3.transfer import TransferConfig

    return TransferConfig(
        multipart_threshold=MULTIPART_CHUNK_SIZE,
        multipart_chunksize=MULTIPART_CHUNK_SIZE,
    )


def _upload_file_to_s3(local_path: str, s3_config: dict):
    if not isinstance(s3_config, dict) or not s3_config.get("enabled"):
        return {"ok": False, "message": "s3 upload disabled"}

    try:
        import boto3
    except Exception:
        return {"ok": False, "message": "boto3 is not installed"}

    bucket = s3_config.get("bucket")
    if not bucket:
        return {"ok": False, "message": "missing s3 bucket"}

    prefix = (s3_config.get("prefix") or "").strip("/")
    key_name = os.path.basename(local_path)
    object_key = f"{prefix}/{key_name}" if prefix else key_name

    client = boto3.client(
        "s3",
        region_name=s3_config.get("region") or None,
        endpoint_url=_normalize_endpoint_url(s3_config.get("endpoint_url")),
        aws_access_key_id=s3_config.get("access_key") or None,
        aws_secret_access_key=s3_config.get("secret_key") or None,
    )
    client.upload_file(local_path, bucket, object_key, Config=_build_transfer_config())
    return {"ok": True, "bucket": bucket, "key": object_key}


def _upload_file_to_us3(local_path: str, s3_config: dict):
    if not isinstance(s3_config, dict) or not s3_config.get("enabled"):
        return {"ok": False, "message": "s3 upload disabled"}
    bucket = s3_config.get("bucket")
    if not bucket:
        return {"ok": False, "message": "missing s3 bucket"}
    prefix = (s3_config.get("prefix") or "").strip("/")
    cli_path = (s3_config.get("us3_cli_path") or "").strip() or "/data/us3cli-linux64"
    if not os.path.exists(cli_path):
        return {"ok": False, "message": f"us3 cli not found: {cli_path}"}
    dest = f"us3://{bucket}/{prefix}" if prefix else f"us3://{bucket}/"
    if not dest.endswith("/"):
        dest = dest + "/"
    try:
        result = subprocess.run([cli_path, "cp", local_path, dest], capture_output=True, text=True, check=True)
        key_name = os.path.basename(local_path)
        object_key = f"{prefix}/{key_name}" if prefix else key_name
        return {"ok": True, "bucket": bucket, "key": object_key, "stdout": result.stdout.strip()}
    except subprocess.CalledProcessError as exc:
        return {"ok": False, "message": exc.stderr or str(exc), "exit_code": exc.returncode}


def _encrypt_backup_file(file_path: str, public_key_pem: str):
    if not public_key_pem:
        return None, None, "public key missing", "public key missing"

    enc_file = f"{file_path}.enc"
    key_bytes = secrets.token_bytes(32)
    iv_bytes = secrets.token_bytes(16)
    key_hex = key_bytes.hex()
    iv_hex = iv_bytes.hex()

    original_size = os.path.getsize(file_path)

    try:
        subprocess.run(
            ["openssl", "enc", "-aes-256-cbc", "-nosalt", "-K", key_hex, "-iv", iv_hex, "-in", file_path, "-out", enc_file],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        return None, None, exc.stderr or str(exc), "encrypt failed"

    header_prefixed_file = f"{enc_file}.tmp"
    with open(header_prefixed_file, "wb") as dst, open(enc_file, "rb") as src:
        dst.write(struct.pack(">Q", original_size))
        shutil.copyfileobj(src, dst)
    os.replace(header_prefixed_file, enc_file)

    with tempfile.NamedTemporaryFile(delete=False) as pub_fp:
        pub_fp.write(public_key_pem.encode())
        pub_fp.flush()
        pub_path = pub_fp.name

    import base64
    try:
        key_iv_data = f"{key_hex}:{iv_hex}".encode()
        encrypted_key_iv = subprocess.run(
            ["openssl", "pkeyutl", "-encrypt", "-pubin", "-inkey", pub_path, "-in", "-"],
            input=key_iv_data,
            capture_output=True,
            check=True,
        ).stdout
        encrypted_key_iv_b64 = base64.b64encode(encrypted_key_iv).decode()
    except subprocess.CalledProcessError as exc:
        return None, None, exc.stderr or str(exc), "encrypt key failed"
    finally:
        try:
            os.remove(pub_path)
        except Exception:
            pass

    with open(enc_file, "ab") as f:
        f.write(b"\n-----BEGIN ENCRYPTED KEY-----\n")
        f.write(encrypted_key_iv_b64.encode())
        f.write(b"\n-----END ENCRYPTED KEY-----\n")

    enc_basename = os.path.basename(enc_file)
    output_basename = os.path.basename(file_path)
    decrypt_cmd = (
        f"python -c \"import base64;from pathlib import Path;d=Path(r'{enc_basename}').read_bytes();"
        "m=b'\\n-----BEGIN ENCRYPTED KEY-----\\n';e=b'\\n-----END ENCRYPTED KEY-----\\n';"
        "i=d.rfind(m);j=d.rfind(e);assert i>8 and j>i,'invalid encrypted file format';"
        "Path('encrypted_payload.bin').write_bytes(d[8:i]);"
        "Path('encrypted_key.bin').write_bytes(base64.b64decode(d[i+len(m):j]))\""
        " && openssl pkeyutl -decrypt -inkey private_key.pem -in encrypted_key.bin -out key_iv.txt"
        " && key=$(cut -d: -f1 key_iv.txt) && iv=$(cut -d: -f2 key_iv.txt)"
        f" && openssl enc -aes-256-cbc -d -nosalt -K $key -iv $iv -in encrypted_payload.bin -out '{output_basename}'"
        " && rm -f key_iv.txt encrypted_key.bin encrypted_payload.bin"
    )

    return enc_file, None, None, decrypt_cmd


def _run_backup(policy: dict, instance: dict, dry_run: bool = False):
    """Execute backup based on policy and instance data"""
    db_type = policy.get("db_type")
    default_tool = "mysqldump" if db_type == "mysql" else "mongodump"
    tool_path = policy.get("tool_path") or current_app.config.get(f"{db_type.upper()}_DUMP_PATH", default_tool)
    
    storage_path = policy.get("storage_path") or os.environ.get("BACKUP_ROOT", "/tmp/backups")
    os.makedirs(storage_path, exist_ok=True)
    
    if not _ensure_disk_space(storage_path):
        return {"ok": False, "message": "insufficient disk space"}
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    instance_name = instance.get("name", "unknown").replace(" ", "_")
    
    compress_method = str(policy.get("compress_method") or "").strip().lower()
    if compress_method not in {"none", "gzip", "zstd"}:
        compress_method = "gzip" if bool(policy.get("compress", True)) else "none"
    compress = compress_method != "none"
    encrypt_cfg = policy.get("encrypt") if isinstance(policy.get("encrypt"), dict) else None
    encrypt_enabled = bool(encrypt_cfg and encrypt_cfg.get("enabled"))

    use_gzip = False
    use_zstd = False
    use_mysql_zstd_pipe = False
    use_zstd_pipe = False
    zstd_source_file = None
    if db_type == "mysql":
        if compress_method == "gzip":
            output_file = os.path.join(storage_path, f"{instance_name}_{timestamp}.sql.gz")
            use_gzip = True
            command = _build_mysql_command(instance, output_file, tool_path, include_result_file=False)
        elif compress_method == "zstd":
            output_file = os.path.join(storage_path, f"{instance_name}_{timestamp}.sql.zst")
            use_mysql_zstd_pipe = True
            command = _build_mysql_command(instance, output_file, tool_path, include_result_file=False)
        else:
            output_file = os.path.join(storage_path, f"{instance_name}_{timestamp}.sql")
            command = _build_mysql_command(instance, output_file, tool_path, include_result_file=True)
    elif db_type == "mongodb":
        if compress_method == "zstd":
            output_file = os.path.join(storage_path, f"{instance_name}_{timestamp}.zst")
            zstd_source_file = None
            use_zstd_pipe = True
            command = _build_mongo_command(instance, output_file, False, tool_path, archive_to_stdout=True)
        else:
            output_file = os.path.join(storage_path, f"{instance_name}_{timestamp}.archive")
            zstd_source_file = None
            command = _build_mongo_command(instance, output_file, compress_method == "gzip", tool_path)
    else:
        return {"ok": False, "message": f"unsupported db_type: {db_type}"}
    
    if dry_run:
        return {
            "ok": True,
            "message": "dry run mode",
            "command": command,
            "output_file": output_file,
        }
    
    try:
        if db_type == "mysql" and use_gzip:
            _run_mysqldump_gzip(command, output_file)
        elif db_type == "mysql" and use_mysql_zstd_pipe:
            _run_mysqldump_zstd(command, output_file)
        elif db_type == "mongodb" and use_zstd_pipe:
            _run_mongodump_zstd(command, output_file)
        else:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=86400,
            )
            if result.returncode != 0:
                return {
                    "ok": False,
                    "message": f"backup failed: {result.stderr}",
                    "command": command,
                }

        if use_zstd:
            output_file = _compress_with_zstd(
                zstd_source_file or output_file,
                target_file=output_file,
                remove_source=True,
            )

        encrypt_info = None
        if encrypt_enabled:
            public_key = (encrypt_cfg.get("public_key") or "").strip() if encrypt_cfg else ""
            enc_file, key_file, enc_err, decrypt_cmd = _encrypt_backup_file(output_file, public_key)
            if enc_err:
                return {"ok": False, "message": f"encrypt failed: {enc_err}", "command": command}
            try:
                os.remove(output_file)
            except Exception:
                pass
            output_file = enc_file
            encrypt_info = {
                "enabled": True,
                "method": "aes-256-cbc+embedded-key",
                "decrypt_cmd": decrypt_cmd,
            }

        s3_result = None
        s3_cfg = policy.get("s3_config")
        if isinstance(s3_cfg, dict) and s3_cfg.get("enabled"):
            upload_mode = str(s3_cfg.get("upload_mode") or "native").strip().lower()
            if upload_mode == "us3":
                s3_result = _upload_file_to_us3(output_file, s3_cfg)
            else:
                s3_result = _upload_file_to_s3(output_file, s3_cfg)
            if not s3_result.get("ok"):
                return {"ok": False, "message": f"s3 upload failed: {s3_result.get('message')}", "command": command, "s3": s3_result}

        file_size = os.path.getsize(output_file) if os.path.exists(output_file) else 0

        return {
            "ok": True,
            "message": "backup completed",
            "command": command,
            "output_file": output_file,
            "file_size": file_size,
            "compress": compress,
            "compress_method": compress_method,
            "encrypt": encrypt_info,
            "s3": s3_result or {"ok": False, "message": "s3 upload disabled"},
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": "backup timeout"}
    except Exception as e:
        return {"ok": False, "message": str(e)}


def _run_backup_task(app, task_id, policy, instance):
    with app.app_context():
        with _backup_tasks_lock:
            task = _backup_tasks.get(task_id)
            if not task:
                return
            task["status"] = "running"
            task["started_at"] = datetime.utcnow().isoformat() + "Z"
        try:
            result = _run_backup(policy, instance, False)
        except Exception as exc:
            logger.exception("backup task crashed: task_id=%s", task_id)
            result = {"ok": False, "message": str(exc)}
        with _backup_tasks_lock:
            task = _backup_tasks.get(task_id)
            if task:
                task["status"] = "success" if result.get("ok") else "failed"
                task["result"] = result
                task["finished_at"] = datetime.utcnow().isoformat() + "Z"
        _prune_backup_tasks()


@bp.route("/instances/probe", methods=["POST"])
@_require_api_key
def probe_database_instance():
    from app.services.instance_probe import probe_instance

    payload = request.get_json(silent=True) or {}
    instance = payload.get("instance")
    if not isinstance(instance, dict):
        return error_response("instance is required", code=400)
    if not instance.get("db_type") or not (instance.get("resolved_ip") or instance.get("host_input")):
        return error_response("instance db_type and host are required", code=400)
    result = probe_instance(instance=instance, password=payload.get("password") or "")
    return ok_response(data=result)


@bp.route("/health", methods=["GET"])
def health_check():
    """健康检查接口 - 无数据库依赖"""
    return ok_response({
        "status": "healthy",
        "version": AGENT_VERSION,
    })


@bp.route("/execute", methods=["POST"])
@_require_api_key
def execute_backup():
    """执行备份任务 - 接收完整的策略和实例数据"""
    payload = request.get_json(silent=True) or {}
    
    policy = payload.get("policy")
    instance = payload.get("instance")
    
    if not policy:
        return error_response("policy is required", code=400)
    if not instance:
        return error_response("instance is required", code=400)
    
    dry_run = payload.get("dry_run", False)

    # Dry runs are cheap and remain synchronous. Real backups are detached from
    # the request so a connection is never held for the backup duration.
    if dry_run:
        result = _run_backup(policy, instance, True)
        status_code = 200 if result.get("ok") else 500
        if result.get("ok"):
            return ok_response(data=result, code=status_code)
        return error_response(result.get("message", "backup failed"), code=status_code, data=result)

    task_id = str(payload.get("task_id") or uuid.uuid4().hex).strip()
    if not task_id or len(task_id) > 128:
        return error_response("invalid task_id", code=400)

    with _backup_tasks_lock:
        existing = _backup_tasks.get(task_id)
        if existing:
            return ok_response(data={"task_id": task_id, "status": existing.get("status")}, code=202)
        _backup_tasks[task_id] = {
            "task_id": task_id,
            "status": "submitted",
            "submitted_at": datetime.utcnow().isoformat() + "Z",
            "started_at": None,
            "finished_at": None,
            "result": None,
        }

    app = current_app._get_current_object()
    worker = threading.Thread(
        target=_run_backup_task,
        args=(app, task_id, deepcopy(policy), deepcopy(instance)),
        daemon=True,
        name=f"backup-{task_id[:12]}",
    )
    worker.start()
    return ok_response(data={"task_id": task_id, "status": "submitted"}, code=202)


@bp.route("/tasks/<task_id>", methods=["GET"])
@_require_api_key
def get_backup_task(task_id):
    with _backup_tasks_lock:
        task = _backup_tasks.get(task_id)
        if not task:
            return error_response("backup task not found", code=404)
        snapshot = _task_snapshot(task)
    return ok_response(data=snapshot)


@bp.route("/tasks/status", methods=["POST"])
@_require_api_key
def get_backup_tasks_status():
    payload = request.get_json(silent=True) or {}
    task_ids = payload.get("task_ids") or []
    if not isinstance(task_ids, list) or len(task_ids) > 500:
        return error_response("task_ids must be a list with at most 500 items", code=400)
    with _backup_tasks_lock:
        tasks = {
            str(task_id): _task_snapshot(_backup_tasks[str(task_id)])
            for task_id in task_ids
            if str(task_id) in _backup_tasks
        }
    missing = [str(task_id) for task_id in task_ids if str(task_id) not in tasks]
    return ok_response(data={"tasks": tasks, "missing": missing})


@bp.route("/files/download", methods=["GET"])
@_require_api_key
def download_backup_file():
    file_path = (request.args.get("path") or "").strip()
    if not file_path:
        return error_response("path is required", code=400)
    if not os.path.isabs(file_path):
        return error_response("path must be absolute", code=400)
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        return error_response("backup file not found", code=404)
    filename = os.path.basename(file_path)
    return send_file(file_path, as_attachment=True, download_name=filename)


@bp.route("/version", methods=["GET"])
def get_version():
    """获取 Agent 版本"""
    return ok_response({"version": AGENT_VERSION})


@bp.route("/tool/verify", methods=["POST"])
@_require_api_key
def verify_tool():
    """验证备份工具是否可用"""
    payload = request.get_json(silent=True) or {}
    tool_path = payload.get("tool_path")
    
    if not tool_path:
        return error_response("tool_path is required", code=400)
    
    if not os.path.exists(tool_path):
        return ok_response(data={"available": False, "message": "tool not found"})
    
    if not os.access(tool_path, os.X_OK):
        return ok_response(data={"available": False, "message": "tool not executable"})
    
    try:
        result = subprocess.run([tool_path, "--version"], capture_output=True, text=True, timeout=5)
        version = result.stdout or result.stderr or "unknown"
        return ok_response(data={"available": True, "version": version.strip()})
    except Exception as e:
        return ok_response(data={"available": False, "message": str(e)})
