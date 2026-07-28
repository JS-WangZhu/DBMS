import csv
import io
from datetime import datetime

from flask import Blueprint, Response, request
from sqlalchemy.exc import IntegrityError

from app.api.routes.common import active_user_required, get_current_user, require_menu_permission
from app.extensions import db
from app.models.db_asset import DatabaseInstance
from app.models.audit_log import AuditLog
from app.models.jumpserver_config import JumpServerConfig
from app.services.audit import log_audit
from app.services.jumpserver_service import (
    DEFAULT_WEB_URL_TEMPLATE,
    normalize_base_url,
    test_jumpserver_connection,
    validate_web_url_template,
)
from app.services.instance_service import invalidate_instance_list_cache
from app.utils.response import error_response, ok_response


bp = Blueprint("jumpserver_configs", __name__, url_prefix="/jumpserver-configs")

MAPPING_CSV_FIELDS = [
    "instance_id",
    "db_type",
    "instance_name",
    "host",
    "port",
    "jumpserver_config_id",
    "jumpserver_config_name",
    "jumpserver_asset_id",
]
MAX_MAPPING_CSV_BYTES = 2 * 1024 * 1024
MAX_MAPPING_CSV_ROWS = 5000


def _apply_payload(row, payload):
    if "name" in payload:
        row.name = str(payload.get("name") or "").strip()
    if not row.name:
        return "name is required"
    if len(row.name) > 128:
        return "name is too long"

    try:
        base_url = normalize_base_url(payload.get("base_url", row.base_url))
        template = validate_web_url_template(
            payload.get("web_url_template", row.web_url_template or DEFAULT_WEB_URL_TEMPLATE),
            base_url,
        )
    except ValueError as exc:
        return str(exc)

    row.base_url = base_url
    row.web_url_template = template
    if len(row.base_url) > 512:
        return "base_url is too long"
    if len(row.web_url_template) > 1024:
        return "web_url_template is too long"
    if "enabled" in payload:
        row.enabled = bool(payload.get("enabled"))
    if "verify_ssl" in payload:
        row.verify_ssl = bool(payload.get("verify_ssl"))
    return None


@bp.get("/options")
@active_user_required
def list_jumpserver_options():
    rows = JumpServerConfig.query.filter_by(enabled=True).order_by(JumpServerConfig.name.asc()).all()
    return ok_response(data=[{"id": row.id, "name": row.name} for row in rows])


@bp.get("")
@require_menu_permission("jumpserver_config")
def list_jumpserver_configs():
    rows = JumpServerConfig.query.order_by(JumpServerConfig.id.desc()).all()
    return ok_response(data=[row.to_dict() for row in rows])


@bp.get("/mapping-template")
@require_menu_permission("jumpserver_config")
def download_mapping_template():
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=MAPPING_CSV_FIELDS, lineterminator="\n")
    writer.writeheader()
    rows = DatabaseInstance.query.order_by(DatabaseInstance.db_type.asc(), DatabaseInstance.id.asc()).all()
    for row in rows:
        writer.writerow(
            {
                "instance_id": row.id,
                "db_type": row.db_type,
                "instance_name": row.name,
                "host": row.host_input,
                "port": row.port,
                "jumpserver_config_id": row.jumpserver_config_id or "",
                "jumpserver_config_name": row.jumpserver_config.name if row.jumpserver_config else "",
                "jumpserver_asset_id": row.jumpserver_asset_id or "",
            }
        )
    content = "\ufeff" + output.getvalue()
    return Response(
        content,
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="jumpserver-instance-mapping.csv"'},
    )


def _mapping_error(row_number, message):
    return {"row": row_number, "message": message}


@bp.post("/mapping-import")
@require_menu_permission("jumpserver_config")
def import_instance_mappings():
    upload = request.files.get("file")
    if not upload or not upload.filename:
        return error_response("CSV file is required", code=400)
    raw = upload.stream.read(MAX_MAPPING_CSV_BYTES + 1)
    if len(raw) > MAX_MAPPING_CSV_BYTES:
        return error_response("CSV file must not exceed 2MB", code=413)
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return error_response("CSV file must use UTF-8 encoding", code=400)

    try:
        reader = csv.DictReader(io.StringIO(content))
        headers = [str(item or "").strip().lower() for item in (reader.fieldnames or [])]
        if len(headers) != len(set(headers)):
            return error_response("CSV contains duplicate column names", code=400)
        missing_headers = [field for field in MAPPING_CSV_FIELDS if field not in headers]
        if missing_headers:
            return error_response(f"CSV missing columns: {', '.join(missing_headers)}", code=400)
        records = []
        for row_number, source in enumerate(reader, start=2):
            if len(records) >= MAX_MAPPING_CSV_ROWS:
                return error_response(f"CSV must not exceed {MAX_MAPPING_CSV_ROWS} data rows", code=400)
            normalized = {str(key or "").strip().lower(): str(value or "").strip() for key, value in source.items()}
            if not any(normalized.values()):
                continue
            records.append((row_number, normalized))
    except csv.Error as exc:
        return error_response(f"Invalid CSV: {exc}", code=400)
    if not records:
        return error_response("CSV contains no mapping rows", code=400)

    errors = []
    parsed_records = []
    seen_instance_ids = set()
    for row_number, row in records:
        try:
            instance_id = int(row.get("instance_id") or "")
        except ValueError:
            errors.append(_mapping_error(row_number, "instance_id must be an integer"))
            continue
        if instance_id in seen_instance_ids:
            errors.append(_mapping_error(row_number, f"duplicate instance_id: {instance_id}"))
            continue
        seen_instance_ids.add(instance_id)

        config_id = None
        if row.get("jumpserver_config_id"):
            try:
                config_id = int(row["jumpserver_config_id"])
            except ValueError:
                errors.append(_mapping_error(row_number, "jumpserver_config_id must be an integer"))
                continue
        config_name = row.get("jumpserver_config_name", "")
        asset_id = row.get("jumpserver_asset_id", "")
        if config_id is None and not config_name:
            errors.append(_mapping_error(row_number, "jumpserver_config_id or jumpserver_config_name is required"))
        if not asset_id:
            errors.append(_mapping_error(row_number, "jumpserver_asset_id is required"))
        elif len(asset_id) > 128:
            errors.append(_mapping_error(row_number, "jumpserver_asset_id is too long"))
        parsed_records.append((row_number, row, instance_id, config_id, config_name, asset_id))

    instance_ids = {item[2] for item in parsed_records}
    instances = DatabaseInstance.query.filter(DatabaseInstance.id.in_(instance_ids)).all() if instance_ids else []
    instance_map = {row.id: row for row in instances}
    config_ids = {item[3] for item in parsed_records if item[3] is not None}
    config_names = {item[4] for item in parsed_records if item[4]}
    config_rows = []
    if config_ids:
        config_rows.extend(JumpServerConfig.query.filter(JumpServerConfig.id.in_(config_ids)).all())
    if config_names:
        config_rows.extend(JumpServerConfig.query.filter(JumpServerConfig.name.in_(config_names)).all())
    config_by_id = {row.id: row for row in config_rows}
    config_by_name = {row.name: row for row in config_rows}

    updates = []
    for row_number, row, instance_id, config_id, config_name, asset_id in parsed_records:
        instance = instance_map.get(instance_id)
        if not instance:
            errors.append(_mapping_error(row_number, f"database instance not found: {instance_id}"))
            continue
        verification_fields = {
            "db_type": instance.db_type,
            "instance_name": instance.name,
            "host": instance.host_input,
            "port": str(instance.port),
        }
        mismatch = next(
            (field for field, expected in verification_fields.items() if row.get(field) and row.get(field) != str(expected)),
            None,
        )
        if mismatch:
            errors.append(_mapping_error(row_number, f"{mismatch} does not match instance {instance_id}"))
            continue

        config_from_id = config_by_id.get(config_id) if config_id is not None else None
        config_from_name = config_by_name.get(config_name) if config_name else None
        if config_id is not None and not config_from_id:
            errors.append(_mapping_error(row_number, f"JumpServer config not found: {config_id}"))
            continue
        if config_name and not config_from_name:
            errors.append(_mapping_error(row_number, f"JumpServer config not found: {config_name}"))
            continue
        config = config_from_id or config_from_name
        if config_from_id and config_from_name and config_from_id.id != config_from_name.id:
            errors.append(_mapping_error(row_number, "JumpServer config id and name refer to different configs"))
            continue
        if config_name and config.name != config_name:
            errors.append(_mapping_error(row_number, "jumpserver_config_name does not match jumpserver_config_id"))
            continue
        if not config.enabled:
            errors.append(_mapping_error(row_number, f"JumpServer config is disabled: {config.name}"))
            continue
        updates.append((instance, config, asset_id))

    if errors:
        return error_response(
            f"CSV validation failed with {len(errors)} error(s); no mappings were imported",
            code=400,
            data={"errors": errors[:100], "error_count": len(errors)},
        )

    for instance, config, asset_id in updates:
        instance.jumpserver_config_id = config.id
        instance.jumpserver_asset_id = asset_id
    user = get_current_user()
    db.session.add(
        AuditLog(
            user_id=user.id if user else None,
            action="jumpserver.mapping.import",
            target_type="database_instance",
            target_id="batch",
            detail_json={"count": len(updates), "instance_ids": [item[0].id for item in updates[:100]]},
        )
    )
    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return error_response(f"CSV import failed: {exc}", code=500)
    invalidate_instance_list_cache()
    return ok_response(data={"imported_count": len(updates)}, message="mappings imported")


@bp.post("")
@require_menu_permission("jumpserver_config")
def create_jumpserver_config():
    payload = request.get_json(silent=True) or {}
    row = JumpServerConfig(web_url_template=DEFAULT_WEB_URL_TEMPLATE)
    err = _apply_payload(row, payload)
    if err:
        return error_response(err, code=400)
    try:
        db.session.add(row)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error_response("JumpServer config name already exists", code=409)
    user = get_current_user()
    log_audit(user_id=user.id if user else None, action="jumpserver.config.create", target_type="jumpserver_config", target_id=str(row.id), detail={"name": row.name, "base_url": row.base_url})
    return ok_response(data=row.to_dict(), code=201)


@bp.patch("/<int:config_id>")
@require_menu_permission("jumpserver_config")
def update_jumpserver_config(config_id):
    row = JumpServerConfig.query.get_or_404(config_id)
    payload = request.get_json(silent=True) or {}
    err = _apply_payload(row, payload)
    if err:
        return error_response(err, code=400)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error_response("JumpServer config name already exists", code=409)
    user = get_current_user()
    log_audit(user_id=user.id if user else None, action="jumpserver.config.update", target_type="jumpserver_config", target_id=str(row.id), detail={"name": row.name, "base_url": row.base_url, "enabled": row.enabled})
    invalidate_instance_list_cache()
    return ok_response(data=row.to_dict())


@bp.delete("/<int:config_id>")
@require_menu_permission("jumpserver_config")
def delete_jumpserver_config(config_id):
    row = JumpServerConfig.query.get_or_404(config_id)
    if DatabaseInstance.query.filter_by(jumpserver_config_id=row.id).first():
        return error_response("JumpServer config is bound to database instances", code=409)
    detail = {"name": row.name, "base_url": row.base_url}
    db.session.delete(row)
    db.session.commit()
    user = get_current_user()
    log_audit(user_id=user.id if user else None, action="jumpserver.config.delete", target_type="jumpserver_config", target_id=str(config_id), detail=detail)
    invalidate_instance_list_cache()
    return ok_response(message="deleted")


@bp.post("/<int:config_id>/test")
@require_menu_permission("jumpserver_config")
def test_jumpserver_config(config_id):
    row = JumpServerConfig.query.get_or_404(config_id)
    row.last_test_at = datetime.now()
    try:
        status_code = test_jumpserver_connection(row)
        row.last_test_status = "success"
        row.last_test_error = None
        db.session.commit()
        return ok_response(data={"status": "success", "http_status": status_code})
    except Exception as exc:
        row.last_test_status = "failed"
        row.last_test_error = str(exc)[:512]
        db.session.commit()
        return error_response(f"JumpServer connection failed: {exc}", code=502)
