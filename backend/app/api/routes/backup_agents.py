import requests
import secrets
from flask import Blueprint, request

from app.api.routes.common import active_user_required, admin_required
from app.extensions import db
from app.models.backup_agent import BackupAgent
from app.models.db_asset import DatabaseInstance
from app.services.audit import log_audit
from app.services.remote_backup_service import checkpoint_remote_backup, recoverable_remote_backups
from app.utils.response import error_response, ok_response

bp = Blueprint("backup_agents", __name__, url_prefix="/backup-agents")


def _agent_callback_authorized(agent):
    supplied = request.headers.get("X-Agent-API-Key") or ""
    expected = agent.api_key or ""
    return secrets.compare_digest(str(supplied), str(expected))


@bp.post("/<int:agent_id>/tasks/checkpoint")
def checkpoint_agent_backup_task(agent_id):
    """Optional callback used only by restart-recovery capable Agents."""
    agent = BackupAgent.query.get_or_404(agent_id)
    if not agent.enabled or not _agent_callback_authorized(agent):
        return error_response("invalid Agent API key", code=401)
    payload = request.get_json(silent=True) or {}
    log = checkpoint_remote_backup(agent_id, payload)
    if not log:
        return error_response("running backup task not found", code=404)
    return ok_response(data={"task_id": payload.get("task_id"), "backup_log_id": log.id})


@bp.post("/<int:agent_id>/tasks/recover")
def recover_agent_backup_tasks(agent_id):
    """Let an upgraded Agent fetch only tasks it previously checkpointed."""
    agent = BackupAgent.query.get_or_404(agent_id)
    if not agent.enabled or not _agent_callback_authorized(agent):
        return error_response("invalid Agent API key", code=401)
    return ok_response(data={"tasks": recoverable_remote_backups(agent_id)})


@bp.route("", methods=["GET"])
@active_user_required
def list_agents():
    """获取 Agent 列表"""
    enabled = request.args.get("enabled")
    query = BackupAgent.query
    if enabled is not None:
        query = query.filter_by(enabled=(enabled.lower() == "true"))

    items = query.order_by(BackupAgent.is_default.desc(), BackupAgent.id.desc()).all()
    return ok_response(data=[item.to_dict() for item in items])


@bp.route("/<int:agent_id>", methods=["GET"])
@active_user_required
def get_agent(agent_id):
    """获取 Agent 详情"""
    agent = BackupAgent.query.get_or_404(agent_id)
    return ok_response(data=agent.to_dict())


@bp.route("", methods=["POST"])
@admin_required
def create_agent():
    """创建 Agent"""
    payload = request.get_json(silent=True) or {}

    name = (payload.get("name") or "").strip()
    url = (payload.get("url") or "").strip()

    if not name:
        return error_response("name is required", code=400)
    if not url:
        return error_response("url is required", code=400)

    # 验证 URL 格式
    if not url.startswith(("http://", "https://")):
        return error_response("url must start with http:// or https://", code=400)

    # 检查名称是否已存在
    if BackupAgent.query.filter_by(name=name).first():
        return error_response("name already exists", code=400)

    # 如果设置为默认，则取消其他默认
    is_default = payload.get("is_default", False)
    if is_default:
        BackupAgent.query.update({"is_default": False})

    agent = BackupAgent(
        name=name,
        url=url,
        api_key=payload.get("api_key", ""),
        description=payload.get("description", ""),
        enabled=bool(payload.get("enabled", True)),
        is_default=is_default,
    )
    db.session.add(agent)
    db.session.commit()

    log_audit(
        user_id=None,
        action="backup.agent.create",
        target_type="backup_agent",
        target_id=str(agent.id),
        detail=payload,
    )
    return ok_response(data=agent.to_dict(), code=201)


@bp.route("/<int:agent_id>", methods=["PATCH"])
@admin_required
def update_agent(agent_id):
    """更新 Agent"""
    payload = request.get_json(silent=True) or {}
    agent = BackupAgent.query.get_or_404(agent_id)

    if "name" in payload:
        name = payload["name"].strip()
        # 检查名称是否已存在（排除自己）
        existing = BackupAgent.query.filter(BackupAgent.name == name, BackupAgent.id != agent_id).first()
        if existing:
            return error_response("name already exists", code=400)
        agent.name = name

    if "url" in payload:
        url = payload["url"].strip()
        if not url.startswith(("http://", "https://")):
            return error_response("url must start with http:// or https://", code=400)
        agent.url = url

    if "api_key" in payload:
        agent.api_key = payload["api_key"]

    if "description" in payload:
        agent.description = payload["description"]

    if "enabled" in payload:
        agent.enabled = bool(payload["enabled"])

    if "is_default" in payload:
        is_default = bool(payload["is_default"])
        if is_default:
            # 取消其他默认
            BackupAgent.query.filter(BackupAgent.id != agent_id).update({"is_default": False})
        agent.is_default = is_default

    db.session.commit()

    log_audit(
        user_id=None,
        action="backup.agent.update",
        target_type="backup_agent",
        target_id=str(agent.id),
        detail=payload,
    )
    return ok_response(data=agent.to_dict())


@bp.route("/<int:agent_id>", methods=["DELETE"])
@admin_required
def delete_agent(agent_id):
    """删除 Agent"""
    agent = BackupAgent.query.get_or_404(agent_id)

    # 检查是否有策略关联
    if agent.policies.count() > 0:
        return error_response("cannot delete agent with associated policies", code=400)
    if DatabaseInstance.query.filter_by(probe_agent_id=agent.id).count() > 0:
        return error_response("cannot delete agent used by database instances", code=400)

    db.session.delete(agent)
    db.session.commit()

    log_audit(
        user_id=None,
        action="backup.agent.delete",
        target_type="backup_agent",
        target_id=str(agent_id),
    )
    return ok_response(message="deleted")


@bp.route("/<int:agent_id>/test", methods=["POST"])
@active_user_required
def test_agent(agent_id):
    """测试 Agent 连接"""
    agent = BackupAgent.query.get_or_404(agent_id)

    if not agent.enabled:
        return error_response("agent is disabled", code=400)

    try:
        response = requests.get(f"{agent.url}/api/agent/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return ok_response(data={"ok": True, "message": "agent is reachable", "health": data.get("data", {})})
        else:
            return ok_response(data={"ok": False, "message": f"agent returned status {response.status_code}"})
    except requests.exceptions.ConnectionError:
        return error_response("cannot connect to agent", code=502)
    except requests.exceptions.Timeout:
        return error_response("agent request timeout", code=504)
    except Exception as e:
        return error_response(f"error: {str(e)}", code=500)


@bp.route("/<int:agent_id>/health", methods=["GET"])
@active_user_required
def get_agent_health(agent_id):
    """获取 Agent 健康状态"""
    agent = BackupAgent.query.get_or_404(agent_id)

    if not agent.enabled:
        return ok_response(data={"status": "disabled", "enabled": False})

    try:
        response = requests.get(f"{agent.url}/api/agent/health", timeout=5)
        if response.status_code == 200:
            data = response.json()
            return ok_response(data=data.get("data", {}))
        else:
            return ok_response(data={"status": "unhealthy", "code": response.status_code})
    except requests.exceptions.ConnectionError:
        return ok_response(data={"status": "unreachable", "message": "cannot connect"})
    except requests.exceptions.Timeout:
        return ok_response(data={"status": "timeout", "message": "request timeout"})
    except Exception as e:
        return ok_response(data={"status": "error", "message": str(e)})
