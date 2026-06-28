from flask import Blueprint, request
from sqlalchemy import or_

from app.api.routes.common import active_user_required, admin_required
from app.extensions import db
from app.models.s3_storage_config import S3StorageConfig
from app.services.audit import log_audit
from app.utils.response import error_response, ok_response

bp = Blueprint("s3_storage", __name__, url_prefix="/s3-storage")


@bp.get("/configs")
@active_user_required
def list_configs():
    enabled = request.args.get("enabled")
    keyword = (request.args.get("keyword") or "").strip()
    page = max(int(request.args.get("page", "1")), 1)
    page_size = min(max(int(request.args.get('page_size', '10')), 1), 200)
    query = S3StorageConfig.query
    if enabled is not None:
        query = query.filter_by(enabled=(enabled.lower() == "true"))
    if keyword:
        query = query.filter(
            or_(
                S3StorageConfig.name.like(f"%{keyword}%"),
                S3StorageConfig.bucket.like(f"%{keyword}%"),
                S3StorageConfig.prefix.like(f"%{keyword}%"),
                S3StorageConfig.endpoint_url.like(f"%{keyword}%"),
            )
        )
    total = query.count()
    rows = (
        query.order_by(S3StorageConfig.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ok_response(
        data={
            "items": [item.to_dict() for item in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@bp.post("/configs")
@admin_required
def create_config():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    bucket = (payload.get("bucket") or "").strip()
    access_key = (payload.get("access_key") or "").strip()
    secret_key = (payload.get("secret_key") or "").strip()

    if not name:
        return error_response("name is required", code=400)
    if not bucket:
        return error_response("bucket is required", code=400)
    if not access_key:
        return error_response("access_key is required", code=400)
    if not secret_key:
        return error_response("secret_key is required", code=400)

    existing = S3StorageConfig.query.filter_by(name=name).first()
    if existing:
        return error_response("name already exists", code=400)

    item = S3StorageConfig(
        name=name,
        description=payload.get("description") or "",
        bucket=bucket,
        prefix=payload.get("prefix") or "",
        region=payload.get("region") or "",
        endpoint_url=payload.get("endpoint_url") or "",
        access_key=access_key,
        secret_key=secret_key,
        enabled=bool(payload.get("enabled", True)),
    )
    db.session.add(item)
    db.session.commit()

    log_audit(user_id=None, action="s3_storage.create", target_type="s3_storage_config", target_id=str(item.id), detail=payload)
    return ok_response(data=item.to_dict(), code=201)


@bp.get("/configs/<int:config_id>")
@active_user_required
def get_config(config_id):
    item = S3StorageConfig.query.get_or_404(config_id)
    return ok_response(data=item.to_dict())


@bp.patch("/configs/<int:config_id>")
@admin_required
def update_config(config_id):
    payload = request.get_json(silent=True) or {}
    item = S3StorageConfig.query.get_or_404(config_id)

    name = (payload.get("name") or "").strip()
    if name and name != item.name:
        existing = S3StorageConfig.query.filter_by(name=name).first()
        if existing:
            return error_response("name already exists", code=400)
        item.name = name

    for field in ["description", "bucket", "prefix", "region", "endpoint_url", "access_key", "secret_key"]:
        if field in payload:
            setattr(item, field, payload[field])

    if "enabled" in payload:
        item.enabled = bool(payload["enabled"])

    db.session.commit()
    log_audit(user_id=None, action="s3_storage.update", target_type="s3_storage_config", target_id=str(config_id), detail=payload)
    return ok_response(data=item.to_dict())


@bp.delete("/configs/<int:config_id>")
@admin_required
def delete_config(config_id):
    item = S3StorageConfig.query.get_or_404(config_id)
    db.session.delete(item)
    db.session.commit()
    log_audit(user_id=None, action="s3_storage.delete", target_type="s3_storage_config", target_id=str(config_id))
    return ok_response(message="deleted")
