import os
import shutil
import subprocess
import requests

from flask import Blueprint, request

from app.api.routes.common import active_user_required
from app.extensions import db
from app.models.backup_tool_config import BackupToolConfig
from app.models.backup_agent import BackupAgent
from app.utils.response import error_response, ok_response

bp = Blueprint("backup_tools", __name__, url_prefix="/backup-tools")
VALID_DB_TYPES = {"mysql", "mongodb"}


@bp.route("", methods=["GET"])
@active_user_required
def list_backup_tools():
    """获取备份工具配置列表"""
    configs = BackupToolConfig.query.order_by(BackupToolConfig.id.desc()).all()
    return ok_response(data=[c.to_dict() for c in configs])


@bp.route("", methods=["POST"])
@active_user_required
def create_backup_tool():
    """创建备份工具配置"""
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    db_type = (payload.get("db_type") or "").strip()
    tool_path = (payload.get("tool_path") or "").strip()
    description = (payload.get("description") or "").strip()
    enabled = payload.get("enabled", True)
    backup_agent_id = payload.get("backup_agent_id")

    if not name:
        return error_response("name is required", code=400)
    if not db_type or db_type not in VALID_DB_TYPES:
        return error_response("db_type must be mysql or mongodb", code=400)
    if not tool_path:
        return error_response("tool_path is required", code=400)

    if backup_agent_id:
        agent = BackupAgent.query.get(backup_agent_id)
        if not agent:
            return error_response("backup_agent_id not found", code=400)

    # 检查名称是否重复
    existing = BackupToolConfig.query.filter_by(name=name).first()
    if existing:
        return error_response("name already exists", code=400)

    config = BackupToolConfig(
        name=name,
        db_type=db_type,
        tool_path=tool_path,
        description=description,
        enabled=bool(enabled),
        backup_agent_id=backup_agent_id,
    )
    db.session.add(config)
    db.session.commit()
    return ok_response(data=config.to_dict(), message="备份工具配置已创建")


@bp.route("/<int:config_id>", methods=["GET"])
@active_user_required
def get_backup_tool(config_id):
    """获取单个备份工具配置"""
    config = BackupToolConfig.query.get(config_id)
    if not config:
        return error_response("config not found", code=404)
    return ok_response(data=config.to_dict())


@bp.route("/<int:config_id>", methods=["PATCH"])
@active_user_required
def update_backup_tool(config_id):
    """更新备份工具配置"""
    config = BackupToolConfig.query.get(config_id)
    if not config:
        return error_response("config not found", code=404)

    payload = request.get_json(silent=True) or {}

    if "name" in payload:
        name = payload["name"].strip()
        if name and name != config.name:
            existing = BackupToolConfig.query.filter_by(name=name).first()
            if existing:
                return error_response("name already exists", code=400)
            config.name = name

    if "db_type" in payload:
        db_type = payload["db_type"].strip()
        if db_type in VALID_DB_TYPES:
            config.db_type = db_type

    if "tool_path" in payload:
        config.tool_path = payload["tool_path"].strip()

    if "description" in payload:
        config.description = payload["description"].strip()

    if "enabled" in payload:
        config.enabled = bool(payload["enabled"])

    if "backup_agent_id" in payload:
        backup_agent_id = payload["backup_agent_id"]
        if backup_agent_id:
            agent = BackupAgent.query.get(backup_agent_id)
            if not agent:
                return error_response("backup_agent_id not found", code=400)
        config.backup_agent_id = backup_agent_id

    db.session.commit()
    return ok_response(data=config.to_dict(), message="备份工具配置已更新")


@bp.route("/<int:config_id>", methods=["DELETE"])
@active_user_required
def delete_backup_tool(config_id):
    """删除备份工具配置"""
    config = BackupToolConfig.query.get(config_id)
    if not config:
        return error_response("config not found", code=404)

    db.session.delete(config)
    db.session.commit()
    return ok_response(message="备份工具配置已删除")


@bp.route("/<int:config_id>/verify", methods=["POST"])
@active_user_required
def verify_backup_tool(config_id):
    """验证备份工具是否可用"""
    config = BackupToolConfig.query.get(config_id)
    if not config:
        return error_response("config not found", code=404)

    tool_path = config.tool_path

    # 检查文件是否存在
    if not os.path.exists(tool_path):
        return error_response(f"工具路径不存在: {tool_path}", code=400)

    # 检查是否是可执行文件
    if not os.access(tool_path, os.X_OK):
        return error_response(f"工具文件不可执行: {tool_path}", code=400)

    # 检查文件类型
    base_name = os.path.basename(tool_path)
    if config.db_type == "mysql" and base_name != "mysqldump":
        return error_response(f"对于MySQL备份，工具名称应为 mysqldump，当前为 {base_name}", code=400)
    if config.db_type == "mongodb" and base_name != "mongodump":
        return error_response(f"对于MongoDB备份，工具名称应为 mongodump，当前为 {base_name}", code=400)
    # 尝试获取版本信息
    try:
        result = subprocess.run([tool_path, "--version"], capture_output=True, text=True, timeout=5)
        version_output = result.stdout or result.stderr
    except Exception as e:
        version_output = f"无法获取版本信息: {str(e)}"

    return ok_response(
        data={
            "available": True,
            "version": version_output.strip() or "unknown",
            "path": tool_path,
        },
        message="工具验证通过",
    )


@bp.route("/direct/verify", methods=["POST"])
@active_user_required
def verify_tool_path():
    """直接验证工具路径"""
    payload = request.get_json(silent=True) or {}
    tool_path = (payload.get("tool_path") or "").strip()
    db_type = (payload.get("db_type") or "").strip()

    if not tool_path:
        return error_response("tool_path is required", code=400)

    # 检查文件是否存在
    if not os.path.exists(tool_path):
        return error_response(f"工具路径不存在: {tool_path}", code=400)

    # 检查是否是可执行文件
    if not os.access(tool_path, os.X_OK):
        return error_response(f"工具文件不可执行: {tool_path}", code=400)

    # 检查工具名称
    base_name = os.path.basename(tool_path)
    if db_type == "mysql" and base_name != "mysqldump":
        return error_response(f"对于MySQL备份，工具名称应为 mysqldump，当前为 {base_name}", code=400)
    if db_type == "mongodb" and base_name != "mongodump":
        return error_response(f"对于MongoDB备份，工具名称应为 mongodump，当前为 {base_name}", code=400)
    # 尝试获取版本信息
    try:
        result = subprocess.run([tool_path, "--version"], capture_output=True, text=True, timeout=5)
        version_output = result.stdout or result.stderr
    except Exception as e:
        version_output = f"无法获取版本信息: {str(e)}"

    return ok_response(
        data={
            "available": True,
            "version": version_output.strip() or "unknown",
            "path": tool_path,
        },
        message="工具验证通过",
    )


@bp.route("/agent/verify", methods=["POST"])
@active_user_required
def verify_tool_on_agent():
    """通过 agent 验证远程备份工具"""
    payload = request.get_json(silent=True) or {}
    backup_agent_id = payload.get("backup_agent_id")
    tool_path = (payload.get("tool_path") or "").strip()

    if not backup_agent_id:
        return error_response("backup_agent_id is required", code=400)
    if not tool_path:
        return error_response("tool_path is required", code=400)

    agent = BackupAgent.query.get(backup_agent_id)
    if not agent:
        return error_response("backup_agent_id not found", code=404)

    if not agent.api_key:
        return error_response("agent api_key not configured", code=400)

    agent_url = agent.url.rstrip("/")
    verify_url = f"{agent_url}/api/agent/tool/verify"

    try:
        response = requests.post(
            verify_url,
            json={"tool_path": tool_path},
            headers={"X-Agent-API-Key": agent.api_key},
            timeout=10,
        )
        result = response.json()
        
        if response.status_code != 200:
            return error_response(
                f"agent verification failed: {result.get('message', 'unknown error')}",
                code=response.status_code,
            )
        
        if result.get("ok"):
            return ok_response(
                data=result.get("data", {}),
                message="工具验证通过",
            )
        else:
            return error_response(
                result.get("message", "tool verification failed"),
                code=400,
            )
    except requests.RequestException as e:
        return error_response(f"无法连接到 agent: {str(e)}", code=503)
