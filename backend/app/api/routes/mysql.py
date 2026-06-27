from flask import Blueprint, request

from datetime import datetime, timedelta

from app.api.routes.common import active_user_required
from app.extensions import db
from app.models.db_asset import DatabaseInstance
from app.models.monitor_snapshot import snapshot_model_for_instance
from app.services.monitor_snapshot_service import latest_snapshot_for_instance
from app.services.audit import log_audit
from app.services.collectors import collect_instance_metrics
from app.services.instance_service import create_instance, list_instances_paginated
from app.utils.crypto import decrypt_secret
from app.utils.response import error_response, ok_response

bp = Blueprint("mysql", __name__, url_prefix="/mysql")


def _infer_replication_role(payload):
    role = payload.get("replication_role")
    if role:
        return role

    io_running = payload.get("replica_io_running")
    sql_running = payload.get("replica_sql_running")
    lag = payload.get("seconds_behind_master")
    effective_read_only = payload.get("effective_read_only")
    read_only = payload.get("read_only")

    if io_running is True or sql_running is True or lag is not None:
        return "slave"
    if effective_read_only is True:
        return "read_only"
    if effective_read_only is False:
        return "master"
    if read_only is True:
        return "read_only"
    if read_only is False:
        return "master"
    return "unknown"


def _replication_view(instance_id, payload, source, running_status="unknown", collect_error=None):
    read_only = payload.get("read_only")
    super_read_only = payload.get("super_read_only")
    effective_read_only = payload.get("effective_read_only")
    if effective_read_only is None:
        if read_only is None and super_read_only is None:
            effective_read_only = None
        else:
            effective_read_only = bool(read_only is True or super_read_only is True)

    return {
        "instance_id": instance_id,
        "source": source,
        "running_status": running_status,
        "collect_error": collect_error,
        "collected_at": payload.get("collected_at"),
        "replication_role": _infer_replication_role({**payload, "effective_read_only": effective_read_only}),
        "mgr_member_role": payload.get("mgr_member_role"),
        "mgr_member_state": payload.get("mgr_member_state"),
        "mgr_group_name": payload.get("mgr_group_name"),
        "mgr_members": payload.get("mgr_members") or [],
        "read_only": read_only,
        "super_read_only": super_read_only,
        "effective_read_only": effective_read_only,
        "replica_io_running": payload.get("replica_io_running"),
        "replica_sql_running": payload.get("replica_sql_running"),
        "replica_source_host": payload.get("replica_source_host"),
        "replica_source_resolved_ip": payload.get("replica_source_resolved_ip"),
        "replica_source_port": payload.get("replica_source_port"),
        "seconds_behind_master": payload.get("seconds_behind_master"),
        "threads_running": payload.get("threads_running"),
        "threads_connected": payload.get("threads_connected"),
        "version": payload.get("version"),
        "node_exporter_status": payload.get("node_exporter_status"),
        "node_exporter_error": payload.get("node_exporter_error"),
        "host_cpu_cores": payload.get("host_cpu_cores"),
        "host_memory_total_bytes": payload.get("host_memory_total_bytes"),
        "host_cpu_usage_pct": payload.get("host_cpu_usage_pct"),
        "host_memory_usage_pct": payload.get("host_memory_usage_pct"),
        "host_data_disk_usage_pct": payload.get("host_data_disk_usage_pct"),
        "host_data_disk_mountpoint": payload.get("host_data_disk_mountpoint"),
        "host_data_disk_device": payload.get("host_data_disk_device"),
        "host_data_disk_size_bytes": payload.get("host_data_disk_size_bytes"),
        "host_disk_entries": payload.get("host_disk_entries"),
        "host_net_rates": payload.get("host_net_rates"),
    }


def _instance_detail_view(instance_id, payload, source, running_status="unknown", collect_error=None):
    uptime = payload.get("uptime")
    started_at = None
    if isinstance(uptime, int) and uptime >= 0:
        started_at = (datetime.now() - timedelta(seconds=uptime)).isoformat()

    return {
        "instance_id": instance_id,
        "source": source,
        "running_status": running_status,
        "collect_error": collect_error,
        "collected_at": payload.get("collected_at"),
        "started_at": started_at,
        "uptime": uptime,
        "version": payload.get("version"),
        "threads_connected": payload.get("threads_connected"),
        "threads_running": payload.get("threads_running"),
        "max_connections": payload.get("max_connections"),
        "lock_waits": payload.get("lock_waits"),
        "qps": payload.get("qps"),
        "tps": payload.get("tps"),
        "node_exporter_status": payload.get("node_exporter_status"),
        "node_exporter_error": payload.get("node_exporter_error"),
        "host_cpu_cores": payload.get("host_cpu_cores"),
        "host_memory_total_bytes": payload.get("host_memory_total_bytes"),
        "host_cpu_usage_pct": payload.get("host_cpu_usage_pct"),
        "host_memory_usage_pct": payload.get("host_memory_usage_pct"),
        "host_data_disk_usage_pct": payload.get("host_data_disk_usage_pct"),
        "host_data_disk_mountpoint": payload.get("host_data_disk_mountpoint"),
        "host_data_disk_device": payload.get("host_data_disk_device"),
        "host_data_disk_size_bytes": payload.get("host_data_disk_size_bytes"),
        "host_disk_entries": payload.get("host_disk_entries"),
        "host_net_rates": payload.get("host_net_rates"),
    }


@bp.get("/instances")
@active_user_required
def mysql_list_instances():
    page = request.args.get("page", 1)
    page_size = request.args.get("page_size", 20)
    keyword = request.args.get("keyword")
    cluster_id = request.args.get("cluster_id")
    namespace = request.args.get("namespace")
    business_line = request.args.get("business_line")
    environment = request.args.get("environment")
    items, total, page, page_size = list_instances_paginated(
        db_type="mysql",
        page=page,
        page_size=page_size,
        keyword=keyword,
        cluster_id=cluster_id,
        namespace=namespace,
        business_line=business_line,
        environment=environment,
    )
    return ok_response(
        data={
            "items": [item.to_dict() for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@bp.post("/instances")
@active_user_required
def mysql_create_instance():
    payload = request.get_json(silent=True) or {}
    payload.pop("role_label", None)
    payload.pop("is_read_only", None)

    instance, err = create_instance(payload, db_type="mysql")
    if err:
        return error_response(err, code=400)

    log_audit(user_id=None, action="mysql.instance.create", target_type="instance", target_id=str(instance.id), detail=payload)
    return ok_response(data=instance.to_dict(), code=201)


@bp.get("/instances/<int:instance_id>/replication")
@active_user_required
def mysql_replication(instance_id):
    instance = DatabaseInstance.query.filter_by(id=instance_id, db_type="mysql").first()
    if not instance:
        return error_response("mysql instance not found", code=404)

    refresh = request.args.get("refresh", "false").lower() == "true"

    snapshot = latest_snapshot_for_instance(instance_id=instance.id, db_type=instance.db_type, metric_type="status")
    snapshot_payload = snapshot.payload_json if snapshot else {}

    if refresh:
        password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
        live = collect_instance_metrics(instance=instance, password=password)
        if live.get("ok"):
            snapshot_model = snapshot_model_for_instance(instance)
            new_snapshot = snapshot_model(instance_id=instance.id, metric_type="status", payload_json=live)
            db.session.add(new_snapshot)
            instance.running_status = "running" if live.get("ping_ok") else "error"
            db.session.commit()
            running_status = instance.running_status
            return ok_response(data=_replication_view(instance.id, live, source="live", running_status=running_status))

        if snapshot_payload:
            instance.running_status = "error"
            db.session.commit()
            data = _replication_view(
                instance.id,
                snapshot_payload,
                source="snapshot",
                running_status="error",
                collect_error=live.get("error"),
            )
            return ok_response(data=data)

        return error_response(live.get("error", "collect failed"), code=502)

    if snapshot_payload:
        return ok_response(data=_replication_view(instance.id, snapshot_payload, source="snapshot", running_status=instance.running_status or "unknown"))
    return ok_response(data=_replication_view(instance.id, {}, source="none", running_status="unknown"))


@bp.get("/instances/<int:instance_id>/detail")
@active_user_required
def mysql_instance_detail(instance_id):
    instance = DatabaseInstance.query.filter_by(id=instance_id, db_type="mysql").first()
    if not instance:
        return error_response("mysql instance not found", code=404)

    refresh = request.args.get("refresh", "false").lower() == "true"
    snapshot = latest_snapshot_for_instance(instance_id=instance.id, db_type=instance.db_type, metric_type="status")
    snapshot_payload = snapshot.payload_json if snapshot else {}

    if refresh:
        password = decrypt_secret(instance.password_encrypted) if instance.password_encrypted else None
        live = collect_instance_metrics(instance=instance, password=password)
        if live.get("ok"):
            snapshot_model = snapshot_model_for_instance(instance)
            new_snapshot = snapshot_model(instance_id=instance.id, metric_type="status", payload_json=live)
            db.session.add(new_snapshot)
            instance.running_status = "running" if live.get("ping_ok") else "error"
            db.session.commit()
            running_status = instance.running_status
            return ok_response(data=_instance_detail_view(instance.id, live, source="live", running_status=running_status))

        if snapshot_payload:
            instance.running_status = "error"
            db.session.commit()
            return ok_response(
                data=_instance_detail_view(
                    instance.id,
                    snapshot_payload,
                    source="snapshot",
                    running_status="error",
                    collect_error=live.get("error"),
                )
            )
        return error_response(live.get("error", "collect failed"), code=502)

    if snapshot_payload:
        return ok_response(data=_instance_detail_view(instance.id, snapshot_payload, source="snapshot", running_status=instance.running_status or "unknown"))
    return ok_response(data=_instance_detail_view(instance.id, {}, source="none", running_status="unknown"))
