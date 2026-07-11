import os
import shutil
import subprocess
import tempfile
import threading
import secrets
import struct
import tarfile
from datetime import datetime, timedelta
from pathlib import Path

BACKUP_TIMEOUT_SECONDS = 2592000
_running_backup_processes = {}
_running_backup_lock = threading.RLock()

def _run_registered_process(command, log_id):
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    with _running_backup_lock:
        _running_backup_processes[log_id] = proc
    try:
        stdout, stderr = proc.communicate(timeout=BACKUP_TIMEOUT_SECONDS)
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, command, output=stdout, stderr=stderr)
    finally:
        with _running_backup_lock:
            _running_backup_processes.pop(log_id, None)

def cancel_local_backup(log_id):
    with _running_backup_lock:
        proc = _running_backup_processes.get(log_id)
    if not proc or proc.poll() is not None:
        return False
    proc.terminate()
    return True


from flask import current_app

from app.extensions import db
from app.models.backup import BackupLog, BackupPolicy
from app.models.backup_key import BackupKey
from app.models.db_asset import DatabaseInstance
from app.models.s3_storage_config import S3StorageConfig
from app.services.notifier import notify_backup_failure
from app.services.s3_storage import upload_file_to_s3, upload_file_to_us3
from app.utils.crypto import decrypt_secret


def _ensure_disk_space(path: str, required_bytes: int = 512 * 1024 * 1024):
    usage = shutil.disk_usage(path)
    return usage.free >= required_bytes


def _resolve_target_instance(policy: BackupPolicy):
    if policy.target_type != "instance":
        return None, "cluster backup execution is not implemented yet"

    instance = DatabaseInstance.query.get(policy.target_id)
    if not instance:
        return None, "target instance not found"
    return instance, None


def _get_tool_path(policy):
    """获取备份工具路径，优先使用已配置的工具路径"""
    if policy.backup_tool_config_id and policy.backup_tool_config:
        return policy.backup_tool_config.tool_path
    if policy.db_type == "mysql":
        return current_app.config.get('MYSQLDUMP_PATH', 'mysqldump')
    elif policy.db_type == "mongodb":
        return current_app.config.get('MONGODUMP_PATH', 'mongodump')
    return None


def _build_mysql_command(instance, password, output_file, tool_path, include_result_file=True):
    command = [
        tool_path,
        f"--host={instance.resolved_ip or instance.host_input}",
        f"--port={instance.port}",
        f"--user={instance.username or ''}",
        "--default-character-set=utf8mb4",
        "--single-transaction",
        "--all-databases",
    ]
    if include_result_file:
        command.append(f"--result-file={output_file}")
    if password:
        command.append(f"--password={password}")
    return command


def _run_mysqldump_gzip(command, output_file):
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout_data = b""
    stderr_data = b""
    try:
        import gzip

        with gzip.open(output_file, "wb") as gz:
            if proc.stdout:
                for chunk in iter(lambda: proc.stdout.read(1024 * 1024), b""):
                    gz.write(chunk)
        if proc.stderr:
            stderr_data = proc.stderr.read()
        proc.wait()
    finally:
        if proc.stdout:
            proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()
    if proc.returncode != 0:
        stderr_text = stderr_data.decode(errors="replace") if stderr_data else ""
        raise subprocess.CalledProcessError(proc.returncode, command, output=stdout_data, stderr=stderr_text)


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


def _build_mongo_command(instance, password, output_file, compress, tool_path, archive_to_stdout=False):
    command = [
        tool_path,
        f"--host={instance.resolved_ip or instance.host_input}",
        f"--port={instance.port}",
    ]
    if archive_to_stdout:
        command.append("--archive=-")
    else:
        command.append(f"--archive={output_file}")

    if instance.username:
        command.extend(["--username", instance.username])
    if password:
        command.extend(["--password", password])

    if compress:
        command.append("--gzip")

    return command


def _build_partial_mongo_commands(instance, password, output_dir, tool_path, databases, exclusions):
    whole = {row["database"] for row in exclusions if not row.get("collection")}
    by_database = {}
    for row in exclusions:
        if row.get("collection"):
            by_database.setdefault(row["database"], []).append(row["collection"])
    commands, skipped = [], []
    for database in databases:
        if database == "local" or database in whole:
            skipped.append(database)
            continue
        command = [tool_path, f"--host={instance.resolved_ip or instance.host_input}", f"--port={instance.port}", f"--db={database}", f"--out={output_dir}"]
        if instance.username: command.extend(["--username", instance.username])
        if password: command.extend(["--password", password])
        for collection in by_database.get(database, []): command.append(f"--excludeCollection={collection}")
        commands.append(command)
    return commands, skipped


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
    zstd_out, zstd_err = zstd_proc.communicate()
    dump_ret = dump_proc.wait()
    if dump_proc.stderr:
        dump_proc.stderr.close()

    if dump_ret != 0:
        raise subprocess.CalledProcessError(dump_ret, command, stderr=dump_err.decode(errors="replace"))
    if zstd_proc.returncode != 0:
        raise subprocess.CalledProcessError(zstd_proc.returncode, ["zstd"], stderr=zstd_err.decode(errors="replace"))


def _should_notify_failure(policy: BackupPolicy):
    extra = policy.extra_json or {}
    notify_cfg = extra.get("notify") or {}
    return bool(notify_cfg.get("on_failure", True))


def _notify_failure(policy: BackupPolicy, instance, error_message, command=None):
    if not _should_notify_failure(policy):
        return {"ok": False, "message": "notify disabled"}
    try:
        return notify_backup_failure(policy=policy, instance=instance, error_message=error_message, command=command)
    except Exception as exc:
        return {"ok": False, "message": str(exc)}


def _cleanup_retention(policy: BackupPolicy):
    if policy.retain_days <= 0:
        return 0

    deleted = 0
    cutoff = datetime.utcnow() - timedelta(days=policy.retain_days)
    old_logs = BackupLog.query.filter(
        BackupLog.policy_id == policy.id,
        BackupLog.status == "success",
        BackupLog.finished_at.isnot(None),
        BackupLog.finished_at < cutoff,
    ).all()

    for item in old_logs:
        file_path = item.file_path
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                deleted += 1
                extra = dict(item.extra_json or {})
                extra["local_file_deleted"] = True
                extra["deleted_at"] = datetime.utcnow().isoformat()
                item.extra_json = extra
            except Exception:
                continue
        extra = dict(item.extra_json or {})
        encrypt_cfg = extra.get("encrypt") if isinstance(extra, dict) else None
        key_path = encrypt_cfg.get("key_file") if isinstance(encrypt_cfg, dict) else None
        if key_path and os.path.exists(key_path):
            try:
                os.remove(key_path)
            except Exception:
                pass

    if deleted:
        db.session.commit()
    return deleted


def _build_failed_result(policy, instance, message, command=None, log=None):
    if log is None:
        log = BackupLog(
            policy_id=policy.id,
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
            status="failed",
            error_message=message,
            extra_json={"command": command or []},
        )
        db.session.add(log)
    else:
        log.status = "failed"
        log.finished_at = datetime.utcnow()
        log.error_message = message
        extra = dict(log.extra_json or {})
        extra["command"] = command or []
        log.extra_json = extra

    notify_result = _notify_failure(policy=policy, instance=instance, error_message=message, command=command)
    extra = dict(log.extra_json or {})
    extra["notify"] = notify_result
    log.extra_json = extra

    db.session.commit()
    return {"ok": False, "message": message, "command": command or [], "backup_log_id": log.id}


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


def _resolve_encrypt_public_key(encrypt_cfg: dict):
    public_key = (encrypt_cfg.get("public_key") or "").strip()
    if public_key:
        return public_key
    key_id = encrypt_cfg.get("key_id")
    if key_id in (None, ""):
        return ""
    try:
        key_id = int(key_id)
    except Exception:
        return ""
    key = BackupKey.query.get(key_id)
    if not key:
        return ""
    return (key.public_key or "").strip()


def _is_policy_s3_upload_enabled(policy: BackupPolicy) -> bool:
    extra = policy.extra_json if isinstance(policy.extra_json, dict) else {}
    s3_cfg = extra.get("s3")
    if isinstance(s3_cfg, dict) and "enabled" in s3_cfg:
        return bool(s3_cfg.get("enabled"))
    return True


def _resolve_s3_upload_options(policy: BackupPolicy) -> dict:
    extra = policy.extra_json if isinstance(policy.extra_json, dict) else {}
    s3_cfg = extra.get("s3") if isinstance(extra.get("s3"), dict) else {}
    upload_mode = str(s3_cfg.get("upload_mode") or "native").strip().lower()
    if upload_mode not in {"native", "us3"}:
        upload_mode = "native"
    return {
        "upload_mode": upload_mode,
        "us3_cli_path": (s3_cfg.get("us3_cli_path") or "").strip() or "/data/us3cli-linux64",
    }


def run_backup_policy(policy_id: int, dry_run: bool = False):
    policy = BackupPolicy.query.get(policy_id)
    if not policy:
        return {"ok": False, "message": "policy not found"}
    if not policy.enabled:
        return {"ok": False, "message": "policy disabled"}

    if not os.path.isdir(policy.storage_path):
        return _build_failed_result(policy, None, "storage path not found")

    if not _ensure_disk_space(policy.storage_path):
        return _build_failed_result(policy, None, "insufficient disk space")

    instance, err = _resolve_target_instance(policy)
    if err:
        return _build_failed_result(policy, None, err)

    password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else ""
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")

    tool_path = _get_tool_path(policy)
    if not tool_path:
        return _build_failed_result(policy, instance, f"无法确定备份工具路径，db_type: {policy.db_type}")

    compress_method = (policy.extra_json or {}).get("compress_method") if isinstance(policy.extra_json, dict) else None
    if compress_method not in {"none", "gzip", "zstd"}:
        compress_method = "gzip" if policy.compress else "none"
    use_gzip = False
    use_zstd = False
    use_mysql_zstd_pipe = False
    use_zstd_pipe = False
    use_partial_mongo = False
    partial_temp_dir = None
    zstd_source_file = None
    if policy.db_type == "mysql":
        if compress_method == "gzip":
            filename = f"mysql_{instance.id}_{timestamp}.sql.gz"
            use_gzip = True
            command = _build_mysql_command(instance, password, None, tool_path, include_result_file=False)
        elif compress_method == "zstd":
            filename = f"mysql_{instance.id}_{timestamp}.sql.zst"
            use_mysql_zstd_pipe = True
            command = _build_mysql_command(instance, password, None, tool_path, include_result_file=False)
        else:
            filename = f"mysql_{instance.id}_{timestamp}.sql"
            command = _build_mysql_command(instance, password, str(Path(policy.storage_path) / filename), tool_path)
    elif policy.db_type == "mongodb":
        mongo_cfg = (policy.extra_json or {}).get("mongo_backup") if isinstance(policy.extra_json, dict) else {}
        if isinstance(mongo_cfg, dict) and mongo_cfg.get("mode") == "partial":
            from pymongo import MongoClient
            options = {"serverSelectionTimeoutMS": 10000}
            if instance.username: options["username"] = instance.username
            if password: options["password"] = password
            client = MongoClient(instance.resolved_ip or instance.host_input, instance.port, **options)
            try: databases = client.list_database_names()
            finally: client.close()
            partial_temp_dir = tempfile.mkdtemp(prefix=f"mongodb_{instance.id}_{timestamp}_", dir=policy.storage_path)
            command, skipped_databases = _build_partial_mongo_commands(instance, password, partial_temp_dir, tool_path, databases, mongo_cfg.get("exclusions") or [])
            use_partial_mongo = True
            suffix = ".tar.gz" if compress_method == "gzip" else (".tar.zst" if compress_method == "zstd" else ".tar")
            filename = f"mongodb_{instance.id}_{timestamp}{suffix}"
        elif compress_method == "zstd":
            filename = f"mongodb_{instance.id}_{timestamp}.zst"
            use_zstd_pipe = True
            command = _build_mongo_command(instance, password, None, False, tool_path, archive_to_stdout=True)
        else:
            filename = f"mongodb_{instance.id}_{timestamp}.archive"
            command = _build_mongo_command(instance, password, str(Path(policy.storage_path) / filename), compress_method == "gzip", tool_path)
    else:
        return _build_failed_result(policy, instance, f"unsupported db_type: {policy.db_type}")

    output_file = str(Path(policy.storage_path) / filename)

    if dry_run:
        return {"ok": True, "message": "dry run", "command": command, "output_file": output_file}

    log = BackupLog(
        policy_id=policy.id,
        started_at=datetime.utcnow(),
        status="running",
        extra_json={"command": command},
    )
    db.session.add(log)
    db.session.commit()

    try:
        if use_partial_mongo:
            for partial_command in command: _run_registered_process(partial_command, log.id)
            if compress_method == "gzip":
                with tarfile.open(output_file, "w:gz") as archive: archive.add(partial_temp_dir, arcname="dump")
            elif compress_method == "zstd":
                tar_source = output_file[:-4]
                with tarfile.open(tar_source, "w") as archive: archive.add(partial_temp_dir, arcname="dump")
                _compress_with_zstd(tar_source, output_file, remove_source=True)
            else:
                with tarfile.open(output_file, "w") as archive: archive.add(partial_temp_dir, arcname="dump")
            shutil.rmtree(partial_temp_dir, ignore_errors=True)
        elif policy.db_type == "mysql" and use_gzip:
            _run_mysqldump_gzip(command, output_file)
        elif policy.db_type == "mysql" and use_mysql_zstd_pipe:
            _run_mysqldump_zstd(command, output_file)
        elif policy.db_type == "mongodb" and use_zstd_pipe:
            _run_mongodump_zstd(command, output_file)
        else:
            _run_registered_process(command, log.id)

        extra = dict(log.extra_json or {})
        extra["compress"] = compress_method != "none"
        extra["compress_method"] = compress_method

        if use_zstd:
            output_file = _compress_with_zstd(
                zstd_source_file or output_file,
                target_file=output_file,
                remove_source=True,
            )

        encrypt_cfg = (policy.extra_json or {}).get("encrypt") if isinstance(policy.extra_json, dict) else None
        if isinstance(encrypt_cfg, dict) and encrypt_cfg.get("enabled"):
            public_key = _resolve_encrypt_public_key(encrypt_cfg)
            enc_file, key_file, enc_err, decrypt_cmd = _encrypt_backup_file(output_file, public_key)
            if enc_err:
                return _build_failed_result(policy, instance, f"encrypt failed: {enc_err}", command, log=log)
            try:
                os.remove(output_file)
            except Exception:
                pass
            output_file = enc_file
            extra["encrypt"] = {
                "enabled": True,
                "method": "aes-256-cbc+embedded-key",
                "decrypt_cmd": decrypt_cmd,
            }

        file_size = os.path.getsize(output_file) if os.path.exists(output_file) else 0
        log.status = "success"
        log.finished_at = datetime.utcnow()
        log.file_path = output_file
        log.size_bytes = file_size

        s3_result = None
        if policy.s3_storage_config_id and _is_policy_s3_upload_enabled(policy):
            s3_config = S3StorageConfig.query.get(policy.s3_storage_config_id)
            if s3_config and s3_config.enabled:
                resolved_s3_config = s3_config.to_s3_config()
                resolved_s3_config.update(_resolve_s3_upload_options(policy))
                if resolved_s3_config.get("upload_mode") == "us3":
                    s3_result = upload_file_to_us3(output_file, resolved_s3_config)
                else:
                    s3_result = upload_file_to_s3(output_file, resolved_s3_config)
                if not s3_result.get("ok"):
                    extra["s3"] = s3_result
                    log.extra_json = extra
                    return _build_failed_result(policy, instance, f"s3 upload failed: {s3_result.get('message')}", command, log=log)

        retention_deleted = _cleanup_retention(policy)

        extra["s3"] = s3_result or {"ok": False, "message": "s3 upload disabled"}
        extra["retention_deleted"] = retention_deleted
        log.extra_json = extra
        db.session.commit()

        return {
            "ok": True,
            "message": "backup success",
            "backup_log_id": log.id,
            "output_file": output_file,
            "size_bytes": file_size,
            "command": command,
            "s3": s3_result,
            "retention_deleted": retention_deleted,
        }
    except subprocess.CalledProcessError as exc:
        return _build_failed_result(policy, instance, f"backup command failed: {exc.stderr or str(exc)}", command, log=log)
    except Exception as exc:
        return _build_failed_result(policy, instance, str(exc), command, log=log)
