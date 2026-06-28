from typing import Dict, Iterable, List

from app.extensions import db
from app.models.db_asset import DatabaseInstance
from app.models.monitor_snapshot import snapshot_model_for_db
from app.services.redis_cache import (
    get_last_success_snapshot,
    get_last_success_snapshots,
    get_latest_snapshot,
    get_latest_snapshots,
    set_last_success_snapshot,
    set_latest_snapshot,
)


def latest_snapshot_for_instance(instance_id: int, db_type: str, metric_type: str = "status"):
    cached = get_latest_snapshot(db_type=db_type, instance_id=instance_id, metric_type=metric_type)
    if cached:
        return cached
    model = snapshot_model_for_db(db_type)
    if not model:
        return None
    snapshot = (
        model.query
        .filter_by(instance_id=instance_id, metric_type=metric_type)
        .order_by(model.collected_at.desc(), model.id.desc())
        .first()
    )
    if snapshot:
        set_latest_snapshot(
            db_type=db_type,
            instance_id=instance_id,
            metric_type=metric_type,
            payload_json=snapshot.payload_json if isinstance(snapshot.payload_json, dict) else {},
            collected_at=snapshot.collected_at,
        )
    return snapshot


def latest_payload_by_instance_ids(
    db_type: str,
    instance_ids: Iterable[int],
    metric_type: str = "status",
) -> Dict[int, dict]:
    model = snapshot_model_for_db(db_type)
    if not model:
        return {}
    ids: List[int] = [int(item) for item in instance_ids if item is not None]
    if not ids:
        return {}
    cached = get_latest_snapshots(db_type=db_type, instance_ids=ids, metric_type=metric_type)
    missing_ids = [item for item in ids if item not in cached]
    if not missing_ids:
        return {
            instance_id: (snapshot.payload_json if isinstance(snapshot.payload_json, dict) else {})
            for instance_id, snapshot in cached.items()
        }

    latest_ids = (
        db.session.query(
            model.instance_id,
            db.func.max(model.id).label("max_id"),
        )
        .filter(model.instance_id.in_(missing_ids), model.metric_type == metric_type)
        .group_by(model.instance_id)
        .subquery()
    )
    snapshots = (
        db.session.query(model)
        .join(latest_ids, model.id == latest_ids.c.max_id)
        .all()
    )
    payload_by_instance = {}
    for instance_id, snapshot in cached.items():
        payload_by_instance[instance_id] = snapshot.payload_json if isinstance(snapshot.payload_json, dict) else {}
    for row in snapshots:
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        payload_by_instance[row.instance_id] = payload
        set_latest_snapshot(db_type=db_type, instance_id=row.instance_id, metric_type=metric_type, payload_json=payload, collected_at=row.collected_at)
    return payload_by_instance


def latest_snapshots_by_instance_ids(
    db_type: str,
    instance_ids: Iterable[int],
    metric_type: str = "status",
):
    model = snapshot_model_for_db(db_type)
    if not model:
        return {}
    ids: List[int] = [int(item) for item in instance_ids if item is not None]
    if not ids:
        return {}
    cached = get_latest_snapshots(db_type=db_type, instance_ids=ids, metric_type=metric_type)
    missing_ids = [item for item in ids if item not in cached]
    if not missing_ids:
        return cached

    latest_ids = (
        db.session.query(
            model.instance_id,
            db.func.max(model.id).label("max_id"),
        )
        .filter(model.instance_id.in_(missing_ids), model.metric_type == metric_type)
        .group_by(model.instance_id)
        .subquery()
    )
    snapshots = (
        db.session.query(model)
        .join(latest_ids, model.id == latest_ids.c.max_id)
        .all()
    )
    result = dict(cached)
    for row in snapshots:
        result[row.instance_id] = row
        set_latest_snapshot(
            db_type=db_type,
            instance_id=row.instance_id,
            metric_type=metric_type,
            payload_json=row.payload_json if isinstance(row.payload_json, dict) else {},
            collected_at=row.collected_at,
        )
    return result


def _snapshot_succeeded(payload: dict) -> bool:
    return isinstance(payload, dict) and payload.get("ok") is not False and payload.get("ping_ok") is not False


def latest_success_snapshot_for_instance(instance_id: int, db_type: str, metric_type: str = "status"):
    cached = get_last_success_snapshot(db_type=db_type, instance_id=instance_id, metric_type=metric_type)
    if cached:
        return cached
    model = snapshot_model_for_db(db_type)
    if not model:
        return None
    recent = (
        model.query
        .filter_by(instance_id=instance_id, metric_type=metric_type)
        .order_by(model.collected_at.desc(), model.id.desc())
        .limit(240)
        .all()
    )
    snapshot = next((row for row in recent if _snapshot_succeeded(row.payload_json or {})), None)
    if snapshot:
        set_last_success_snapshot(
            db_type=db_type,
            instance_id=instance_id,
            metric_type=metric_type,
            payload_json=snapshot.payload_json if isinstance(snapshot.payload_json, dict) else {},
            collected_at=snapshot.collected_at,
        )
    return snapshot


def latest_success_snapshots_by_instance_ids(
    db_type: str,
    instance_ids: Iterable[int],
    metric_type: str = "status",
):
    ids: List[int] = [int(item) for item in instance_ids if item is not None]
    if not ids:
        return {}
    result = get_last_success_snapshots(db_type=db_type, instance_ids=ids, metric_type=metric_type)
    model = snapshot_model_for_db(db_type)
    if not model:
        return result
    for instance_id in (item for item in ids if item not in result):
        recent = (
            model.query
            .filter_by(instance_id=instance_id, metric_type=metric_type)
            .order_by(model.collected_at.desc(), model.id.desc())
            .limit(240)
            .all()
        )
        snapshot = next((row for row in recent if _snapshot_succeeded(row.payload_json or {})), None)
        if not snapshot:
            continue
        result[instance_id] = snapshot
        set_last_success_snapshot(
            db_type=db_type,
            instance_id=instance_id,
            metric_type=metric_type,
            payload_json=snapshot.payload_json if isinstance(snapshot.payload_json, dict) else {},
            collected_at=snapshot.collected_at,
        )
    return result


def warm_latest_snapshot_cache(metric_types=("status", "inspection")) -> int:
    rows = DatabaseInstance.query.filter_by(enabled=True).all()
    if not rows:
        return 0

    warmed = 0
    rows_by_type = {}
    status_by_id = {}
    for row in rows:
        rows_by_type.setdefault(row.db_type, []).append(row)
        status_by_id[row.id] = row.running_status or "unknown"

    for db_type, instances in rows_by_type.items():
        model = snapshot_model_for_db(db_type)
        if not model:
            continue
        ids = [row.id for row in instances]
        for metric_type in metric_types:
            latest_ids = (
                db.session.query(
                    model.instance_id,
                    db.func.max(model.id).label("max_id"),
                )
                .filter(model.instance_id.in_(ids), model.metric_type == metric_type)
                .group_by(model.instance_id)
                .subquery()
            )
            snapshots = (
                db.session.query(model)
                .join(latest_ids, model.id == latest_ids.c.max_id)
                .all()
            )
            for snapshot in snapshots:
                set_latest_snapshot(
                    db_type=db_type,
                    instance_id=snapshot.instance_id,
                    metric_type=metric_type,
                    payload_json=snapshot.payload_json if isinstance(snapshot.payload_json, dict) else {},
                    collected_at=snapshot.collected_at,
                    running_status=status_by_id.get(snapshot.instance_id) if metric_type == "status" else None,
                )
                warmed += 1
    return warmed
