import json
import os
import sys
from typing import Any, Dict

import requests


SERVER_NAME = "dbms-instance-status"
SERVER_VERSION = "1.1.0"
TOOL_NAME = "dbms_get_latest_instance_status"
CLUSTER_INSTANCE_TOOL_NAME = "dbms_get_cluster_instance_mapping"
BACKUP_STATUS_TOOL_NAME = "dbms_get_database_backup_status"
INSPECTION_STATUS_TOOL_NAME = "dbms_get_inspection_status"


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _api_base_url() -> str:
    return _env("DBMS_BASE_URL", "http://127.0.0.1:5000").rstrip("/")


def _api_key() -> str:
    return _env("DBMS_MCP_API_KEY")


def _response(result: Dict[str, Any], request_id: Any = None) -> Dict[str, Any]:
    payload = {"jsonrpc": "2.0", "result": result}
    if request_id is not None:
        payload["id"] = request_id
    return payload


def _error(code: int, message: str, request_id: Any = None) -> Dict[str, Any]:
    payload = {"jsonrpc": "2.0", "error": {"code": code, "message": message}}
    if request_id is not None:
        payload["id"] = request_id
    return payload


def _tool_schema() -> Dict[str, Any]:
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
            "instance_id": {"type": "integer", "description": "Optional exact DBMS instance id."},
            "instance_name": {"type": "string", "description": "Optional exact DBMS instance name."},
            "host": {"type": "string", "description": "Optional exact configured instance host."},
            "port": {"type": "integer", "description": "Optional exact instance port."},
            "status": {"type": "string", "description": "Optional normalized status filter."},
            "unhealthy_only": {"type": "boolean", "description": "Return only unhealthy or alerted instances."},
            "include_raw_payload": {"type": "boolean", "description": "Include original collector payload."},
        },
        "additionalProperties": False,
    }


def _cluster_instance_tool_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "db_type": {"type": "string", "enum": ["mysql", "mongodb", "redis", "postgresql", "doris"]},
            "cluster_id": {"type": "integer", "description": "Optional exact DBMS cluster id."},
            "enabled_only": {"type": "boolean", "description": "Only include enabled instances."},
        },
        "additionalProperties": False,
    }


def _backup_status_tool_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "db_type": {"type": "string", "enum": ["mysql", "mongodb", "postgresql"]},
            "cluster_id": {"type": "integer", "description": "Optional exact DBMS cluster id."},
            "instance_id": {"type": "integer", "description": "Optional exact DBMS instance id."},
            "hours": {"type": "integer", "minimum": 1, "maximum": 720, "description": "Healthy backup time window, default 48 hours."},
            "protection_status": {
                "type": "string",
                "enum": ["healthy", "stale", "running", "failed", "never_run", "unconfigured"],
            },
        },
        "additionalProperties": False,
    }


def _inspection_status_tool_schema() -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "db_type": {"type": "string", "enum": ["mysql", "mongodb", "redis", "postgresql", "doris"]},
            "cluster_id": {"type": "integer", "description": "Optional exact DBMS cluster id."},
            "instance_id": {"type": "integer", "description": "Optional exact DBMS instance id."},
            "include_recovered": {"type": "boolean", "description": "Include recovered alert history; default false."},
        },
        "additionalProperties": False,
    }


def _list_tools() -> Dict[str, Any]:
    return {
        "tools": [
            {
                "name": TOOL_NAME,
                "description": "Query DBMS latest database instance status details for MySQL, MongoDB, Redis, PostgreSQL and Doris.",
                "inputSchema": _tool_schema(),
            },
            {
                "name": CLUSTER_INSTANCE_TOOL_NAME,
                "description": "Return the DBMS cluster-to-instance mapping visible to the API key owner.",
                "inputSchema": _cluster_instance_tool_schema(),
            },
            {
                "name": BACKUP_STATUS_TOOL_NAME,
                "description": "Return backup protection status for all visible MySQL, MongoDB and PostgreSQL instances, including policies and latest results.",
                "inputSchema": _backup_status_tool_schema(),
            },
            {
                "name": INSPECTION_STATUS_TOOL_NAME,
                "description": "Return all current inspection item thresholds, visible assets and alert information.",
                "inputSchema": _inspection_status_tool_schema(),
            },
        ]
    }


def _call_tool(name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    api_key = _api_key()
    if not api_key:
        raise RuntimeError("DBMS_MCP_API_KEY is required")
    url = f"{_api_base_url()}/api/v1/mcp/tools/{name}"
    response = requests.post(
        url,
        headers={"X-API-Key": api_key, "Content-Type": "application/json"},
        json=arguments or {},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("ok"):
        raise RuntimeError(payload.get("message") or "DBMS API returned an error")
    return payload.get("data") or {}


def _handle(request: Dict[str, Any]) -> Dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")
    params = request.get("params") or {}

    if method == "initialize":
        return _response(
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
            request_id,
        )
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return _response({}, request_id)
    if method == "tools/list":
        return _response(_list_tools(), request_id)
    if method == "tools/call":
        name = params.get("name")
        tool_names = {item["name"] for item in _list_tools()["tools"]}
        if name not in tool_names:
            return _error(-32602, f"unknown tool: {name}", request_id)
        try:
            data = _call_tool(name, params.get("arguments") or {})
        except Exception as exc:
            return _response({"content": [{"type": "text", "text": str(exc)}], "isError": True}, request_id)
        return _response(
            {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                    }
                ],
                "isError": False,
            },
            request_id,
        )
    return _error(-32601, f"method not found: {method}", request_id)


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = _handle(request)
        except Exception as exc:
            response = _error(-32700, str(exc))
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
