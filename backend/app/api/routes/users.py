from flask import Blueprint, request

from app.api.routes.common import admin_required
from app.extensions import db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.models.user_permission import RoleGroup, UserRoleGroup
from app.services.audit import log_audit
from app.utils.response import error_response, ok_response

bp = Blueprint("users", __name__, url_prefix="/users")


@bp.get("")
@admin_required
def list_users():
    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        page = 1
    try:
        page_size = int(request.args.get('page_size', '10'))
    except ValueError:
        page_size = 10
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    keyword = (request.args.get("keyword") or "").strip()
    query = User.query
    if keyword:
        query = query.filter(User.username.like(f"%{keyword}%"))
    total = query.count()
    users = (
        query.order_by(User.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    user_ids = [item.id for item in users]
    bindings = UserRoleGroup.query.filter(UserRoleGroup.user_id.in_(user_ids)).all() if user_ids else []
    group_ids = sorted({item.role_group_id for item in bindings})
    groups = RoleGroup.query.filter(RoleGroup.id.in_(group_ids)).all() if group_ids else []
    group_name_map = {item.id: item.name for item in groups}
    user_group_ids = {}
    for row in bindings:
        user_group_ids.setdefault(row.user_id, []).append(row.role_group_id)
    data_items = []
    for item in users:
        user_data = item.to_dict()
        ids = user_group_ids.get(item.id, [])
        user_data["role_group_ids"] = ids
        user_data["role_group_names"] = [group_name_map[group_id] for group_id in ids if group_id in group_name_map]
        data_items.append(user_data)
    return ok_response(data={"items": data_items, "total": total, "page": page, "page_size": page_size})


@bp.post("")
@admin_required
def create_user():
    payload = request.get_json(silent=True) or {}
    username = (payload.get("username") or "").strip()
    password = payload.get("password") or ""
    role = payload.get("role") or "user"
    status = payload.get("status") or "active"
    role_group_ids = payload.get("role_group_ids") or []

    if not username or not password:
        return error_response("username and password are required", code=400)
    if len(password) < 8:
        return error_response("password must be at least 8 chars", code=400)
    if role not in {"admin", "user", "api"}:
        return error_response("invalid role", code=400)
    if status not in {"active", "disabled"}:
        return error_response("invalid status", code=400)

    existing = User.query.filter_by(username=username).first()
    if existing:
        return error_response("username already exists", code=409)

    user = User(username=username, role=role, status=status, auth_source="local")
    user.set_password(password)

    db.session.add(user)
    db.session.flush()
    for group_id in role_group_ids:
        try:
            parsed_id = int(group_id)
        except (TypeError, ValueError):
            continue
        if not RoleGroup.query.get(parsed_id):
            continue
        db.session.add(UserRoleGroup(user_id=user.id, role_group_id=parsed_id))
    db.session.commit()

    log_audit(user_id=None, action="user.create", target_type="user", target_id=str(user.id), detail={"username": username})
    return ok_response(data=user.to_dict(), code=201)


@bp.patch("/<int:user_id>")
@admin_required
def update_user(user_id):
    payload = request.get_json(silent=True) or {}

    user = User.query.get_or_404(user_id)

    if "username" in payload:
        username = (payload.get("username") or "").strip()
        if not username:
            return error_response("username is required", code=400)
        existing = User.query.filter_by(username=username).first()
        if existing and existing.id != user.id:
            return error_response("username already exists", code=409)
        user.username = username

    if "role" in payload:
        role = payload.get("role")
        if role not in {"admin", "user", "api"}:
            return error_response("invalid role", code=400)
        user.role = role

    if "status" in payload:
        status = payload.get("status")
        if status not in {"active", "disabled"}:
            return error_response("invalid status", code=400)
        user.status = status

    if payload.get("password"):
        if len(payload["password"]) < 8:
            return error_response("password must be at least 8 chars", code=400)
        user.set_password(payload["password"])

    if "role_group_ids" in payload:
        role_group_ids = payload.get("role_group_ids") or []
        UserRoleGroup.query.filter_by(user_id=user.id).delete(synchronize_session=False)
        for group_id in role_group_ids:
            try:
                parsed_id = int(group_id)
            except (TypeError, ValueError):
                continue
            if not RoleGroup.query.get(parsed_id):
                continue
            db.session.add(UserRoleGroup(user_id=user.id, role_group_id=parsed_id))

    db.session.commit()

    log_audit(user_id=None, action="user.update", target_type="user", target_id=str(user.id), detail=payload)
    return ok_response(data=user.to_dict())


@bp.delete("/<int:user_id>")
@admin_required
def delete_user(user_id):
    user = User.query.get_or_404(user_id)

    username = user.username
    try:
        # Keep audit history but break FK dependency before deleting user.
        AuditLog.query.filter_by(user_id=user.id).update({"user_id": None}, synchronize_session=False)
        UserRoleGroup.query.filter_by(user_id=user.id).delete(synchronize_session=False)
        db.session.delete(user)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return error_response(f"delete failed: {exc}", code=500)

    try:
        log_audit(user_id=None, action="user.delete", target_type="user", target_id=str(user_id), detail={"username": username})
    except Exception:
        # Audit failure should not break already completed delete operation.
        db.session.rollback()

    return ok_response(message="deleted")
