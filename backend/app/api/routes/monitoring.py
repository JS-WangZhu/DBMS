from datetime import datetime

import math

from flask import Blueprint, current_app, request

from app.api.routes.common import active_user_required, require_menu_permission
from app.extensions import db
from app.models.db_asset import DatabaseInstance
from app.services.monitor_snapshot_service import (
    latest_snapshot_for_instance,
    latest_snapshots_by_instance_ids,
    latest_success_snapshot_for_instance,
    latest_success_snapshots_by_instance_ids,
    snapshot_history_for_instance,
)
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


@bp.get("/instance/<int:instance_id>/performance")
@require_menu_permission("mysql_instance_detail")
def get_instance_performance(instance_id):
    instance = DatabaseInstance.query.get_or_404(instance_id)
    if instance.db_type != "mysql":
        return error_response("performance detail currently supports mysql only", code=400)
    try:
        hours = int(request.args.get("hours", "24"))
    except (TypeError, ValueError):
        return error_response("hours must be an integer", code=400)
    hours = min(max(hours, 1), 168)
    rows = snapshot_history_for_instance(
        instance_id=instance.id,
        db_type=instance.db_type,
        metric_type="status",
        hours=hours,
    )
    # Seven days at a 30-second interval can exceed 20,000 rows. Preserve the
    # time range while bounding the response size rendered by the browser.
    if len(rows) > 2000:
        step = math.ceil(len(rows) / 2000)
        sampled = rows[::step]
        if sampled[-1].id != rows[-1].id:
            sampled.append(rows[-1])
        rows = sampled
    points = []
    for row in rows:
        payload = row.payload_json if isinstance(row.payload_json, dict) else {}
        net_rates = payload.get("host_net_rates") if isinstance(payload.get("host_net_rates"), list) else []
        def _sum_rate(key):
            total = 0.0
            found = False
            for item in net_rates:
                if not isinstance(item, dict) or item.get(key) is None:
                    continue
                try:
                    total += float(item[key])
                    found = True
                except (TypeError, ValueError):
                    continue
            return round(total, 2) if found else None

        rx_bps = _sum_rate("rx_bps")
        tx_bps = _sum_rate("tx_bps")
        points.append({
            "collected_at": row.collected_at.isoformat() if row.collected_at else None,
            "cpu_usage_pct": payload.get("host_cpu_usage_pct"),
            "memory_usage_pct": payload.get("host_memory_usage_pct"),
            "disk_usage_pct": payload.get("host_data_disk_usage_pct"),
            "disk_io_latency_ms": payload.get("host_disk_io_latency_ms"),
            "network_rx_bps": rx_bps,
            "network_tx_bps": tx_bps,
            "sessions": payload.get("threads_connected"),
            "running_sessions": payload.get("threads_running"),
            "lock_waits": payload.get("lock_waits"),
        })
    return ok_response(data={
        "instance": {
            "id": instance.id,
            "name": instance.name,
            "host": instance.resolved_ip or instance.host_input,
            "port": instance.port,
        },
        "hours": hours,
        "points": points,
    })


@bp.get("/instance/<int:instance_id>/health")
@active_user_required
def get_instance_health(instance_id):
    """获取实例最新健康状态（缓存优先，数据库兜底）"""
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
    if latest_failed:
        last_success_snapshot = latest_success_snapshot_for_instance(
            instance_id=instance.id,
            db_type=instance.db_type,
            metric_type="status",
        )

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
    if db_type not in {"mysql", "mongodb", "redis", "postgresql", "doris"}:
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

    failed_ids = [
        instance_id
        for instance_id, snapshot in latest_snapshot_by_id.items()
        if _snapshot_failed(snapshot.payload_json if isinstance(snapshot.payload_json, dict) else {})
    ]
    last_success_by_id = latest_success_snapshots_by_instance_ids(
        db_type=db_type,
        instance_ids=failed_ids,
        metric_type="status",
    ) if failed_ids else {}

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
