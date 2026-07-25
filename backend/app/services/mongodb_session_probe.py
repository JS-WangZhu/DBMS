import atexit
import json
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta


PROBE_TTL_SECONDS = 5 * 60


class SessionProbeError(Exception):
    pass


@dataclass
class ProbeSession:
    token: str
    user_id: int
    instance_id: int
    connection: object
    instance_name: str
    app_name: str
    started_at: datetime
    expires_at: datetime
    timer: threading.Timer | None = None
    lock: threading.RLock = field(default_factory=threading.RLock)


_SESSIONS = {}
_SESSIONS_LOCK = threading.RLock()


def _close_connection(connection):
    try:
        connection.close()
    except Exception:
        pass


def _expire_session(token):
    with _SESSIONS_LOCK:
        session = _SESSIONS.pop(token, None)
    if session:
        with session.lock:
            _close_connection(session.connection)


def close_probe_session(token: str, user_id: int | None = None) -> bool:
    with _SESSIONS_LOCK:
        session = _SESSIONS.get(token)
        if not session:
            return False
        if user_id is not None and session.user_id != int(user_id):
            raise SessionProbeError("session probe does not belong to current user")
        _SESSIONS.pop(token, None)
    if session.timer:
        session.timer.cancel()
    with session.lock:
        _close_connection(session.connection)
    return True


def close_all_probe_sessions():
    with _SESSIONS_LOCK:
        tokens = list(_SESSIONS)
    for token in tokens:
        close_probe_session(token)


atexit.register(close_all_probe_sessions)


def _get_probe_session(token: str, user_id: int) -> ProbeSession:
    with _SESSIONS_LOCK:
        session = _SESSIONS.get(token)
    if not session:
        raise SessionProbeError("session probe not found or expired")
    if session.user_id != int(user_id):
        raise SessionProbeError("session probe does not belong to current user")
    if datetime.now() >= session.expires_at:
        _expire_session(token)
        raise SessionProbeError("session probe expired")
    return session


def _as_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _create_client(instance, password: str, app_name: str):
    from pymongo import MongoClient

    extra = instance.extra_json if isinstance(instance.extra_json, dict) else {}
    options = {
        "serverSelectionTimeoutMS": 5000,
        "connectTimeoutMS": 5000,
        "socketTimeoutMS": 5000,
        "directConnection": True,
        "tls": _as_bool(extra.get("tls", extra.get("ssl")), default=False),
        "appname": app_name,
    }
    host = instance.resolved_ip or instance.host_input
    auth_mechanism = str(extra.get("auth_mechanism") or "").strip() or None
    configured_source = str(extra.get("auth_source") or extra.get("auth_db") or "").strip()
    auth_sources = [configured_source] if configured_source else []
    for source in ("admin", "local"):
        if source not in auth_sources:
            auth_sources.append(source)

    if not instance.username:
        client = MongoClient(host, instance.port, **options)
        client.admin.command("ping")
        return client

    last_error = None
    for source in auth_sources:
        kwargs = dict(username=instance.username, password=password or "", authSource=source, **options)
        if auth_mechanism:
            kwargs["authMechanism"] = auth_mechanism
        try:
            client = MongoClient(host, instance.port, **kwargs)
            client.admin.command("ping")
            return client
        except Exception as exc:
            _close_connection(locals().get("client"))
            last_error = exc
            if not auth_mechanism:
                continue
            try:
                kwargs.pop("authMechanism", None)
                client = MongoClient(host, instance.port, **kwargs)
                client.admin.command("ping")
                return client
            except Exception as retry_exc:
                _close_connection(locals().get("client"))
                last_error = retry_exc
    raise last_error or SessionProbeError("mongodb authentication failed")


def start_probe_session(instance, password: str, user_id: int) -> dict:
    if str(getattr(instance, "access_mode", "server") or "server").lower() != "server":
        raise SessionProbeError("会话探测需要平台服务端可直接访问 MongoDB，当前实例使用 Agent 接入模式")
    token = secrets.token_urlsafe(32)
    app_name = f"dbms-mongodb-session-probe-{token[:12]}"
    try:
        connection = _create_client(instance, password, app_name)
    except Exception as exc:
        raise SessionProbeError(f"mongodb session probe connect failed: {exc}") from exc

    now = datetime.now()
    session = ProbeSession(
        token=token, user_id=int(user_id), instance_id=int(instance.id), connection=connection,
        instance_name=instance.name, app_name=app_name, started_at=now,
        expires_at=now + timedelta(seconds=PROBE_TTL_SECONDS),
    )
    timer = threading.Timer(PROBE_TTL_SECONDS, _expire_session, args=(token,))
    timer.daemon = True
    session.timer = timer
    with _SESSIONS_LOCK:
        _SESSIONS[token] = session
    timer.start()
    return probe_session_metadata(session)


def probe_session_metadata(session: ProbeSession) -> dict:
    return {
        "token": session.token,
        "instance_id": session.instance_id,
        "instance_name": session.instance_name,
        "started_at": session.started_at.isoformat(),
        "expires_at": session.expires_at.isoformat(),
        "ttl_seconds": max(0, int((session.expires_at - datetime.now()).total_seconds())),
    }


def _json_safe(value):
    try:
        return json.loads(json.dumps(value, default=str))
    except Exception:
        pass
    try:
        from bson.json_util import dumps
        return json.loads(dumps(value))
    except Exception:
        return str(value)


def _is_probe_operation(item: dict, app_name: str) -> bool:
    if str(item.get("appName") or "") == app_name:
        return True
    metadata = item.get("clientMetadata") if isinstance(item.get("clientMetadata"), dict) else {}
    application = metadata.get("application") if isinstance(metadata.get("application"), dict) else {}
    return str(application.get("name") or "") == app_name


def _is_hidden_operation(item: dict) -> bool:
    return str(item.get("ns") or "").strip() == "local.oplog.rs"


def _format_operation_user(item: dict) -> str:
    raw_users = item.get("effectiveUsers")
    if raw_users in (None, "", []):
        raw_users = item.get("authenticatedUsers")
    if raw_users in (None, "", []):
        raw_users = item.get("user")
    if raw_users in (None, "", []):
        return ""

    users = raw_users if isinstance(raw_users, list) else [raw_users]
    labels = []
    for value in users:
        if isinstance(value, dict):
            username = str(value.get("user") or value.get("username") or "").strip()
            auth_database = str(value.get("db") or value.get("authSource") or "").strip()
            label = f"{username}@{auth_database}" if username and auth_database else username or auth_database
        else:
            label = str(value).strip()
        if label and label not in labels:
            labels.append(label)
    return ", ".join(labels)


def _normalize_operation(item: dict, app_name: str) -> dict | None:
    operation_id = item.get("opid")
    if operation_id is None:
        return None
    command = item.get("command") if isinstance(item.get("command"), dict) else {}
    return {
        "id": str(operation_id),
        "operation": item.get("op"),
        "namespace": item.get("ns"),
        "client": item.get("client"),
        "user": _format_operation_user(item),
        "app_name": item.get("appName"),
        "description": item.get("desc"),
        "time_seconds": max(0, int(item.get("secs_running") or item.get("microsecs_running", 0) / 1000000 or 0)),
        "active": bool(item.get("active")),
        "waiting_for_lock": bool(item.get("waitingForLock")),
        "command": _json_safe(command),
        "is_probe_connection": _is_probe_operation(item, app_name),
    }


def _current_op_command() -> dict:
    # allUsers/idleConnections/truncateOps belong to the $currentOp aggregation
    # stage. The legacy currentOp database command uses the special $all option.
    return {"currentOp": 1, "$all": True}


def fetch_operations(token: str, user_id: int) -> dict:
    session = _get_probe_session(token, user_id)
    try:
        with session.lock:
            result = session.connection.admin.command(_current_op_command())
    except Exception as exc:
        close_probe_session(token, user_id=user_id)
        raise SessionProbeError(f"currentOp fetch failed: {exc}") from exc
    items = [
        normalized for raw in (result.get("inprog") or [])
        if isinstance(raw, dict)
        if not _is_hidden_operation(raw)
        for normalized in [_normalize_operation(raw, session.app_name)]
        if normalized is not None
    ]
    items.sort(key=lambda item: (-item["time_seconds"], item["id"]))
    return {**probe_session_metadata(session), "collected_at": datetime.now().isoformat(), "sessions": items}


def kill_operation(token: str, user_id: int, operation_id) -> dict:
    session = _get_probe_session(token, user_id)
    target_id = str(operation_id or "").strip()
    if not target_id:
        raise SessionProbeError("invalid operation id")
    try:
        with session.lock:
            current = session.connection.admin.command(_current_op_command())
            target = next((item for item in current.get("inprog") or [] if str(item.get("opid")) == target_id), None)
            if target and _is_probe_operation(target, session.app_name):
                raise SessionProbeError("cannot kill the session probe operation")
            raw_operation_id = target.get("opid") if target else (int(target_id) if target_id.isdigit() else target_id)
            session.connection.admin.command({"killOp": 1, "op": raw_operation_id})
    except SessionProbeError:
        raise
    except Exception as exc:
        raise SessionProbeError(f"kill mongodb operation failed: {exc}") from exc
    return {"operation_id": target_id, "killed": True}
