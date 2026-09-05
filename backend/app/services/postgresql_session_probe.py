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
    backend_pid: int
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


def get_probe_instance_id(token: str, user_id: int) -> int:
    return int(_get_probe_session(token, user_id).instance_id)


def _connection_kwargs(instance, password):
    extra = instance.extra_json if isinstance(instance.extra_json, dict) else {}
    return {
        "host": instance.resolved_ip or instance.host_input,
        "port": int(instance.port or 5432),
        "user": instance.username or "",
        "password": password or "",
        "dbname": extra.get("database") or extra.get("dbname") or "postgres",
        "sslmode": extra.get("sslmode") or "prefer",
        "connect_timeout": 5,
        "application_name": "dbms-session-probe",
        "options": "-c statement_timeout=5000",
    }


def start_probe_session(instance, password: str, user_id: int) -> dict:
    if str(getattr(instance, "access_mode", "server") or "server").lower() != "server":
        raise SessionProbeError("会话探测需要平台服务端可直接访问 PostgreSQL，当前实例使用 Agent 接入模式")
    try:
        import psycopg2

        connection = psycopg2.connect(**_connection_kwargs(instance, password))
        connection.autocommit = True
        backend_pid = int(connection.get_backend_pid())
    except Exception as exc:
        if "connection" in locals():
            _close_connection(connection)
        raise SessionProbeError(f"postgresql session probe connect failed: {exc}") from exc

    now = datetime.now()
    token = secrets.token_urlsafe(32)
    session = ProbeSession(
        token=token,
        user_id=int(user_id),
        instance_id=int(instance.id),
        connection=connection,
        backend_pid=backend_pid,
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
        "backend_pid": session.backend_pid,
        "started_at": session.started_at.isoformat(),
        "expires_at": session.expires_at.isoformat(),
        "ttl_seconds": max(0, int((session.expires_at - datetime.now()).total_seconds())),
    }


def _normalize_query(value):
    if value is None:
        return None
    return " ".join(str(value).strip().split())


def fetch_sessions(token: str, user_id: int) -> dict:
    session = _get_probe_session(token, user_id)
    sql = (
        "SELECT pid, usename, datname, COALESCE(client_addr::text, ''), application_name, "
        "state, wait_event_type, wait_event, "
        "GREATEST(0, EXTRACT(EPOCH FROM (clock_timestamp() - COALESCE(query_start, backend_start))))::bigint, query "
        "FROM pg_catalog.pg_stat_activity ORDER BY query_start NULLS LAST, pid"
    )
    try:
        with session.lock:
            with session.connection.cursor() as cursor:
                cursor.execute(sql)
                rows = cursor.fetchall() or []
    except Exception as exc:
        close_probe_session(token, user_id=user_id)
        raise SessionProbeError(f"postgresql sessions fetch failed: {exc}") from exc

    items = []
    for row in rows:
        pid = int(row[0])
        items.append({
            "id": pid,
            "user": row[1] or None,
            "database": row[2] or None,
            "client": row[3] or None,
            "application_name": row[4] or None,
            "state": row[5] or None,
            "wait_event_type": row[6] or None,
            "wait_event": row[7] or None,
            "time_seconds": int(row[8] or 0),
            "sql": _normalize_query(row[9]),
            "is_probe_connection": pid == session.backend_pid,
        })
    return {
        **probe_session_metadata(session),
        "collected_at": datetime.now().isoformat(),
        "sessions": items,
    }


def terminate_backend(token: str, user_id: int, process_id: int) -> dict:
    session = _get_probe_session(token, user_id)
    try:
        target_id = int(process_id)
    except (TypeError, ValueError) as exc:
        raise SessionProbeError("invalid process id") from exc
    if target_id <= 0:
        raise SessionProbeError("invalid process id")
    if target_id == session.backend_pid:
        raise SessionProbeError("cannot terminate the session probe connection")
    try:
        with session.lock:
            with session.connection.cursor() as cursor:
                cursor.execute("SELECT pg_catalog.pg_terminate_backend(%s)", (target_id,))
                row = cursor.fetchone()
    except Exception as exc:
        raise SessionProbeError(f"terminate postgresql session failed: {exc}") from exc
    if not row or not bool(row[0]):
        raise SessionProbeError("postgresql session was not found or could not be terminated")
    return {"process_id": target_id, "terminated": True}
