import requests
from flask import current_app
from typing import Optional

from app.models.backup_agent import BackupAgent
from app.models.backup import BackupPolicy
from app.models.backup_key import BackupKey
from app.models.s3_storage_config import S3StorageConfig
from app.models.db_asset import DatabaseInstance
from app.models.backup_tool_config import BackupToolConfig
from app.utils.crypto import decrypt_secret


class BackupAgentError(Exception):
    """Backup agent error"""
    pass


def get_agent_url(agent_id: int = None) -> str:
    """
    Get the backup agent URL.

    Args:
        agent_id: Specific agent ID. If None, uses default agent or config fallback.

    Returns:
        Agent URL string
    """
    if agent_id:
        agent = BackupAgent.query.get(agent_id)
        if agent and agent.enabled:
            return agent.url
        elif agent:
            raise BackupAgentError(f"Agent {agent_id} is disabled")

    default_agent = BackupAgent.query.filter_by(is_default=True, enabled=True).first()
    if default_agent:
        return default_agent.url

    return current_app.config.get("BACKUP_AGENT_URL", "http://localhost:5001")


def get_agent_api_key(agent_id: int = None) -> str:
    """Get the API key for the agent"""
    if agent_id:
        agent = BackupAgent.query.get(agent_id)
        if agent:
            return agent.api_key or ""
    
    default_agent = BackupAgent.query.filter_by(is_default=True, enabled=True).first()
    if default_agent:
        return default_agent.api_key or ""
    
    return ""


def is_agent_enabled() -> bool:
    """Check if remote agent is enabled"""
    if BackupAgent.query.filter_by(enabled=True).count() > 0:
        return True
    return current_app.config.get("ENABLE_REMOTE_AGENT", False)


def get_agent_by_id(agent_id: int) -> Optional[BackupAgent]:
    """Get agent by ID"""
    return BackupAgent.query.get(agent_id)


def probe_instance_on_agent(instance, password):
    """Collect an instance snapshot from the agent explicitly bound to the asset."""
    agent_id = getattr(instance, "probe_agent_id", None)
    if not agent_id:
        return {"ok": False, "error": "probe agent is not configured"}
    try:
        runtime_settings_supplied = hasattr(instance, "probe_agent_url")
        url = getattr(instance, "probe_agent_url", None)
        api_key = getattr(instance, "probe_agent_api_key", None)
        timeout = getattr(instance, "probe_timeout_seconds", None)
        if not url:
            if runtime_settings_supplied:
                return {"ok": False, "error": "probe agent is unavailable or disabled"}
            url = get_agent_url(agent_id)
        if api_key is None:
            api_key = get_agent_api_key(agent_id)
        if timeout is None:
            timeout = float(current_app.config.get("MONITOR_COLLECT_TIMEOUT_SECONDS", 8))
        response = requests.post(
            f"{url.rstrip('/')}/api/agent/instances/probe",
            json={
                "instance": {
                    "id": getattr(instance, "id", None),
                    "db_type": getattr(instance, "db_type", None),
                    "host_input": getattr(instance, "host_input", None),
                    "resolved_ip": getattr(instance, "resolved_ip", None),
                    "port": getattr(instance, "port", None),
                    "username": getattr(instance, "username", None),
                    "extra_json": getattr(instance, "extra_json", None),
                },
                "password": password or "",
            },
            headers={"X-Agent-API-Key": api_key},
            timeout=float(timeout),
        )
        body = response.json() if response.content else {}
        if response.status_code >= 400:
            return {"ok": False, "error": body.get("message") or f"agent returned status {response.status_code}"}
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            return {"ok": False, "error": "invalid probe response from agent"}
        data.setdefault("probe_source", "agent")
        data.setdefault("probe_agent_id", agent_id)
        return data
    except requests.Timeout:
        return {"ok": False, "error": "agent probe timeout"}
    except Exception as exc:
        return {"ok": False, "error": f"agent probe failed: {exc}"}

def fetch_postgresql_metadata_on_agent(instance, password, agent_id, database=None):
    url = get_agent_url(agent_id)
    api_key = get_agent_api_key(agent_id)
    headers = {"X-Agent-API-Key": api_key} if api_key else {}
    response = requests.post(
        f"{url.rstrip('/')}/api/agent/postgresql/metadata",
        json={
            "instance": {
                "host_input": instance.host_input,
                "resolved_ip": instance.resolved_ip,
                "port": instance.port,
                "username": instance.username,
                "extra_json": instance.extra_json if isinstance(instance.extra_json, dict) else {},
                "password": password or "",
            },
            "database": database,
        },
        headers=headers,
        timeout=(5, 15),
    )
    body = response.json() if response.content else {}
    if response.status_code >= 400:
        raise BackupAgentError(body.get("message") or f"Agent metadata error({response.status_code})")
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, list):
        raise BackupAgentError("invalid postgresql metadata response")
    return data


def _resolve_encrypt_public_key(encrypt_cfg: dict) -> str:
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


def _mongo_auth_database(instance: DatabaseInstance) -> str:
    """Read MongoDB auth DB from the managed asset connection settings."""
    extra = instance.extra_json if isinstance(instance.extra_json, dict) else {}
    return str(extra.get("auth_source") or extra.get("auth_db") or "admin").strip() or "admin"


def _build_payload_from_policy(policy: BackupPolicy, instance: DatabaseInstance) -> dict:
    """Build payload from policy and instance data"""
    tool_config = None
    if policy.backup_tool_config_id:
        tool_config = BackupToolConfig.query.get(policy.backup_tool_config_id)
    
    password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else ""
    
    encrypt_cfg = (policy.extra_json or {}).get("encrypt") if isinstance(policy.extra_json, dict) else None
    encrypt_payload = None
    if isinstance(encrypt_cfg, dict):
        encrypt_payload = dict(encrypt_cfg)
        encrypt_payload["public_key"] = _resolve_encrypt_public_key(encrypt_cfg)

    compress_method = (policy.extra_json or {}).get("compress_method") if isinstance(policy.extra_json, dict) else None
    allowed_methods = {"default", "gzip", "lz4", "zstd", "none"} if policy.db_type == "postgresql" else {"none", "gzip", "zstd"}
    if compress_method not in allowed_methods:
        compress_method = ("default" if policy.compress else "none") if policy.db_type == "postgresql" else ("gzip" if policy.compress else "none")

    mongo_backup = dict((policy.extra_json or {}).get("mongo_backup") or {"mode": "full", "exclusions": []})
    if policy.db_type == "mongodb":
        # The remote agent needs the asset-derived value, not a policy form field.
        mongo_backup["auth_database"] = _mongo_auth_database(instance)

    policy_data = {
        "db_type": policy.db_type,
        "tool_path": tool_config.tool_path if tool_config else policy.tool_name,
        "storage_path": policy.storage_path or "/tmp/backups",
        "compress": compress_method != "none",
        "compress_method": compress_method,
        "encrypt": encrypt_payload,
        "mongo_backup": mongo_backup,
        "postgresql_backup": dict((policy.extra_json or {}).get("postgresql_backup") or {}),
    }
    if policy.s3_storage_config_id and _is_policy_s3_upload_enabled(policy):
        s3_config = S3StorageConfig.query.get(policy.s3_storage_config_id)
        if s3_config and s3_config.enabled:
            resolved_s3_config = s3_config.to_s3_config()
            resolved_s3_config.update(_resolve_s3_upload_options(policy))
            policy_data["s3_config"] = resolved_s3_config
    
    instance_data = {
        "id": instance.id,
        "name": instance.name,
        "host_input": instance.host_input,
        "resolved_ip": instance.resolved_ip,
        "port": instance.port,
        "username": instance.username,
        "password": password,
        "extra_json": instance.extra_json if isinstance(instance.extra_json, dict) else {},
    }
    
    return {
        "policy": policy_data,
        "instance": instance_data,
    }


def execute_backup_on_agent(
    policy_id: int,
    agent_id: int = None,
    dry_run: bool = False,
    task_id: str = None,
) -> dict:
    """
    Call remote agent to execute backup

    Args:
        policy_id: Backup policy ID
        agent_id: Specific agent ID to use. If None, uses policy's agent or default.
        dry_run: If True, only return the command without executing

    Returns:
        dict with execution result

    Raises:
        BackupAgentError: If the call fails
    """
    if not is_agent_enabled():
        raise BackupAgentError("Remote agent is not enabled")

    policy = BackupPolicy.query.get(policy_id)
    if not policy:
        raise BackupAgentError(f"Policy {policy_id} not found")
    
    instance = DatabaseInstance.query.get(policy.target_id)
    if not instance:
        raise BackupAgentError(f"Instance {policy.target_id} not found")
    
    if agent_id is None:
        agent_id = policy.backup_agent_id
    
    url = get_agent_url(agent_id)
    api_key = get_agent_api_key(agent_id)
    execute_url = f"{url.rstrip('/')}/api/agent/execute"
    
    payload = _build_payload_from_policy(policy, instance)
    payload["dry_run"] = dry_run
    if task_id:
        payload["task_id"] = task_id

    headers = {
        "Content-Type": "application/json",
    }
    if api_key:
        headers["X-Agent-API-Key"] = api_key

    try:
        response = requests.post(execute_url, json=payload, headers=headers, timeout=(5, 15))
        try:
            response_data = response.json()
        except Exception:
            response_data = None

        if response.status_code >= 400:
            agent_message = ""
            if isinstance(response_data, dict):
                agent_message = (
                    response_data.get("message")
                    or (response_data.get("data") or {}).get("message")
                    or ""
                )
            if not agent_message:
                agent_message = (response.text or "").strip()[:500] or f"HTTP {response.status_code}"
            raise BackupAgentError(f"Agent error({response.status_code}): {agent_message}")

        if isinstance(response_data, dict):
            return response_data
        raise BackupAgentError("Agent returned invalid JSON response")
    except requests.exceptions.ConnectionError as e:
        raise BackupAgentError(f"Failed to connect to agent: {str(e)}")
    except requests.exceptions.Timeout as e:
        raise BackupAgentError(f"Agent request timeout: {str(e)}")
    except Exception as e:
        if isinstance(e, BackupAgentError):
            raise
        raise BackupAgentError(f"Unexpected error: {str(e)}")


def get_backup_tasks_on_agent(agent_id: int, task_ids: list) -> dict:
    """Fetch multiple in-memory task results with one short request."""
    if not task_ids:
        return {"tasks": {}, "missing": []}
    url = get_agent_url(agent_id)
    api_key = get_agent_api_key(agent_id)
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-Agent-API-Key"] = api_key
    try:
        response = requests.post(
            f"{url.rstrip('/')}/api/agent/tasks/status",
            json={"task_ids": task_ids},
            headers=headers,
            timeout=(3, 8),
        )
        response_data = response.json()
        if response.status_code >= 400 or not isinstance(response_data, dict):
            message = response_data.get("message") if isinstance(response_data, dict) else response.text
            raise BackupAgentError(f"Agent task query error({response.status_code}): {message}")
        return response_data.get("data") or {"tasks": {}, "missing": []}
    except requests.exceptions.ConnectionError as exc:
        raise BackupAgentError(f"Failed to connect to agent: {exc}")
    except requests.exceptions.Timeout as exc:
        raise BackupAgentError(f"Agent task query timeout: {exc}")
    except BackupAgentError:
        raise
    except Exception as exc:
        raise BackupAgentError(f"Unexpected task query error: {exc}")


def cancel_backup_on_agent(agent_id: int, task_id: str) -> dict:
    url, api_key = get_agent_url(agent_id), get_agent_api_key(agent_id)
    headers = {"X-Agent-API-Key": api_key} if api_key else {}
    try:
        response = requests.post(f"{url.rstrip('/')}/api/agent/tasks/{task_id}/cancel", headers=headers, timeout=(3, 15))
        data = response.json()
        if response.status_code >= 400: raise BackupAgentError(data.get("message") or f"Agent cancel error({response.status_code})")
        return data.get("data") or {}
    except requests.exceptions.RequestException as exc:
        raise BackupAgentError(f"Agent cancel request failed: {exc}")


def check_agent_health(agent_id: int = None) -> dict:
    """Check agent health status"""
    url = get_agent_url(agent_id)
    api_key = get_agent_api_key(agent_id)
    health_url = f"{url.rstrip('/')}/api/agent/health"
    
    headers = {}
    if api_key:
        headers["X-Agent-API-Key"] = api_key
    
    try:
        response = requests.get(health_url, headers=headers, timeout=5)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {
            "ok": False,
            "message": str(e),
        }


def download_backup_file_from_agent(agent_id: int, file_path: str):
    if not file_path:
        raise BackupAgentError("backup file path is empty")
    url = get_agent_url(agent_id)
    api_key = get_agent_api_key(agent_id)
    download_url = f"{url.rstrip('/')}/api/agent/files/download"

    headers = {}
    if api_key:
        headers["X-Agent-API-Key"] = api_key

    try:
        response = requests.get(
            download_url,
            params={"path": file_path},
            headers=headers,
            stream=True,
            timeout=(10, 2592000),
        )
        if response.status_code >= 400:
            agent_message = ""
            try:
                response_data = response.json()
            except Exception:
                response_data = None
            if isinstance(response_data, dict):
                agent_message = (
                    response_data.get("message")
                    or (response_data.get("data") or {}).get("message")
                    or ""
                )
            if not agent_message:
                agent_message = (response.text or "").strip()[:500] or f"HTTP {response.status_code}"
            response.close()
            raise BackupAgentError(f"Agent error({response.status_code}): {agent_message}")
        return response
    except requests.exceptions.ConnectionError as e:
        raise BackupAgentError(f"Failed to connect to agent: {str(e)}")
    except requests.exceptions.Timeout as e:
        raise BackupAgentError(f"Agent request timeout: {str(e)}")
    except Exception as e:
        if isinstance(e, BackupAgentError):
            raise
        raise BackupAgentError(f"Unexpected error: {str(e)}")
