import requests

from app.models.backup_agent import BackupAgent
from app.utils.crypto import decrypt_secret


class SqlReleaseAgentError(RuntimeError):
    def __init__(self, message, result=None):
        super().__init__(message)
        self.result = result if isinstance(result, dict) else None


def execute_sql_release_on_agent(instance, database, statements, db_type, timeout_seconds=86400, seed_nodes=None):
    agent_id = getattr(instance, "probe_agent_id", None)
    agent = BackupAgent.query.get(agent_id) if agent_id else None
    if not agent or not agent.enabled:
        raise SqlReleaseAgentError("实例绑定的 Agent 不存在或已停用")

    password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else ""
    extra = instance.extra_json if isinstance(instance.extra_json, dict) else {}
    payload = {
        "db_type": db_type,
        "database": database,
        "statements": statements,
        "timeout_seconds": timeout_seconds,
        "instance": {
            "id": instance.id,
            "host_input": instance.host_input,
            "resolved_ip": instance.resolved_ip,
            "port": instance.port,
            "username": instance.username,
            "password": password,
            "extra_json": extra,
        },
    }
    if db_type == "mongodb":
        payload["instance"]["seed_nodes"] = seed_nodes or extra.get("seed_nodes") or None
    try:
        response = requests.post(
            f"{agent.url.rstrip('/')}/api/agent/sql-releases/execute",
            json=payload,
            headers={"X-Agent-API-Key": agent.api_key or ""},
            timeout=(5, min(max(int(timeout_seconds), 1), 86400) + 30),
        )
    except requests.Timeout as exc:
        raise SqlReleaseAgentError("Agent SQL 执行超时，执行结果未知，请先核对数据库后再重试") from exc
    except requests.RequestException as exc:
        raise SqlReleaseAgentError(f"无法连接实例绑定的 Agent：{exc}") from exc

    try:
        body = response.json() if response.content else {}
    except ValueError as exc:
        raise SqlReleaseAgentError("Agent 返回了无法解析的响应") from exc
    if response.status_code >= 400:
        raise SqlReleaseAgentError(
            body.get("message") or f"Agent SQL 执行失败（HTTP {response.status_code}）",
            body.get("data") if isinstance(body, dict) else None,
        )
    data = body.get("data") if isinstance(body, dict) else None
    if not isinstance(data, dict) or not isinstance(data.get("statements"), list):
        raise SqlReleaseAgentError("Agent SQL 执行响应缺少逐条结果")
    data.setdefault("execution_source", "agent")
    data.setdefault("agent_id", agent.id)
    data.setdefault("agent_name", agent.name)
    return data
