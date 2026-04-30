from functools import wraps

from flask import g, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.models.user import User
from app.models.user_permission import (
    ApiKey,
    RoleGroupClusterPermission,
    RoleGroupMenuPermission,
    UserClusterPermission,
    UserMenuPermission,
    UserRoleGroup,
)
from app.utils.response import error_response


def get_current_user():
    current = getattr(g, "current_user", None)
    if current:
        return current
    try:
        identity = get_jwt_identity()
    except RuntimeError:
        return None
    if not identity:
        return None
    try:
        user_id = int(identity)
    except (TypeError, ValueError):
        return None
    return User.query.get(user_id)


def active_user_required(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user or user.status != "active":
            return error_response("forbidden", code=403)
        g.current_user = user
        return fn(*args, **kwargs)

    return wrapper


def admin_required(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user or user.status != "active" or user.role != "admin":
            return error_response("admin required", code=403)
        g.current_user = user
        return fn(*args, **kwargs)

    return wrapper


def api_key_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        token = request.headers.get("X-API-Key") or ""
        if not token:
            return error_response("api key required", code=401)
        api_key = ApiKey.query.filter_by(token=token, status="active").first()
        if not api_key:
            return error_response("invalid api key", code=401)
        user = User.query.get(api_key.user_id)
        if not user or user.status != "active":
            return error_response("forbidden", code=403)
        g.current_user = user
        g.api_key = api_key
        return fn(*args, **kwargs)

    return wrapper


def require_menu_permission(menu_key: str):
    def decorator(fn):
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user or user.status != "active":
                return error_response("forbidden", code=403)
            if user.role == "admin":
                g.current_user = user
                return fn(*args, **kwargs)
            if menu_key not in get_effective_menu_keys(user.id):
                return error_response("permission denied", code=403)
            g.current_user = user
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def require_cluster_permission(cluster_id: int, action: str):
    user = get_current_user()
    if not user or user.status != "active":
        return False
    if user.role == "admin":
        return True
    effective = get_effective_cluster_permissions(user.id)
    row = effective.get(cluster_id)
    if not row:
        return False
    if action == "query":
        return bool(row.get("can_query"))
    if action == "change":
        return bool(row.get("can_change"))
    return False


def get_effective_menu_keys(user_id: int):
    direct_keys = {row.menu_key for row in UserMenuPermission.query.filter_by(user_id=user_id).all()}
    role_group_ids = [row.role_group_id for row in UserRoleGroup.query.filter_by(user_id=user_id).all()]
    if not role_group_ids:
        return direct_keys
    group_keys = {
        row.menu_key
        for row in RoleGroupMenuPermission.query.filter(RoleGroupMenuPermission.role_group_id.in_(role_group_ids)).all()
    }
    return direct_keys.union(group_keys)


def get_effective_cluster_permissions(user_id: int):
    effective = {}
    for row in UserClusterPermission.query.filter_by(user_id=user_id).all():
        effective[row.cluster_id] = {
            "can_query": bool(row.can_query),
            "can_change": bool(row.can_change),
        }
    role_group_ids = [row.role_group_id for row in UserRoleGroup.query.filter_by(user_id=user_id).all()]
    if not role_group_ids:
        return effective
    for row in RoleGroupClusterPermission.query.filter(RoleGroupClusterPermission.role_group_id.in_(role_group_ids)).all():
        merged = effective.setdefault(row.cluster_id, {"can_query": False, "can_change": False})
        merged["can_query"] = merged["can_query"] or bool(row.can_query)
        merged["can_change"] = merged["can_change"] or bool(row.can_change)
    return effective


def list_allowed_cluster_ids(action: str):
    user = get_current_user()
    if not user or user.status != "active":
        return []
    if user.role == "admin":
        return None
    effective = get_effective_cluster_permissions(user.id)
    if action == "query":
        return [cid for cid, perm in effective.items() if perm.get("can_query")]
    if action == "change":
        return [cid for cid, perm in effective.items() if perm.get("can_change")]
    return []
