from datetime import datetime

from flask import Blueprint

from app.api.routes.common import active_user_required
from app.extensions import db
from app.models.db_asset import DatabaseInstance
from app.models.monitor_snapshot import snapshot_model_for_instance
from app.services.monitor_snapshot_service import latest_snapshot_for_instance
from app.services.collectors import collect_instance_metrics
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
    snapshot_model = snapshot_model_for_instance(instance)
    snapshot = snapshot_model(instance_id=instance.id, metric_type="status", payload_json=payload)
    db.session.add(snapshot)
    db.session.commit()

    if not payload.get("ok"):
        return error_response(payload.get("error", "collect failed"), code=502)
    return ok_response(data=snapshot.to_dict())


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

