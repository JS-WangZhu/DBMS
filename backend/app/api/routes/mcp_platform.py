import secrets
import json
from datetime import datetime

from flask import Blueprint, g, jsonify, request

from app.api.routes.common import api_key_required, get_current_user, list_allowed_cluster_ids, require_menu_permission
from app.extensions import db
from app.models.user import User
from app.models.user_permission import ApiKey
from app.services.audit import log_audit
from app.services.mcp_status import build_mcp_instance_status
from app.utils.response import error_response, ok_response

bp = Blueprint("mcp_platform", __name__, url_prefix="/mcp")

MCP_SCOPE_INSTANCE_STATUS = "instance_status:read"
MCP_TOOL_NAME = "dbms_get_latest_instance_status"
MCP_PROTOCOL_VERSION = "2024-11-05"


def _current_user_api_key_query():
    user = get_current_user()
    query = ApiKey.query.filter_by(purpose="mcp")
    if not user or user.role != "admin":
        query = query.filter_by(user_id=user.id if user else None)
    return query


def _api_key_row(item: ApiKey):
    data = item.to_dict()
    user = User.query.get(item.user_id)
    data["username"] = user.username if user else None
    return data


def _require_mcp_key():
    api_key = getattr(g, "api_key", None)
    if not api_key or api_key.purpose != "mcp":
        return error_response("mcp api key required", code=403)
    scopes = api_key.scopes if isinstance(api_key.scopes, list) else []
    if scopes and MCP_SCOPE_INSTANCE_STATUS not in scopes:
        return error_response("api key scope denied", code=403)
    api_key.last_used_at = datetime.utcnow()
    db.session.commit()
    return None


def _bool_arg(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _filters_from_source(source):
    filters = {}
    for key in ("db_type", "business_line", "environment", "cluster_name", "status"):
        value = source.get(key)
        if value not in (None, ""):
            filters[key] = str(value).strip()
    for key in ("cluster_id",):
        value = source.get(key)
        if value not in (None, ""):
            try:
                filters[key] = int(value)
            except (TypeError, ValueError):
                raise ValueError(f"{key} must be integer")
    if "enabled" in source and source.get("enabled") not in (None, ""):
        filters["enabled"] = _bool_arg(source.get("enabled"))
    filters["unhealthy_only"] = _bool_arg(source.get("unhealthy_only"))
    filters["include_raw_payload"] = _bool_arg(source.get("include_raw_payload"))
    return filters


def _status_payload(source):
    denied = _require_mcp_key()
    if denied:
        return denied
    try:
        filters = _filters_from_source(source)
    except ValueError as exc:
        return error_response(str(exc), code=400)
    data = build_mcp_instance_status(filters=filters, allowed_cluster_ids=list_allowed_cluster_ids("query"))
    return ok_response(data=data)


def _jsonrpc_result(result, request_id=None):
    payload = {"jsonrpc": "2.0", "result": result}
    if request_id is not None:
        payload["id"] = request_id
    return payload


def _jsonrpc_error(code, message, request_id=None):
    payload = {"jsonrpc": "2.0", "error": {"code": code, "message": message}}
    if request_id is not None:
        payload["id"] = request_id
    return payload


def _mcp_tool_schema():
    return {
        "type": "object",
        "properties": {
            "db_type": {
                "type": "string",
                "enum": ["mysql", "mongodb", "redis", "postgresql", "doris"],
                "description": "Optional database type filter.",
            },
            "business_line": {"type": "string", "description": "Optional business line filter."},
            "environment": {"type": "string", "description": "Optional environment filter."},
            "cluster_id": {"type": "integer", "description": "Optional DBMS cluster id filter."},
            "cluster_name": {"type": "string", "description": "Optional DBMS cluster name filter."},
            "status": {"type": "string", "description": "Optional normalized status filter."},
            "unhealthy_only": {"type": "boolean", "description": "Return only unhealthy or alerted instances."},
            "include_raw_payload": {"type": "boolean", "description": "Include original collector payload."},
        },
        "additionalProperties": False,
    }


def _mcp_tools():
    return [
        {
            "name": MCP_TOOL_NAME,
            "description": "Query DBMS latest database instance status details for MySQL, MongoDB, Redis and Doris.",
            "inputSchema": _mcp_tool_schema(),
        }
    ]


def _handle_mcp_jsonrpc(message):
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}

    if method == "initialize":
        return _jsonrpc_result(
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "dbms-instance-status", "version": "1.0.0"},
            },
            request_id,
        )
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return _jsonrpc_result({}, request_id)
    if method == "tools/list":
        return _jsonrpc_result({"tools": _mcp_tools()}, request_id)
    if method == "tools/call":
        if params.get("name") != MCP_TOOL_NAME:
            return _jsonrpc_error(-32602, f"unknown tool: {params.get('name')}", request_id)
        try:
            filters = _filters_from_source(params.get("arguments") or {})
            data = build_mcp_instance_status(filters=filters, allowed_cluster_ids=list_allowed_cluster_ids("query"))
        except Exception as exc:
            return _jsonrpc_result({"content": [{"type": "text", "text": str(exc)}], "isError": True}, request_id)
        return _jsonrpc_result(
            {
                "content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, separators=(",", ":"))}],
                "isError": False,
            },
            request_id,
        )
    return _jsonrpc_error(-32601, f"method not found: {method}", request_id)


def _mcp_http_response(payload, status=200):
    if payload is None:
        return "", 202
    response = jsonify(payload)
    response.status_code = status
    response.headers["MCP-Protocol-Version"] = MCP_PROTOCOL_VERSION
    response.headers["Cache-Control"] = "no-cache"
    return response


@bp.get("/api-keys")
@require_menu_permission("mcp_platform")
def list_api_keys():
    rows = _current_user_api_key_query().order_by(ApiKey.id.desc()).all()
    return ok_response(data=[_api_key_row(item) for item in rows])


@bp.post("/api-keys")
@require_menu_permission("mcp_platform")
def create_api_key():
    user = get_current_user()
    payload = request.get_json(silent=True) or {}
    user_id = payload.get("user_id") if user and user.role == "admin" else None
    if user_id in (None, "") and user:
        user_id = user.id
    target_user = User.query.get(user_id)
    if not target_user or target_user.status != "active":
        return error_response("active user not found", code=404)
    name = (payload.get("name") or "").strip() or "MCP Instance Status"
    token = "mcp_" + secrets.token_urlsafe(32)
    api_key = ApiKey(
        user_id=target_user.id,
        name=name[:128],
        token=token,
        purpose="mcp",
        scopes=[MCP_SCOPE_INSTANCE_STATUS],
        status="active",
    )
    db.session.add(api_key)
    db.session.commit()
    log_audit(
        user_id=user.id if user else None,
        action="mcp.api_key.create",
        target_type="api_key",
        target_id=str(api_key.id),
        detail={"name": api_key.name, "user_id": target_user.id},
    )
    return ok_response(data=_api_key_row(api_key), code=201)


@bp.delete("/api-keys/<int:key_id>")
@require_menu_permission("mcp_platform")
def delete_api_key(key_id: int):
    user = get_current_user()
    query = ApiKey.query.filter_by(id=key_id, purpose="mcp")
    if not user or user.role != "admin":
        query = query.filter_by(user_id=user.id if user else None)
    api_key = query.first()
    if not api_key:
        return error_response("api key not found", code=404)
    db.session.delete(api_key)
    db.session.commit()
    log_audit(
        user_id=user.id if user else None,
        action="mcp.api_key.delete",
        target_type="api_key",
        target_id=str(key_id),
    )
    return ok_response(message="deleted")


@bp.post("")
@bp.post("/")
@api_key_required
def streamable_http_mcp():
    denied = _require_mcp_key()
    if denied:
        return denied
    payload = request.get_json(silent=True)
    if payload is None:
        return _mcp_http_response(_jsonrpc_error(-32700, "invalid json"), status=400)
    if isinstance(payload, list):
        responses = [_handle_mcp_jsonrpc(item) for item in payload if isinstance(item, dict)]
        responses = [item for item in responses if item is not None]
        return _mcp_http_response(responses if responses else None)
    if not isinstance(payload, dict):
        return _mcp_http_response(_jsonrpc_error(-32600, "invalid request"), status=400)
    response = _handle_mcp_jsonrpc(payload)
    return _mcp_http_response(response)


@bp.get("")
@bp.get("/")
@api_key_required
def streamable_http_info():
    denied = _require_mcp_key()
    if denied:
        return denied
    return ok_response(
        data={
            "transport": "streamable-http",
            "protocol_version": MCP_PROTOCOL_VERSION,
            "server": "dbms-instance-status",
            "tools": _mcp_tools(),
        }
    )


@bp.get("/instance-status")
@api_key_required
def get_instance_status():
    return _status_payload(request.args)


@bp.post("/tools/dbms_get_latest_instance_status")
@api_key_required
def get_instance_status_tool():
    return _status_payload(request.get_json(silent=True) or {})
