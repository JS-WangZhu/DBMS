from flask import Blueprint, request

from app.api.routes.common import require_menu_permission
from app.extensions import db
from app.models.data_query_op import DataQueryOperationConfig
from app.services.audit import log_audit
from app.utils.response import error_response, ok_response


bp = Blueprint("data_query_ops", __name__, url_prefix="/data-query-ops")


SUPPORTED_DB_TYPES = {"mysql", "mongodb", "redis"}


def _invalidate_cache():
    try:
        from app.services import data_access

        data_access.invalidate_query_ops_cache()
    except Exception:
        pass


@bp.get("")
@require_menu_permission("data_query_op_config")
def list_ops():
    rows = (
        DataQueryOperationConfig.query
        .order_by(
            DataQueryOperationConfig.db_type.asc(),
            DataQueryOperationConfig.sort_order.asc(),
            DataQueryOperationConfig.id.asc(),
        )
        .all()
    )
    groups = {"mysql": [], "mongodb": [], "redis": []}
    for row in rows:
        data = row.to_dict()
        groups.setdefault(row.db_type, []).append(data)
    return ok_response(data={"groups": groups, "items": [row.to_dict() for row in rows]})


@bp.post("")
@require_menu_permission("data_query_op_config")
def create_op():
    payload = request.get_json(silent=True) or {}
    db_type = (payload.get("db_type") or "").strip().lower()
    op_key = (payload.get("op_key") or "").strip()
    label = (payload.get("label") or "").strip()

    if db_type not in SUPPORTED_DB_TYPES:
        return error_response("db_type must be one of mysql/mongodb/redis", code=400)
    if not op_key:
        return error_response("op_key is required", code=400)

    existing = (
        DataQueryOperationConfig.query
        .filter(DataQueryOperationConfig.db_type == db_type)
        .filter(db.func.lower(DataQueryOperationConfig.op_key) == op_key.lower())
        .first()
    )
    if existing:
        return error_response("op_key already exists for this db_type", code=400)

    row = DataQueryOperationConfig(
        db_type=db_type,
        op_key=op_key,
        label=label,
        enabled=bool(payload.get("enabled", True)),
        is_builtin=False,
        sort_order=int(payload.get("sort_order") or 99),
    )
    db.session.add(row)
    db.session.commit()
    _invalidate_cache()
    log_audit(
        user_id=None,
        action="data_query_op.create",
        target_type="data_query_op",
        target_id=str(row.id),
        detail=row.to_dict(),
    )
    return ok_response(data=row.to_dict(), code=201)


@bp.patch("/<int:op_id>")
@require_menu_permission("data_query_op_config")
def update_op(op_id):
    payload = request.get_json(silent=True) or {}
    row = DataQueryOperationConfig.query.get_or_404(op_id)

    if "label" in payload:
        row.label = (payload.get("label") or "").strip()
    if "enabled" in payload:
        row.enabled = bool(payload.get("enabled"))
    if "sort_order" in payload:
        try:
            row.sort_order = int(payload.get("sort_order") or 0)
        except (TypeError, ValueError):
            pass
    # 内置项不允许改 op_key / db_type，非内置项允许修改关键字本身
    if not row.is_builtin:
        if "op_key" in payload:
            new_key = (payload.get("op_key") or "").strip()
            if not new_key:
                return error_response("op_key is required", code=400)
            if new_key.lower() != row.op_key.lower():
                dup = (
                    DataQueryOperationConfig.query
                    .filter(DataQueryOperationConfig.db_type == row.db_type)
                    .filter(db.func.lower(DataQueryOperationConfig.op_key) == new_key.lower())
                    .filter(DataQueryOperationConfig.id != row.id)
                    .first()
                )
                if dup:
                    return error_response("op_key already exists for this db_type", code=400)
            row.op_key = new_key

    db.session.commit()
    _invalidate_cache()
    log_audit(
        user_id=None,
        action="data_query_op.update",
        target_type="data_query_op",
        target_id=str(row.id),
        detail=payload,
    )
    return ok_response(data=row.to_dict())


@bp.delete("/<int:op_id>")
@require_menu_permission("data_query_op_config")
def delete_op(op_id):
    row = DataQueryOperationConfig.query.get_or_404(op_id)
    if row.is_builtin:
        return error_response("builtin operation cannot be deleted", code=400)
    db.session.delete(row)
    db.session.commit()
    _invalidate_cache()
    log_audit(
        user_id=None,
        action="data_query_op.delete",
        target_type="data_query_op",
        target_id=str(op_id),
    )
    return ok_response(message="deleted")
