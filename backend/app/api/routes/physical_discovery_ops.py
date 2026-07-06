from datetime import datetime

from flask import Blueprint, request

from app.api.routes.common import active_user_required, require_menu_permission
from app.extensions import db
from app.models.physical_discovery import PhysicalDiscoveryDetail, PhysicalDiscoveryRun, VCenterConfig
from app.services.physical_discovery import run_discovery
from app.services.physical_discovery_config import normalize_cidrs, validate_non_overlapping_cidrs
from app.services.vcenter_readonly import ReadOnlyVCenterClient
from app.utils.crypto import decrypt_secret, encrypt_secret
from app.utils.response import error_response, ok_response


bp = Blueprint("physical_discovery_ops", __name__, url_prefix="/physical-discovery")


@bp.patch("/vcenters/<int:vcenter_id>")
@require_menu_permission("physical_discovery_manage")
def update_vcenter(vcenter_id):
    row = VCenterConfig.query.filter_by(id=vcenter_id, deleted=False).first_or_404()
    payload = request.get_json(silent=True) or {}
    if "cidrs" in payload:
        try:
            cidrs = normalize_cidrs(payload["cidrs"])
            existing = [(item.id, item.cidrs_json or []) for item in VCenterConfig.query.filter_by(deleted=False).all()]
            validate_non_overlapping_cidrs(cidrs, existing, exclude_id=row.id)
            row.cidrs_json = cidrs
        except ValueError as exc:
            return error_response(str(exc), code=400)
    for field in ("name", "address", "username"):
        if field in payload:
            setattr(row, field, str(payload[field] or "").strip())
    if "port" in payload:
        row.port = int(payload["port"])
    if "enabled" in payload:
        row.enabled = bool(payload["enabled"])
    if "verify_ssl" in payload:
        row.verify_ssl = bool(payload["verify_ssl"])
    if payload.get("password"):
        row.password_encrypted = encrypt_secret(str(payload["password"]))
    db.session.commit()
    return ok_response(data=row.to_dict())


@bp.delete("/vcenters/<int:vcenter_id>")
@require_menu_permission("physical_discovery_manage")
def delete_vcenter(vcenter_id):
    row = VCenterConfig.query.filter_by(id=vcenter_id, deleted=False).first_or_404()
    row.deleted = True
    row.enabled = False
    db.session.commit()
    return ok_response(data={"id": row.id})


@bp.post("/vcenters/<int:vcenter_id>/test")
@require_menu_permission("physical_discovery_manage")
def test_vcenter(vcenter_id):
    row = VCenterConfig.query.filter_by(id=vcenter_id, deleted=False).first_or_404()
    client = None
    try:
        client = ReadOnlyVCenterClient(
            address=row.address, port=row.port, username=row.username,
            password=decrypt_secret(row.password_encrypted), verify_ssl=row.verify_ssl,
        )
        client.query_vm_host_facts()
        row.last_test_status = "success"
        row.last_test_message = "read-only query succeeded"
    except Exception as exc:
        row.last_test_status = "failed"
        row.last_test_message = str(exc).replace("\n", " ")[:500]
    finally:
        if client:
            client.close()
        row.last_tested_at = datetime.utcnow()
        db.session.commit()
    return ok_response(data=row.to_dict())


@bp.post("/vcenters/<int:vcenter_id>/run")
@require_menu_permission("physical_discovery_manage")
def run_vcenter(vcenter_id):
    try:
        run = run_discovery(vcenter_id=vcenter_id, trigger_type="manual")
    except RuntimeError as exc:
        return error_response(str(exc), code=409)
    return ok_response(data={"run_id": run.id if run else None}, code=202)


def _run_dict(row):
    return {
        "id": row.id, "vcenter_id": row.vcenter_id, "vcenter_name": row.vcenter_name,
        "trigger_type": row.trigger_type, "status": row.status,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "total_count": row.total_count, "success_count": row.success_count,
        "failed_count": row.failed_count, "unmatched_count": row.unmatched_count,
        "error_message": row.error_message,
    }


@bp.get("/runs")
@active_user_required
def list_runs():
    page = max(1, request.args.get("page", 1, type=int))
    page_size = min(100, max(1, request.args.get("page_size", 20, type=int)))
    query = PhysicalDiscoveryRun.query
    status = request.args.get("status")
    if status:
        query = query.filter_by(status=status)
    total = query.count()
    rows = query.order_by(PhysicalDiscoveryRun.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return ok_response(data={"items": [_run_dict(row) for row in rows], "total": total, "page": page, "page_size": page_size})


@bp.get("/runs/<int:run_id>/details")
@active_user_required
def list_run_details(run_id):
    rows = PhysicalDiscoveryDetail.query.filter_by(run_id=run_id).order_by(PhysicalDiscoveryDetail.id.asc()).all()
    return ok_response(data=[{
        "id": row.id, "instance_id": row.instance_id, "instance_name": row.instance_name,
        "input_ip": row.input_ip, "status": row.status, "discovered_address": row.discovered_address,
        "error_code": row.error_code, "error_message": row.error_message,
    } for row in rows])
