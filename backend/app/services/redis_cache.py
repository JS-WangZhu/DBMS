import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from types import SimpleNamespace
from typing import Iterable, Optional

import redis
from flask import current_app, has_app_context

from app.extensions import db
from app.models.monitor_snapshot import snapshot_model_for_db


_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="redis-cache-flush")
_CLIENT = None
_CLIENT_CONFIG = None

KEY_QUERY_OPS = "dbms:config:data_query_ops"
KEY_INSTANCE_LIST_PREFIX = "dbms:instances:list"
KEY_INSTANCE_STATUS_PREFIX = "dbms:instance_status"
KEY_SNAPSHOT_PREFIX = "dbms:latest_snapshot"
KEY_LAST_SUCCESS_SNAPSHOT_PREFIX = "dbms:last_success_snapshot"
LATEST_SNAPSHOT_TTL_SECONDS = 600
KEY_INSPECTION_SUMMARY = "dbms:inspection:last_summary"


def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _loads(raw):
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def get_client():
    global _CLIENT, _CLIENT_CONFIG
    if not has_app_context():
        return None
    cfg = (
        current_app.config.get("REDIS_HOST", "127.0.0.1"),
        int(current_app.config.get("REDIS_PORT", 6379)),
        int(current_app.config.get("REDIS_DB", 0)),
        current_app.config.get("REDIS_PASSWORD") or None,
    )
    if _CLIENT is not None and _CLIENT_CONFIG == cfg:
        return _CLIENT
    try:
        client = redis.Redis(
            host=cfg[0],
            port=cfg[1],
            db=cfg[2],
            password=cfg[3],
            socket_connect_timeout=0.3,
            socket_timeout=0.8,
            decode_responses=True,
        )
        client.ping()
    except Exception as exc:
        try:
            current_app.logger.debug("redis cache unavailable: %s", exc)
        except Exception:
            pass
        _CLIENT = None
        _CLIENT_CONFIG = cfg
        return None
    _CLIENT = client
    _CLIENT_CONFIG = cfg
    return _CLIENT


def get_json(key: str):
    client = get_client()
    if not client:
        return None
    try:
        return _loads(client.get(key))
    except Exception:
        return None


def set_json(key: str, value, ex: Optional[int] = None) -> bool:
    client = get_client()
    if not client:
        return False
    try:
        payload = json.dumps(value, ensure_ascii=False, default=_json_default)
        client.set(key, payload, ex=ex)
        return True
    except Exception:
        return False


def delete(*keys: str) -> None:
    client = get_client()
    if not client or not keys:
        return
    try:
        client.delete(*keys)
    except Exception:
        pass


def delete_pattern(pattern: str) -> None:
    client = get_client()
    if not client:
        return
    try:
        keys = list(client.scan_iter(match=pattern, count=200))
        if keys:
            client.delete(*keys)
    except Exception:
        pass


def snapshot_key(db_type: str, instance_id: int, metric_type: str = "status") -> str:
    return f"{KEY_SNAPSHOT_PREFIX}:{db_type}:{metric_type}:{int(instance_id)}"


def last_success_snapshot_key(db_type: str, instance_id: int, metric_type: str = "status") -> str:
    return f"{KEY_LAST_SUCCESS_SNAPSHOT_PREFIX}:{db_type}:{metric_type}:{int(instance_id)}"


def instance_status_key(instance_id: int) -> str:
    return f"{KEY_INSTANCE_STATUS_PREFIX}:{int(instance_id)}"


class CachedSnapshot(SimpleNamespace):
    def to_dict(self) -> dict:
        return {
            "id": getattr(self, "id", None),
            "instance_id": self.instance_id,
            "metric_type": self.metric_type,
            "payload_json": self.payload_json if isinstance(self.payload_json, dict) else {},
            "collected_at": self.collected_at.isoformat() if self.collected_at else None,
        }


def _parse_datetime(value):
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def cached_snapshot_from_dict(data: dict):
    if not isinstance(data, dict):
        return None
    try:
        instance_id = int(data.get("instance_id"))
    except (TypeError, ValueError):
        return None
    return CachedSnapshot(
        id=data.get("id"),
        instance_id=instance_id,
        metric_type=data.get("metric_type") or "status",
        payload_json=data.get("payload_json") if isinstance(data.get("payload_json"), dict) else {},
        collected_at=_parse_datetime(data.get("collected_at")),
    )


def set_last_success_snapshot(
    db_type: str,
    instance_id: int,
    metric_type: str,
    payload_json: dict,
    collected_at: Optional[datetime] = None,
) -> bool:
    collected_at = collected_at or datetime.now()
    return set_json(
        last_success_snapshot_key(db_type, instance_id, metric_type),
        {
            "id": None,
            "instance_id": int(instance_id),
            "db_type": db_type,
            "metric_type": metric_type,
            "payload_json": payload_json if isinstance(payload_json, dict) else {},
            "collected_at": collected_at.isoformat(),
        },
        ex=LATEST_SNAPSHOT_TTL_SECONDS,
    )


def set_latest_snapshot(
    db_type: str,
    instance_id: int,
    metric_type: str,
    payload_json: dict,
    collected_at: Optional[datetime] = None,
    running_status: Optional[str] = None,
) -> bool:
    collected_at = collected_at or datetime.now()
    payload = {
        "id": None,
        "instance_id": int(instance_id),
        "db_type": db_type,
        "metric_type": metric_type,
        "payload_json": payload_json if isinstance(payload_json, dict) else {},
        "collected_at": collected_at.isoformat(),
    }
    ok = set_json(snapshot_key(db_type, instance_id, metric_type), payload, ex=LATEST_SNAPSHOT_TTL_SECONDS)
    snapshot_payload = payload["payload_json"]
    succeeded = snapshot_payload.get("ok") is not False and snapshot_payload.get("ping_ok") is not False
    if metric_type == "status" and succeeded:
        set_last_success_snapshot(
            db_type=db_type,
            instance_id=instance_id,
            metric_type=metric_type,
            payload_json=snapshot_payload,
            collected_at=collected_at,
        )
    if metric_type == "status" and running_status:
        set_json(
            instance_status_key(instance_id),
            {
                "instance_id": int(instance_id),
                "db_type": db_type,
                "running_status": running_status,
                "collected_at": collected_at.isoformat(),
                "payload_json": payload["payload_json"],
            },
            ex=LATEST_SNAPSHOT_TTL_SECONDS,
        )
    return ok


def get_latest_snapshot(db_type: str, instance_id: int, metric_type: str = "status"):
    return cached_snapshot_from_dict(get_json(snapshot_key(db_type, instance_id, metric_type)))


def get_last_success_snapshot(db_type: str, instance_id: int, metric_type: str = "status"):
    return cached_snapshot_from_dict(get_json(last_success_snapshot_key(db_type, instance_id, metric_type)))


def get_last_success_snapshots(db_type: str, instance_ids: Iterable[int], metric_type: str = "status") -> dict:
    client = get_client()
    ids = [int(item) for item in instance_ids if item is not None]
    if not client or not ids:
        return {}
    try:
        keys = [last_success_snapshot_key(db_type, item, metric_type) for item in ids]
        values = client.mget(keys)
    except Exception:
        return {}
    result = {}
    for raw in values:
        snap = cached_snapshot_from_dict(_loads(raw))
        if snap:
            result[snap.instance_id] = snap
    return result


def get_latest_snapshots(db_type: str, instance_ids: Iterable[int], metric_type: str = "status") -> dict:
    client = get_client()
    ids = [int(item) for item in instance_ids if item is not None]
    if not client or not ids:
        return {}
    try:
        keys = [snapshot_key(db_type, item, metric_type) for item in ids]
        values = client.mget(keys)
    except Exception:
        return {}
    result = {}
    for raw in values:
        snap = cached_snapshot_from_dict(_loads(raw))
        if snap:
            result[snap.instance_id] = snap
    return result


def enqueue_snapshot_flush(app, db_type: str, instance_id: int, metric_type: str, payload_json: dict, collected_at=None):
    if app is None:
        return
    collected_iso = (collected_at or datetime.now()).isoformat() if isinstance(collected_at, datetime) else str(collected_at or datetime.now().isoformat())
    payload = payload_json if isinstance(payload_json, dict) else {}

    def _flush():
        with app.app_context():
            model = snapshot_model_for_db(db_type)
            if not model:
                return
            try:
                db.session.add(
                    model(
                        instance_id=int(instance_id),
                        metric_type=metric_type,
                        payload_json=payload,
                        collected_at=_parse_datetime(collected_iso) or datetime.now(),
                    )
                )
                db.session.commit()
            except Exception as exc:
                db.session.rollback()
                try:
                    current_app.logger.exception("async snapshot flush failed: %s", exc)
                except Exception:
                    pass

    _EXECUTOR.submit(_flush)
