import ipaddress
import threading
from datetime import datetime

from app.extensions import db
from app.models.db_asset import DatabaseInstance
from app.models.physical_discovery import PhysicalDiscoveryDetail, PhysicalDiscoveryRun, VCenterConfig
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


def run_discovery(vcenter_id=None, trigger_type="scheduled", client_factory=ReadOnlyVCenterClient):
    if not _RUN_LOCK.acquire(blocking=False):
        raise RuntimeError("physical discovery is already running")
    try:
        query = VCenterConfig.query.filter_by(enabled=True, deleted=False)
        if vcenter_id is not None:
            query = query.filter_by(id=int(vcenter_id))
        vcenters = query.order_by(VCenterConfig.id.asc()).all()
        last_run = None
        for vcenter in vcenters:
            last_run = _run_for_vcenter(vcenter, trigger_type, client_factory)
        return last_run
    finally:
        _RUN_LOCK.release()


def _run_for_vcenter(vcenter, trigger_type, client_factory):
    started = datetime.utcnow()
    instances = []
    for instance in DatabaseInstance.query.filter_by(enabled=True).order_by(DatabaseInstance.id.asc()).all():
        extra = instance.extra_json if isinstance(instance.extra_json, dict) else {}
        if str(extra.get("physical_discovery_mode") or "auto").lower() != "auto":
            continue
        value = _instance_ip(instance)
        if value and _in_cidrs(value, vcenter.cidrs_json):
            instances.append((instance, value))

    run = PhysicalDiscoveryRun(
        vcenter_id=vcenter.id,
        vcenter_name=vcenter.name,
        trigger_type=trigger_type,
        status="running",
        started_at=started,
        total_count=len(instances),
    )
    db.session.add(run)
    db.session.flush()
    client = None
    try:
        client = client_factory(
            address=vcenter.address,
            port=vcenter.port,
            username=vcenter.username,
            password=decrypt_secret(vcenter.password_encrypted),
            verify_ssl=vcenter.verify_ssl,
        )
        facts = client.query_vm_host_facts()
        by_ip = {str(value): fact for fact in facts for value in fact.get("vm_ips", [])}
        for instance, value in instances:
            fact = by_ip.get(value)
            if fact is None:
                run.failed_count += 1
                db.session.add(PhysicalDiscoveryDetail(
                    run_id=run.id, instance_id=instance.id, instance_name=instance.name, input_ip=value,
                    status="failed", error_code="VM_NOT_FOUND", error_message="virtual machine not found in vCenter",
                ))
                continue
            try:
                physical_address = resolve_physical_address(fact)
                extra = dict(instance.extra_json or {})
                extra.update({
                    "physical_discovery_mode": "auto",
                    "physical_address": physical_address,
                    "physical_discovery_source": vcenter.name,
                    "physical_discovered_at": datetime.utcnow().isoformat(),
                })
                instance.extra_json = extra
                run.success_count += 1
                db.session.add(PhysicalDiscoveryDetail(
                    run_id=run.id, instance_id=instance.id, instance_name=instance.name, input_ip=value,
                    status="success", discovered_address=physical_address,
                ))
            except Exception as exc:
                run.failed_count += 1
                db.session.add(PhysicalDiscoveryDetail(
                    run_id=run.id, instance_id=instance.id, instance_name=instance.name, input_ip=value,
                    status="failed", error_code="ADDRESS_UNAVAILABLE", error_message=_safe_error(exc),
                ))
        run.status = "success" if run.failed_count == 0 else ("failed" if run.success_count == 0 else "partial_success")
    except Exception as exc:
        run.status = "failed"
        run.failed_count = len(instances)
        run.error_message = _safe_error(exc)
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        run.finished_at = datetime.utcnow()
        db.session.commit()
    return run
