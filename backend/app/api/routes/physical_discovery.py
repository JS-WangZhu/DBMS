from flask import Blueprint, request

from app.api.routes.common import active_user_required, require_menu_permission
from app.extensions import db
from app.models.physical_discovery import PhysicalDiscoveryConfig, VCenterConfig
from app.services.physical_discovery_config import normalize_cidrs, validate_non_overlapping_cidrs
from app.utils.crypto import encrypt_secret
from app.utils.response import error_response, ok_response


bp = Blueprint("physical_discovery", __name__, url_prefix="/physical-discovery")


def _global_config():
    config = PhysicalDiscoveryConfig.query.first()
    if config is None:
        config = PhysicalDiscoveryConfig()
        db.session.add(config)
        db.session.commit()
    return config


@bp.get("/config")
@active_user_required
def get_config():
    return ok_response(data=_global_config().to_dict())


@bp.put("/config")
@require_menu_permission("physical_discovery_manage")
def update_config():
    payload = request.get_json(silent=True) or {}
    config = _global_config()
    try:
        config.enabled = bool(payload.get("enabled", config.enabled))
        config.poll_interval_minutes = max(1, int(payload.get("poll_interval_minutes", config.poll_interval_minutes)))
        config.connect_timeout_seconds = max(1, int(payload.get("connect_timeout_seconds", config.connect_timeout_seconds)))
        config.batch_size = max(1, int(payload.get("batch_size", config.batch_size)))
    except (TypeError, ValueError):
        return error_response("configuration values must be integers", code=400)
    db.session.commit()
    return ok_response(data=config.to_dict())


@bp.get("/vcenters")
@active_user_required
def list_vcenters():
    rows = VCenterConfig.query.filter_by(deleted=False).order_by(VCenterConfig.id.asc()).all()
    return ok_response(data=[row.to_dict() for row in rows])


@bp.post("/vcenters")
@require_menu_permission("physical_discovery_manage")
def create_vcenter():
    payload = request.get_json(silent=True) or {}
    required = ["name", "address", "username", "password"]
    missing = [field for field in required if not str(payload.get(field) or "").strip()]
    if missing:
        return error_response(f"missing required fields: {', '.join(missing)}", code=400)
    try:
        cidrs = normalize_cidrs(payload.get("cidrs"))
        existing = [(row.id, row.cidrs_json or []) for row in VCenterConfig.query.filter_by(deleted=False).all()]
        validate_non_overlapping_cidrs(cidrs, existing)
        port = int(payload.get("port") or 443)
    except ValueError as exc:
        return error_response(str(exc), code=400)
    if VCenterConfig.query.filter_by(address=str(payload["address"]).strip(), port=port, deleted=False).first():
        return error_response("vCenter address and port already exist", code=400)
    row = VCenterConfig(
        name=str(payload["name"]).strip(),
        address=str(payload["address"]).strip(),
        port=port,
        cidrs_json=cidrs,
        username=str(payload["username"]).strip(),
        password_encrypted=encrypt_secret(str(payload["password"])),
        verify_ssl=bool(payload.get("verify_ssl", True)),
        enabled=bool(payload.get("enabled", True)),
    )
    db.session.add(row)
    db.session.commit()
    return ok_response(data=row.to_dict(), code=201)
