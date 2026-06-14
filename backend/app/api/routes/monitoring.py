from datetime import datetime

from flask import Blueprint, current_app, request

from app.api.routes.common import active_user_required
from app.extensions import db
from app.models.db_asset import DatabaseInstance
from app.models.monitor_snapshot import snapshot_model_for_db, snapshot_model_for_instance
from app.services.monitor_snapshot_service import latest_snapshot_for_instance, latest_snapshots_by_instance_ids
from app.services.collectors import collect_instance_metrics
from app.services.instance_service import list_instances as list_instances_by_type
from app.services.redis_cache import enqueue_snapshot_flush, set_latest_snapshot
from app.utils.crypto import decrypt_secret
from app.utils.response import error_response, ok_response

bp = Blueprint("monitoring", __name__, url_prefix="/monitoring")
FAIL_THRESHOLD_SECONDS = 120


def _snapshot_failed(payload: dict) -> bool:
    if not isinstance(payload, dict):
        return True
    if payload.get("ok") is False:
        return True
    # 运行情况只认 SELECT 1 结果
    if payload.get("ping_ok") is False:
        return True
    return False


@bp.post("/collect/<int:instance_id>")
@active_user_required
def collect_now(instance_id):
    instance = DatabaseInstance.query.get_or_404(instance_id)

    password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
    data = collect_instance_metrics(instance=instance, password=password)
    payload = dict(data or {})
    payload.setdefault("ok", False)
    payload.setdefault("collected_at", datetime.now().isoformat())

    instance.running_status = "running" if payload.get("ok") and payload.get("ping_ok") else "error"
    collected_at = datetime.now()
    set_latest_snapshot(
        db_type=instance.db_type,
        instance_id=instance.id,
        metric_type="status",
        payload_json=payload,
        collected_at=collected_at,
        running_status=instance.running_status,
    )
    enqueue_snapshot_flush(
        app=current_app._get_current_object(),
        db_type=instance.db_type,
        instance_id=instance.id,
        metric_type="status",
        payload_json=payload,
        collected_at=collected_at,
    )
    db.session.commit()

    if not payload.get("ok"):
        return error_response(payload.get("error", "collect failed"), code=502)
    snapshot = latest_snapshot_for_instance(instance_id=instance.id, db_type=instance.db_type, metric_type="status")
    return ok_response(data=snapshot.to_dict() if snapshot else {})


@bp.get("/latest/<int:instance_id>")
@active_user_required
def latest_snapshot(instance_id):
    instance = DatabaseInstance.query.get_or_404(instance_id)
    snapshot = latest_snapshot_for_instance(instance_id=instance.id, db_type=instance.db_type, metric_type="status")
    if not snapshot:
        return error_response("snapshot not found", code=404)
    return ok_response(data=snapshot.to_dict())


@bp.get("/instance/<int:instance_id>/health")
@active_user_required
def get_instance_health(instance_id):
    """获取实例最新健康状态（从数据库读取）"""
    instance = DatabaseInstance.query.get_or_404(instance_id)

    latest_snapshot = latest_snapshot_for_instance(instance_id=instance.id, db_type=instance.db_type, metric_type="status")

    if not latest_snapshot:
        return ok_response(
            data={
                "instance_id": instance.id,
                "instance_name": instance.name,
                "running_status": "unknown",
                "collected_at": None,
                "payload_json": {},
                "latest_failed": False,
                "stale_failed": False,
                "seconds_since_base": None,
            }
        )

    payload_json = latest_snapshot.payload_json or {}
    latest_failed = _snapshot_failed(payload_json)

    last_success_snapshot = None
    snapshot_model = snapshot_model_for_instance(instance)
    recent = (
        snapshot_model.query
        .filter_by(instance_id=instance_id, metric_type="status")
        .order_by(snapshot_model.collected_at.desc(), snapshot_model.id.desc())
        .limit(240)
        .all()
    )
    for snap in recent:
        if not _snapshot_failed(snap.payload_json or {}):
            last_success_snapshot = snap
            break

    now = datetime.now()
    base = last_success_snapshot.collected_at if last_success_snapshot else latest_snapshot.collected_at
    seconds_since_base = int((now - base).total_seconds()) if base else None
    stale_failed = bool(latest_failed and seconds_since_base is not None and seconds_since_base > FAIL_THRESHOLD_SECONDS)

    ping_ok = payload_json.get("ping_ok")
    if ping_ok is True:
        running_status = "running"
    elif stale_failed:
        running_status = "error"
    else:
        # 最新采集失败但未超过阈值，按未知显示，避免瞬时抖动
        running_status = "unknown"
    exposed_payload = payload_json

    return ok_response(
        data={
            "instance_id": instance.id,
            "instance_name": instance.name,
            "running_status": running_status,
            "collected_at": latest_snapshot.collected_at.isoformat() if latest_snapshot.collected_at else None,
            "payload_json": exposed_payload,
            "latest_failed": latest_failed,
            "stale_failed": stale_failed,
            "seconds_since_base": seconds_since_base,
        }
    )


@bp.post("/instances/health")
@active_user_required
def get_instances_health():
    """批量获取实例最新健康状态，减少前端 N+1 请求。"""
    payload = request.get_json(silent=True) or {}
    db_type = str(payload.get("db_type") or "").strip().lower()
    if db_type not in {"mysql", "mongodb", "redis", "doris"}:
        return error_response("invalid db_type", code=400)

    raw_ids = payload.get("instance_ids")
    if not isinstance(raw_ids, list):
        return error_response("instance_ids must be a list", code=400)

    instance_ids = []
    for item in raw_ids:
        try:
            instance_ids.append(int(item))
        except (TypeError, ValueError):
            continue
    if not instance_ids:
        return ok_response(data={})

    requested_ids = set(instance_ids)
    rows = [
        item
        for item in list_instances_by_type(db_type=db_type)
        if int(item["id"] if isinstance(item, dict) else item.id) in requested_ids
    ]
    if not rows:
        return ok_response(data={})

    def _row_id(row):
        return int(row["id"] if isinstance(row, dict) else row.id)

    def _row_status(row):
        if isinstance(row, dict):
            return row.get("running_status") or "unknown"
        return row.running_status or "unknown"

    row_ids = [_row_id(row) for row in rows]
    status_by_id = {_row_id(row): _row_status(row) for row in rows}
    latest_snapshot_by_id = latest_snapshots_by_instance_ids(db_type=db_type, instance_ids=row_ids, metric_type="status")

    last_success_by_id = {}
    snapshot_model = snapshot_model_for_db(db_type)
    if snapshot_model:
        recent_snapshots = (
            snapshot_model.query
            .filter(snapshot_model.instance_id.in_(row_ids), snapshot_model.metric_type == "status")
            .order_by(snapshot_model.instance_id.asc(), snapshot_model.collected_at.desc(), snapshot_model.id.desc())
            .limit(max(1, len(row_ids)) * 240)
            .all()
        )
        for snap in recent_snapshots:
            if snap.instance_id in last_success_by_id:
                continue
            if not _snapshot_failed(snap.payload_json or {}):
                last_success_by_id[snap.instance_id] = snap

    snapshot_payload_by_id = {}
    now = datetime.now()
    for row in rows:
        row_id = _row_id(row)
        snapshot = latest_snapshot_by_id.get(row_id)
        if not snapshot:
            continue
        payload_json = snapshot.payload_json if isinstance(snapshot.payload_json, dict) else {}
        latest_failed = _snapshot_failed(payload_json)
        last_success_snapshot = last_success_by_id.get(row_id)
        base = last_success_snapshot.collected_at if last_success_snapshot else snapshot.collected_at
        seconds_since_base = int((now - base).total_seconds()) if base else None
        stale_failed = bool(latest_failed and seconds_since_base is not None and seconds_since_base > FAIL_THRESHOLD_SECONDS)
        ping_ok = payload_json.get("ping_ok")
        if ping_ok is True:
            running_status = "running"
        elif stale_failed:
            running_status = "error"
        else:
            running_status = "unknown"
        snapshot_payload_by_id[row_id] = {
            "running_status": running_status,
            "collected_at": snapshot.collected_at.isoformat() if snapshot.collected_at else None,
            "payload_json": payload_json,
            "latest_failed": latest_failed,
            "stale_failed": stale_failed,
            "seconds_since_base": seconds_since_base,
        }

    result = {}
    for row in rows:
        row_id = _row_id(row)
        result[row_id] = snapshot_payload_by_id.get(row_id) or {
            "running_status": status_by_id.get(row_id, "unknown"),
            "collected_at": None,
            "payload_json": {},
            "latest_failed": False,
            "stale_failed": False,
            "seconds_since_base": None,
        }
    return ok_response(data=result)
