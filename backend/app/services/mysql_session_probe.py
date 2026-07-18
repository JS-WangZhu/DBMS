import atexit
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
    connection_id: int
    instance_name: str
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


def start_probe_session(instance, password: str, user_id: int) -> dict:
    if str(getattr(instance, "access_mode", "server") or "server").lower() != "server":
        raise SessionProbeError("会话探测需要平台服务端可直接访问 MySQL，当前实例使用 Agent 接入模式")
    try:
        import pymysql

        connection = pymysql.connect(
            host=instance.resolved_ip or instance.host_input,
            port=int(instance.port or 3306),
            user=instance.username or "",
            password=password or "",
            connect_timeout=5,
            read_timeout=5,
            write_timeout=5,
            autocommit=True,
            charset="utf8mb4",
        )
        with connection.cursor() as cursor:
            cursor.execute("SELECT CONNECTION_ID()")
            row = cursor.fetchone()
            connection_id = int(row[0])
    except Exception as exc:
        if "connection" in locals():
            _close_connection(connection)
        raise SessionProbeError(f"mysql session probe connect failed: {exc}") from exc

    now = datetime.now()
    token = secrets.token_urlsafe(32)
    session = ProbeSession(
        token=token,
        user_id=int(user_id),
        instance_id=int(instance.id),
        connection=connection,
        connection_id=connection_id,
        instance_name=instance.name,
        started_at=now,
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
        "connection_id": session.connection_id,
        "started_at": session.started_at.isoformat(),
        "expires_at": session.expires_at.isoformat(),
        "ttl_seconds": max(0, int((session.expires_at - datetime.now()).total_seconds())),
    }


def _normalize_info(value):
    if value is None:
        return None
    text = str(value).strip()
    return " ".join(text.split())


REPLICATION_STATE_MARKERS = (
    "waiting for source to send event",
    "waiting for master to send event",
    "source has sent all binlog",
    "master has sent all binlog",
    "replica has read all relay log",
    "slave has read all relay log",
    "waiting for an event from coordinator",
    "waiting for replica workers",
    "waiting for slave workers",
    "queueing source event to the relay log",
    "queueing master event to the relay log",
    "reading event from the relay log",
    "connecting to source",
    "connecting to master",
    "reconnecting after a failed source event read",
    "reconnecting after a failed master event read",
)


def _is_system_or_replication_session(item: dict) -> bool:
    user = str(item.get("user") or "").strip().lower()
    if user in {"system user", "event_scheduler"}:
        return True
    command = str(item.get("command") or "").strip().lower()
    if command.startswith("binlog dump"):
        return True
    state = str(item.get("state") or "").strip().lower()
    return any(marker in state for marker in REPLICATION_STATE_MARKERS)


def fetch_processlist(token: str, user_id: int) -> dict:
    session = _get_probe_session(token, user_id)
    sql = (
        "SELECT ID, USER, HOST, DB, COMMAND, TIME, STATE, INFO "
        "FROM information_schema.PROCESSLIST ORDER BY TIME DESC, ID ASC"
    )
    try:
        with session.lock:
            session.connection.ping(reconnect=False)
            with session.connection.cursor() as cursor:
                cursor.execute(sql)
                columns = [str(item[0]).lower() for item in cursor.description]
                rows = cursor.fetchall() or []
    except Exception as exc:
        close_probe_session(token, user_id=user_id)
        raise SessionProbeError(f"processlist fetch failed: {exc}") from exc

    items = []
    for raw in rows:
        item = dict(zip(columns, raw))
        if _is_system_or_replication_session(item):
            continue
        user = str(item.get("user") or "").strip()
        process_id = int(item.get("id"))
        items.append({
            "id": process_id,
            "user": user or None,
            "host": item.get("host"),
            "database": item.get("db"),
            "command": item.get("command"),
            "time_seconds": int(item.get("time") or 0),
            "state": item.get("state"),
            "sql": _normalize_info(item.get("info")),
            "is_probe_connection": process_id == session.connection_id,
        })
    return {
        **probe_session_metadata(session),
        "collected_at": datetime.now().isoformat(),
        "sessions": items,
    }


def kill_process(token: str, user_id: int, process_id: int) -> dict:
    session = _get_probe_session(token, user_id)
    try:
        target_id = int(process_id)
    except (TypeError, ValueError) as exc:
        raise SessionProbeError("invalid process id") from exc
    if target_id <= 0:
        raise SessionProbeError("invalid process id")
    if target_id == session.connection_id:
        raise SessionProbeError("cannot kill the session probe connection")
    try:
        with session.lock:
            session.connection.ping(reconnect=False)
            with session.connection.cursor() as cursor:
                cursor.execute(f"KILL CONNECTION {target_id}")
    except Exception as exc:
        raise SessionProbeError(f"kill mysql session failed: {exc}") from exc
    return {"process_id": target_id, "killed": True}
