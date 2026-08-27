import ipaddress
import threading
from datetime import datetime

from app.extensions import db
from app.models.db_asset import DatabaseInstance
from app.models.physical_discovery import (
    PhysicalDiscoveryConfig,
    PhysicalDiscoveryDetail,
    PhysicalDiscoveryRun,
    VCenterConfig,
)
from app.services.vcenter_readonly import ReadOnlyVCenterClient, resolve_physical_address
from app.utils.crypto import decrypt_secret


_RUN_LOCK = threading.Lock()


def _instance_ip(instance):
    value = str(instance.resolved_ip or instance.host_input or "").strip()
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def _in_cidrs(value, cidrs):
    address = ipaddress.ip_address(value)
    return any(address in ipaddress.ip_network(cidr, strict=False) for cidr in cidrs or [])


def _safe_error(exc):
    return str(exc).replace("\n", " ")[:500]


def _chunks(values, size):
    for offset in range(0, len(values), size):
        yield values[offset:offset + size]


def _vcenter_snapshot(row):
    return {
        "id": row.id,
        "name": row.name,
        "address": row.address,
        "port": row.port,
        "cidrs": list(row.cidrs_json or []),
        "username": row.username,
        "password_encrypted": row.password_encrypted,
        "verify_ssl": row.verify_ssl,
    }


def run_discovery(vcenter_id=None, trigger_type="scheduled", client_factory=ReadOnlyVCenterClient):
    if not _RUN_LOCK.acquire(blocking=False):
        raise RuntimeError("physical discovery is already running")
    try:
        query = VCenterConfig.query.filter_by(enabled=True, deleted=False)
        if vcenter_id is not None:
            query = query.filter_by(id=int(vcenter_id))
        vcenters = [_vcenter_snapshot(row) for row in query.order_by(VCenterConfig.id.asc()).all()]
        config = PhysicalDiscoveryConfig.query.first()
        batch_size = max(1, int(config.batch_size if config else 500))
        connect_timeout = max(1, int(config.connect_timeout_seconds if config else 10))
        db.session.rollback()

        last_run = None
        for vcenter in vcenters:
            last_run = _run_for_vcenter(vcenter, trigger_type, client_factory, batch_size, connect_timeout)
        return last_run
    finally:
        _RUN_LOCK.release()


def _target_snapshots(cidrs):
    targets = []
    rows = DatabaseInstance.query.filter_by(enabled=True).order_by(DatabaseInstance.id.asc()).all()
    for instance in rows:
        extra = instance.extra_json if isinstance(instance.extra_json, dict) else {}
        if str(extra.get("physical_discovery_mode") or "auto").lower() != "auto":
            continue
        value = _instance_ip(instance)
        if value and _in_cidrs(value, cidrs):
            targets.append({"id": instance.id, "name": instance.name, "ip": value})
    db.session.rollback()
    return targets


def _create_run(vcenter, trigger_type, total_count):
    run = PhysicalDiscoveryRun(
        vcenter_id=vcenter["id"],
        vcenter_name=vcenter["name"],
        trigger_type=trigger_type,
        status="running",
        started_at=datetime.utcnow(),
        total_count=total_count,
    )
    db.session.add(run)
    db.session.flush()
    run_id = run.id
    db.session.commit()
    return run_id


def _result_for_target(target, by_ip):
    fact = by_ip.get(target["ip"])
    if fact is None:
        return {
            **target,
            "status": "failed",
            "error_code": "VM_NOT_FOUND",
            "error_message": "virtual machine not found in vCenter",
        }
    try:
        return {**target, "status": "success", "physical_address": resolve_physical_address(fact)}
    except Exception as exc:
        return {
            **target,
            "status": "failed",
            "error_code": "ADDRESS_UNAVAILABLE",
            "error_message": _safe_error(exc),
        }


def _persist_result_batch(run_id, vcenter_name, results):
    success_count = 0
    failed_count = 0
    for result in results:
        if result["status"] == "success":
            instance = DatabaseInstance.query.filter_by(id=result["id"], enabled=True).first()
            extra = instance.extra_json if instance and isinstance(instance.extra_json, dict) else {}
            if instance is not None and str(extra.get("physical_discovery_mode") or "auto").lower() == "auto":
                updated = dict(extra)
                updated.update({
                    "physical_discovery_mode": "auto",
                    "physical_address": result["physical_address"],
                    "physical_discovery_source": vcenter_name,
                    "physical_discovered_at": datetime.utcnow().isoformat(),
                })
                instance.extra_json = updated
                success_count += 1
                detail = PhysicalDiscoveryDetail(
                    run_id=run_id, instance_id=result["id"], instance_name=result["name"],
                    input_ip=result["ip"], status="success",
                    discovered_address=result["physical_address"],
                )
            else:
                failed_count += 1
                detail = PhysicalDiscoveryDetail(
                    run_id=run_id, instance_id=result["id"], instance_name=result["name"],
                    input_ip=result["ip"], status="failed", error_code="INSTANCE_CHANGED",
                    error_message="instance is disabled or no longer uses automatic discovery",
                )
        else:
            failed_count += 1
            detail = PhysicalDiscoveryDetail(
                run_id=run_id, instance_id=result["id"], instance_name=result["name"],
                input_ip=result["ip"], status="failed", error_code=result["error_code"],
                error_message=result["error_message"],
            )
        db.session.add(detail)

    run = db.session.get(PhysicalDiscoveryRun, run_id)
    run.success_count += success_count
    run.failed_count += failed_count
    db.session.commit()


def _finish_run(run_id, error_message=None, failed_count=None):
    run = db.session.get(PhysicalDiscoveryRun, run_id)
    if error_message is not None:
        run.status = "failed"
        run.error_message = error_message
        if failed_count is not None:
            run.failed_count = failed_count
    else:
        run.status = "success" if run.failed_count == 0 else ("failed" if run.success_count == 0 else "partial_success")
    run.finished_at = datetime.utcnow()
    db.session.commit()
    return run


def _iter_client_facts(client):
    iterator = getattr(client, "iter_vm_host_facts", None)
    if callable(iterator):
        yield from iterator()
        return
    yield from client.query_vm_host_facts()


def _execute_run(vcenter, client_factory, batch_size, connect_timeout, targets, run_id):
    client = None
    pending_by_ip = {}
    for target in targets:
        pending_by_ip.setdefault(target["ip"], []).append(target)
    try:
        client = client_factory(
            address=vcenter["address"],
            port=vcenter["port"],
            username=vcenter["username"],
            password=decrypt_secret(vcenter["password_encrypted"]),
            verify_ssl=vcenter["verify_ssl"],
            timeout=connect_timeout,
        )
        for fact in _iter_client_facts(client):
            matched = []
            for value in fact.get("vm_ips", []):
                for target in pending_by_ip.pop(str(value), []):
                    matched.append(_result_for_target(target, {target["ip"]: fact}))
            if matched:
                _persist_result_batch(run_id, vcenter["name"], matched)

        unmatched = [
            _result_for_target(target, {})
            for targets_for_ip in pending_by_ip.values()
            for target in targets_for_ip
        ]
        for batch in _chunks(unmatched, batch_size):
            _persist_result_batch(run_id, vcenter["name"], batch)
        return _finish_run(run_id)
    except Exception as exc:
        db.session.rollback()
        run = db.session.get(PhysicalDiscoveryRun, run_id)
        failed_count = len(targets)
        if run is not None:
            failed_count = max(int(run.failed_count or 0), len(targets) - int(run.success_count or 0))
        return _finish_run(run_id, error_message=_safe_error(exc), failed_count=failed_count)
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


def _run_for_vcenter(vcenter, trigger_type, client_factory, batch_size, connect_timeout):
    targets = _target_snapshots(vcenter["cidrs"])
    run_id = _create_run(vcenter, trigger_type, len(targets))
    return _execute_run(vcenter, client_factory, batch_size, connect_timeout, targets, run_id)


def _run_async_worker(app, vcenter, client_factory, batch_size, connect_timeout, targets, run_id):
    try:
        with app.app_context():
            try:
                _execute_run(vcenter, client_factory, batch_size, connect_timeout, targets, run_id)
            finally:
                db.session.remove()
    finally:
        _RUN_LOCK.release()


def start_discovery_async(app, vcenter_id, trigger_type="manual", client_factory=ReadOnlyVCenterClient):
    if not _RUN_LOCK.acquire(blocking=False):
        raise RuntimeError("physical discovery is already running")
    run_id = None
    try:
        row = VCenterConfig.query.filter_by(id=int(vcenter_id), enabled=True, deleted=False).first()
        if row is None:
            raise ValueError("enabled vCenter not found")
        vcenter = _vcenter_snapshot(row)
        config = PhysicalDiscoveryConfig.query.first()
        batch_size = max(1, int(config.batch_size if config else 500))
        connect_timeout = max(1, int(config.connect_timeout_seconds if config else 10))
        targets = _target_snapshots(vcenter["cidrs"])
        run_id = _create_run(vcenter, trigger_type, len(targets))
        worker = threading.Thread(
            target=_run_async_worker,
            args=(app, vcenter, client_factory, batch_size, connect_timeout, targets, run_id),
            name=f"physical-discovery-{run_id}",
            daemon=True,
        )
        worker.start()
        return run_id
    except Exception as exc:
        db.session.rollback()
        if run_id is not None:
            _finish_run(run_id, error_message=_safe_error(exc))
        _RUN_LOCK.release()
        raise
