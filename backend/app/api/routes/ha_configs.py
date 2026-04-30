import os
import string
import subprocess

from flask import Blueprint, request

from app.api.routes.common import require_menu_permission
from app.extensions import db
from app.models.ha_config import HAConfig
from app.models.notify_target import BackupNotifyTarget
from app.utils.response import error_response, ok_response

bp = Blueprint("ha_configs", __name__, url_prefix="/ha")


def _validate_script_path(script_path: str):
    if not script_path:
        return "script_path is required"
    if not os.path.exists(script_path):
        return f"脚本路径不存在: {script_path}"
    if not os.access(script_path, os.X_OK):
        return f"脚本不可执行: {script_path}"
    return None


def _validate_command_template(command_template: str):
    text = str(command_template or "").strip()
    if not text:
        return None
    try:
        string.Template(text).substitute(
            script_path="script_path",
            switch_mode="normal",
            switch_label="在线切换",
            cluster_id="1",
            cluster_name="cluster",
            business_line="demo",
            environment="prod",
            ha_domain="db.example.com",
            source_host="old-master",
            source_ip="10.0.0.1",
            source_port="3306",
            source_name="mysql-a",
            source_address="10.0.0.1:3306",
            target_host="new-master",
            target_ip="10.0.0.2",
            target_port="3306",
            target_name="mysql-b",
            target_address="10.0.0.2:3306",
            switch_info_json="{}",
        )
    except ValueError as exc:
        return f"命令模板格式非法: {exc}"
    except KeyError as exc:
        return f"命令模板包含未知变量: {exc}"
    return None


def _normalize_notify_target_ids(value):
    target_ids = []
    for item in value or []:
        try:
            target_ids.append(int(item))
        except (TypeError, ValueError):
            continue
    return target_ids


def _validate_notify_target_ids(target_ids):
    if not target_ids:
        return None
    rows = BackupNotifyTarget.query.filter(BackupNotifyTarget.id.in_(target_ids)).all()
    row_map = {row.id: row for row in rows}
    missing_ids = [item for item in target_ids if item not in row_map]
    if missing_ids:
        return f"通知地址不存在: {', '.join(str(item) for item in missing_ids)}"
    invalid_rows = [row.name for row in rows if row.channel != "wecom"]
    if invalid_rows:
        return f"仅支持绑定企微通知地址: {', '.join(invalid_rows)}"
    return None


@bp.get("/configs")
@require_menu_permission("ha_config")
def list_ha_configs():
    try:
        configs = HAConfig.query.order_by(HAConfig.id.desc()).all()
        return ok_response(data=[item.to_dict() for item in configs])
    except Exception as exc:
        if "no such table" in str(exc).lower():
            try:
                db.create_all()
                return ok_response(data=[])
            except Exception:
                pass
        return error_response(f"Database error: {exc}", code=500)


@bp.post("/configs")
@require_menu_permission("ha_config")
def create_ha_config():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name") or "").strip()
    script_path = str(payload.get("script_path") or "").strip()
    command_template = str(payload.get("command_template") or "").strip()
    description = str(payload.get("description") or "").strip()
    enabled = bool(payload.get("enabled", True))
    is_default = bool(payload.get("is_default", False))
    notify_target_ids = _normalize_notify_target_ids(payload.get("notify_target_ids"))

    if not name:
        return error_response("name is required", code=400)
    err = _validate_script_path(script_path)
    if err:
        return error_response(err, code=400)
    template_err = _validate_command_template(command_template)
    if template_err:
        return error_response(template_err, code=400)
    notify_err = _validate_notify_target_ids(notify_target_ids)
    if notify_err:
        return error_response(notify_err, code=400)
    if HAConfig.query.filter_by(name=name).first():
        return error_response("name already exists", code=400)

    config = HAConfig(
        name=name,
        script_path=script_path,
        command_template=command_template or None,
        description=description,
        enabled=enabled,
        is_default=is_default,
        notify_target_ids=notify_target_ids,
    )
    if is_default:
        HAConfig.query.update({HAConfig.is_default: False})
    db.session.add(config)
    db.session.commit()
    return ok_response(data=config.to_dict())


@bp.patch("/configs/<int:config_id>")
@require_menu_permission("ha_config")
def update_ha_config(config_id: int):
    config = HAConfig.query.get_or_404(config_id)
    payload = request.get_json(silent=True) or {}

    if "name" in payload:
        name = str(payload.get("name") or "").strip()
        if not name:
            return error_response("name is required", code=400)
        existing = HAConfig.query.filter_by(name=name).first()
        if existing and existing.id != config_id:
            return error_response("name already exists", code=400)
        config.name = name

    if "script_path" in payload:
        script_path = str(payload.get("script_path") or "").strip()
        err = _validate_script_path(script_path)
        if err:
            return error_response(err, code=400)
        config.script_path = script_path

    if "command_template" in payload:
        command_template = str(payload.get("command_template") or "").strip()
        template_err = _validate_command_template(command_template)
        if template_err:
            return error_response(template_err, code=400)
        config.command_template = command_template or None

    if "description" in payload:
        config.description = str(payload.get("description") or "").strip()

    if "enabled" in payload:
        config.enabled = bool(payload.get("enabled"))

    if "is_default" in payload:
        config.is_default = bool(payload.get("is_default"))
        if config.is_default:
            HAConfig.query.filter(HAConfig.id != config_id).update({HAConfig.is_default: False})

    if "notify_target_ids" in payload:
        notify_target_ids = _normalize_notify_target_ids(payload.get("notify_target_ids"))
        notify_err = _validate_notify_target_ids(notify_target_ids)
        if notify_err:
            return error_response(notify_err, code=400)
        config.notify_target_ids = notify_target_ids

    db.session.commit()
    return ok_response(data=config.to_dict())


@bp.delete("/configs/<int:config_id>")
@require_menu_permission("ha_config")
def delete_ha_config(config_id: int):
    config = HAConfig.query.get_or_404(config_id)
    db.session.delete(config)
    db.session.commit()
    return ok_response()


@bp.post("/configs/verify")
@require_menu_permission("ha_config")
def verify_ha_script_path():
    payload = request.get_json(silent=True) or {}
    script_path = str(payload.get("script_path") or "").strip()
    err = _validate_script_path(script_path)
    if err:
        return error_response(err, code=400)

    try:
        result = subprocess.run([script_path, "--version"], capture_output=True, text=True, timeout=5, check=False)
        version_output = result.stdout or result.stderr
    except Exception as exc:
        version_output = f"无法获取版本信息: {exc}"

    return ok_response(
        data={
            "available": True,
            "path": script_path,
            "version": (version_output or "").strip() or "unknown",
        }
    )
