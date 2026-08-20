from flask import Blueprint, request

from app.api.routes.common import admin_required, get_effective_cluster_permissions
from app.extensions import db
from app.models.db_asset import DatabaseCluster
from app.models.user import User
from app.models.user_permission import (
    DataSourceGroup,
    DataSourceGroupClusterPermission,
    UserClusterPermission,
    UserDataSourceGroup,
)
from app.services.audit import log_audit
from app.utils.response import error_response, ok_response

bp = Blueprint("data_source_permissions", __name__, url_prefix="/data-source-permissions")


def _normalize_permissions(raw):
    result = []
    seen = set()
    for item in raw if isinstance(raw, list) else []:
        try:
            cluster_id = int(item.get("cluster_id"))
        except (AttributeError, TypeError, ValueError):
            continue
        if cluster_id in seen or not DatabaseCluster.query.get(cluster_id):
            continue
        seen.add(cluster_id)
        can_query = item.get("can_query") is True
        can_change = item.get("can_change") is True
        can_execute = item.get("can_execute") is True
        can_view_instance = item.get("can_view_instance") is True
        if can_query or can_change or can_execute or can_view_instance:
            result.append({
                "cluster_id": cluster_id,
                "can_query": can_query,
                "can_change": can_change,
                "can_execute": can_execute,
                "can_view_instance": can_view_instance,
            })
    return result


def _group_dict(group):
    data = group.to_dict()
    data["permissions"] = [
        {
            "cluster_id": row.cluster_id,
            "can_query": bool(row.can_query),
            "can_change": bool(row.can_change),
            "can_execute": bool(row.can_execute),
            "can_view_instance": bool(row.can_view_instance),
        }
        for row in DataSourceGroupClusterPermission.query.filter_by(group_id=group.id).all()
    ]
    data["user_ids"] = [row.user_id for row in UserDataSourceGroup.query.filter_by(group_id=group.id).all()]
    return data


@bp.get("/overview")
@admin_required
def overview():
    users = User.query.order_by(User.username.asc()).all()
    groups = DataSourceGroup.query.order_by(DataSourceGroup.name.asc()).all()
    return ok_response(data={
        "users": [user.to_dict() for user in users],
        "clusters": [cluster.to_dict() for cluster in DatabaseCluster.query.order_by(DatabaseCluster.db_type, DatabaseCluster.name).all()],
        "groups": [_group_dict(group) for group in groups],
    })


@bp.get("/users/<int:user_id>")
@admin_required
def get_user_data_source_permissions(user_id):
    user = User.query.get_or_404(user_id)
    direct = [
        {
            "cluster_id": row.cluster_id,
            "can_query": bool(row.can_query),
            "can_change": bool(row.can_change),
            "can_execute": bool(row.can_execute),
            "can_view_instance": bool(row.can_view_instance),
        }
        for row in UserClusterPermission.query.filter_by(user_id=user.id).all()
    ]
    group_ids = [row.group_id for row in UserDataSourceGroup.query.filter_by(user_id=user.id).all()]
    effective = get_effective_cluster_permissions(user.id) if user.role != "admin" else {
        row.id: {"can_query": True, "can_change": True, "can_execute": True, "can_view_instance": True}
        for row in DatabaseCluster.query.all()
    }
    return ok_response(data={
        "user": user.to_dict(),
        "direct_permissions": direct,
        "group_ids": group_ids,
        "effective_permissions": [{"cluster_id": cid, **value} for cid, value in effective.items()],
    })


@bp.put("/users/<int:user_id>")
@admin_required
def update_user_data_source_permissions(user_id):
    user = User.query.get_or_404(user_id)
    if user.role == "admin":
        return error_response("admin permissions are managed by system", code=400)
    payload = request.get_json(silent=True) or {}
    permissions = _normalize_permissions(payload.get("direct_permissions"))
    group_ids = []
    for value in payload.get("group_ids") or []:
        try:
            group_id = int(value)
        except (TypeError, ValueError):
            continue
        if DataSourceGroup.query.get(group_id):
            group_ids.append(group_id)
    UserClusterPermission.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    for item in permissions:
        db.session.add(UserClusterPermission(user_id=user.id, **item))
    UserDataSourceGroup.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    for group_id in sorted(set(group_ids)):
        db.session.add(UserDataSourceGroup(user_id=user.id, group_id=group_id))
    db.session.commit()
    log_audit(user_id=None, action="data_source_permission.user.update", target_type="user", target_id=str(user.id), detail={"direct_permissions": permissions, "group_ids": group_ids})
    return ok_response(message="数据源权限已保存")


@bp.post("/groups")
@admin_required
def create_group():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name") or "").strip()
    if not name:
        return error_response("name is required", code=400)
    if DataSourceGroup.query.filter_by(name=name).first():
        return error_response("数据源组名称已存在", code=409)
    group = DataSourceGroup(name=name, description=str(payload.get("description") or "").strip() or None)
    db.session.add(group)
    db.session.flush()
    for item in _normalize_permissions(payload.get("permissions")):
        db.session.add(DataSourceGroupClusterPermission(group_id=group.id, **item))
    db.session.commit()
    return ok_response(data=_group_dict(group), code=201)


@bp.patch("/groups/<int:group_id>")
@admin_required
def update_group(group_id):
    group = DataSourceGroup.query.get_or_404(group_id)
    payload = request.get_json(silent=True) or {}
    if "name" in payload:
        name = str(payload.get("name") or "").strip()
        existing = DataSourceGroup.query.filter_by(name=name).first()
        if not name or (existing and existing.id != group.id):
            return error_response("数据源组名称为空或已存在", code=409)
        group.name = name
    if "description" in payload:
        group.description = str(payload.get("description") or "").strip() or None
    if "permissions" in payload:
        permissions = _normalize_permissions(payload.get("permissions"))
        DataSourceGroupClusterPermission.query.filter_by(group_id=group.id).delete(synchronize_session=False)
        for item in permissions:
            db.session.add(DataSourceGroupClusterPermission(group_id=group.id, **item))
    db.session.commit()
    return ok_response(data=_group_dict(group))


@bp.delete("/groups/<int:group_id>")
@admin_required
def delete_group(group_id):
    group = DataSourceGroup.query.get_or_404(group_id)
    UserDataSourceGroup.query.filter_by(group_id=group.id).delete(synchronize_session=False)
    DataSourceGroupClusterPermission.query.filter_by(group_id=group.id).delete(synchronize_session=False)
    db.session.delete(group)
    db.session.commit()
    return ok_response(message="已删除")
