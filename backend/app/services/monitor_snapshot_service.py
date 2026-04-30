from typing import Dict, Iterable, List

from app.extensions import db
from app.models.monitor_snapshot import snapshot_model_for_db


def latest_snapshot_for_instance(instance_id: int, db_type: str, metric_type: str = "status"):
    model = snapshot_model_for_db(db_type)
    if not model:
        return None
    return (
        model.query
        .filter_by(instance_id=instance_id, metric_type=metric_type)
        .order_by(model.collected_at.desc(), model.id.desc())
        .first()
    )


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
    payload_by_instance = {}
    for row in snapshots:
        payload_by_instance[row.instance_id] = row.payload_json if isinstance(row.payload_json, dict) else {}
    return payload_by_instance
