import secrets

from flask import Blueprint, request

from app.api.routes.common import active_user_required, admin_required, get_current_user
from app.extensions import db
from app.models.db_asset import DatabaseCluster
from app.models.user import User
from app.models.user_permission import (
    ApiKey,
    RoleGroup,
    RoleGroupClusterPermission,
    RoleGroupMenuPermission,
    UserClusterPermission,
    UserMenuPermission,
    UserRoleGroup,
)
from app.services.audit import log_audit
from app.utils.response import error_response, ok_response

bp = Blueprint("user_permissions", __name__, url_prefix="/users/permissions")

MENU_CATALOG = [
    {"key": "dashboard", "label": "总览"},
    {"key": "mysql_instances", "label": "MySQL 实例管理"},
    {"key": "mysql_clusters", "label": "MySQL 集群管理"},
    {"key": "mysql_connections", "label": "MySQL 连接管理"},
    {"key": "mongodb_instances", "label": "MongoDB 实例管理"},
    {"key": "mongodb_clusters", "label": "MongoDB 集群管理"},
    {"key": "mongodb_connections", "label": "MongoDB 连接管理"},
    {"key": "redis_instances", "label": "Redis 实例管理"},
    {"key": "redis_clusters", "label": "Redis 集群管理"},
    {"key": "redis_connections", "label": "Redis 连接管理"},
    {"key": "doris_instances", "label": "Doris 实例管理"},
    {"key": "doris_clusters", "label": "Doris 集群管理"},
    {"key": "inspection_manage", "label": "巡检管理"},
    {"key": "data_query", "label": "数据查询"},
    {"key": "data_change", "label": "数据变更"},
    {"key": "ai_analysis", "label": "智能分析"},
    {"key": "data_history", "label": "历史记录"},
    {"key": "backup_mysql_policies", "label": "MySQL策略"},
    {"key": "backup_mongo_policies", "label": "MongoDB策略"},
    {"key": "backup_records", "label": "备份记录"},
    {"key": "backup_tool_configs", "label": "备份工具管理"},
    {"key": "backup_agents", "label": "Agent管理"},
    {"key": "backup_notify_targets", "label": "通知地址管理"},
    {"key": "backup_s3_storage", "label": "存储配置管理"},
    {"key": "backup_keys", "label": "备份密钥管理"},
    {"key": "users_info", "label": "用户信息管理"},
    {"key": "users_role_groups", "label": "角色组管理"},
    {"key": "users_permissions", "label": "用户权限管理"},
    {"key": "ai_model_config", "label": "AI模型管理"},
    {"key": "ha_config", "label": "高可用配置管理"},
    {"key": "instance_status_config", "label": "实例状态检测管理"},
    {"key": "inspection_param_config", "label": "巡检参数管理"},
    {"key": "data_query_op_config", "label": "数据查询操作配置"},
    {"key": "sso_config", "label": "SSO登录管理"},
]
MENU_KEY_SET = {item["key"] for item in MENU_CATALOG}


def _normalize_menu_keys(raw):
    if not raw:
        return []
    if isinstance(raw, str):
        raw = [raw]
    normalized = []
    seen = set()
    for item in raw:
        key = str(item).strip()
        if not key or key not in MENU_KEY_SET or key in seen:
            continue
        seen.add(key)
        normalized.append(key)
    return normalized


def _parse_page_params():
    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        page = 1
    try:
        page_size = int(request.args.get("page_size", "20"))
    except ValueError:
        page_size = 20
    page = max(page, 1)
    page_size = min(max(page_size, 1), 200)
    return page, page_size


@bp.get("/<int:user_id>")
@admin_required
def get_permissions(user_id: int):
    user = User.query.get_or_404(user_id)
    if user.role == "admin":
        menu_keys = [item["key"] for item in MENU_CATALOG]
    else:
        menu_keys = [item.menu_key for item in UserMenuPermission.query.filter_by(user_id=user.id).all()]
    cluster_rows = UserClusterPermission.query.filter_by(user_id=user.id).all()
    cluster_permissions = [
        {
            "cluster_id": item.cluster_id,
            "can_query": bool(item.can_query),
            "can_change": bool(item.can_change),
        }
        for item in cluster_rows
    ]
    api_keys = [item.to_dict() for item in ApiKey.query.filter_by(user_id=user.id).all()]
    role_group_rows = UserRoleGroup.query.filter_by(user_id=user.id).all()
    role_group_ids = [row.role_group_id for row in role_group_rows]
    if role_group_ids:
        group_menu_keys = [
            item.menu_key
            for item in RoleGroupMenuPermission.query.filter(RoleGroupMenuPermission.role_group_id.in_(role_group_ids)).all()
        ]
        menu_keys = sorted(set(menu_keys).union(group_menu_keys))
        merged = {item["cluster_id"]: item for item in cluster_permissions}
        group_cluster_rows = RoleGroupClusterPermission.query.filter(RoleGroupClusterPermission.role_group_id.in_(role_group_ids)).all()
        for item in group_cluster_rows:
            row = merged.setdefault(
                item.cluster_id,
                {"cluster_id": item.cluster_id, "can_query": False, "can_change": False},
            )
            row["can_query"] = row["can_query"] or bool(item.can_query)
            row["can_change"] = row["can_change"] or bool(item.can_change)
        cluster_permissions = list(merged.values())
    return ok_response(
        data={
            "user": user.to_dict(),
            "menu_keys": menu_keys,
            "menu_catalog": MENU_CATALOG,
            "cluster_permissions": cluster_permissions,
            "api_keys": api_keys,
            "role_group_ids": role_group_ids,
        }
    )


@bp.get("/me")
@active_user_required
def get_my_permissions():
    user = get_current_user()
    if user.role == "admin":
        menu_keys = [item["key"] for item in MENU_CATALOG]
    else:
        menu_keys = [item.menu_key for item in UserMenuPermission.query.filter_by(user_id=user.id).all()]
    cluster_rows = UserClusterPermission.query.filter_by(user_id=user.id).all()
    cluster_permissions = [
        {
            "cluster_id": item.cluster_id,
            "can_query": bool(item.can_query),
            "can_change": bool(item.can_change),
        }
        for item in cluster_rows
    ]
    role_group_rows = UserRoleGroup.query.filter_by(user_id=user.id).all()
    role_group_ids = [row.role_group_id for row in role_group_rows]
    if role_group_ids:
        group_menu_keys = [
            item.menu_key
            for item in RoleGroupMenuPermission.query.filter(RoleGroupMenuPermission.role_group_id.in_(role_group_ids)).all()
        ]
        menu_keys = sorted(set(menu_keys).union(group_menu_keys))
        merged = {item["cluster_id"]: item for item in cluster_permissions}
        group_cluster_rows = RoleGroupClusterPermission.query.filter(RoleGroupClusterPermission.role_group_id.in_(role_group_ids)).all()
        for item in group_cluster_rows:
            row = merged.setdefault(
                item.cluster_id,
                {"cluster_id": item.cluster_id, "can_query": False, "can_change": False},
            )
            row["can_query"] = row["can_query"] or bool(item.can_query)
            row["can_change"] = row["can_change"] or bool(item.can_change)
        cluster_permissions = list(merged.values())
    return ok_response(
        data={
            "user": user.to_dict(),
            "menu_keys": menu_keys,
            "menu_catalog": MENU_CATALOG,
            "cluster_permissions": cluster_permissions,
            "api_keys": [],
            "role_group_ids": role_group_ids,
        }
    )


@bp.put("/<int:user_id>")
@admin_required
def update_permissions(user_id: int):
    user = User.query.get_or_404(user_id)
    if user.role == "admin":
        return error_response("admin permissions are managed by system", code=400)
    payload = request.get_json(silent=True) or {}
    menu_keys = _normalize_menu_keys(payload.get("menu_keys"))
    cluster_permissions = payload.get("cluster_permissions") or []
    role_group_ids = payload.get("role_group_ids") or []

    UserMenuPermission.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    for key in menu_keys:
        db.session.add(UserMenuPermission(user_id=user.id, menu_key=key))

    UserClusterPermission.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    for item in cluster_permissions:
        try:
            cluster_id = int(item.get("cluster_id"))
        except (TypeError, ValueError):
            continue
        if not DatabaseCluster.query.get(cluster_id):
            continue
        db.session.add(
            UserClusterPermission(
                user_id=user.id,
                cluster_id=cluster_id,
                can_query=bool(item.get("can_query")),
                can_change=bool(item.get("can_change")),
            )
        )

    valid_role_group_ids = []
    for group_id in role_group_ids:
        try:
            parsed = int(group_id)
        except (TypeError, ValueError):
            continue
        if not RoleGroup.query.get(parsed):
            continue
        valid_role_group_ids.append(parsed)
    UserRoleGroup.query.filter_by(user_id=user.id).delete(synchronize_session=False)
    for group_id in sorted(set(valid_role_group_ids)):
        db.session.add(UserRoleGroup(user_id=user.id, role_group_id=group_id))

    db.session.commit()
    log_audit(
        user_id=None,
        action="user.permissions.update",
        target_type="user",
        target_id=str(user.id),
        detail={"menu_keys": menu_keys, "cluster_permissions": cluster_permissions, "role_group_ids": valid_role_group_ids},
    )
    return ok_response(message="updated")


@bp.get("/role-groups")
@admin_required
def list_role_groups():
    page, page_size = _parse_page_params()
    keyword = (request.args.get("keyword") or "").strip()
    query = RoleGroup.query
    if keyword:
        query = query.filter(RoleGroup.name.like(f"%{keyword}%"))
    total = query.count()
    rows = (
        query.order_by(RoleGroup.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = []
    for row in rows:
        menu_keys = [item.menu_key for item in RoleGroupMenuPermission.query.filter_by(role_group_id=row.id).all()]
        cluster_permissions = [
            {
                "cluster_id": item.cluster_id,
                "can_query": bool(item.can_query),
                "can_change": bool(item.can_change),
            }
            for item in RoleGroupClusterPermission.query.filter_by(role_group_id=row.id).all()
        ]
        user_count = UserRoleGroup.query.filter_by(role_group_id=row.id).count()
        data = row.to_dict()
        data.update({"menu_keys": menu_keys, "cluster_permissions": cluster_permissions, "user_count": user_count})
        items.append(data)
    return ok_response(data={"items": items, "total": total, "page": page, "page_size": page_size, "menu_catalog": MENU_CATALOG})


@bp.get("/role-groups/options")
@admin_required
def list_role_group_options():
    rows = RoleGroup.query.order_by(RoleGroup.id.desc()).all()
    return ok_response(data=[row.to_dict() for row in rows])


@bp.post("/role-groups")
@admin_required
def create_role_group():
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    description = (payload.get("description") or "").strip() or None
    menu_keys = _normalize_menu_keys(payload.get("menu_keys"))
    cluster_permissions = payload.get("cluster_permissions") or []
    if not name:
        return error_response("name is required", code=400)
    if RoleGroup.query.filter_by(name=name).first():
        return error_response("role group already exists", code=409)
    group = RoleGroup(name=name, description=description)
    db.session.add(group)
    db.session.flush()
    for key in menu_keys:
        db.session.add(RoleGroupMenuPermission(role_group_id=group.id, menu_key=key))
    for item in cluster_permissions:
        try:
            cluster_id = int(item.get("cluster_id"))
        except (TypeError, ValueError):
            continue
        if not DatabaseCluster.query.get(cluster_id):
            continue
        db.session.add(
            RoleGroupClusterPermission(
                role_group_id=group.id,
                cluster_id=cluster_id,
                can_query=bool(item.get("can_query")),
                can_change=bool(item.get("can_change")),
            )
        )
    db.session.commit()
    log_audit(user_id=None, action="role_group.create", target_type="role_group", target_id=str(group.id), detail=payload)
    return ok_response(data=group.to_dict(), code=201)


@bp.patch("/role-groups/<int:group_id>")
@admin_required
def update_role_group(group_id: int):
    payload = request.get_json(silent=True) or {}
    group = RoleGroup.query.get_or_404(group_id)
    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            return error_response("name is required", code=400)
        existing = RoleGroup.query.filter_by(name=name).first()
        if existing and existing.id != group.id:
            return error_response("role group already exists", code=409)
        group.name = name
    if "description" in payload:
        group.description = (payload.get("description") or "").strip() or None
    if "menu_keys" in payload:
        menu_keys = _normalize_menu_keys(payload.get("menu_keys"))
        RoleGroupMenuPermission.query.filter_by(role_group_id=group.id).delete(synchronize_session=False)
        for key in menu_keys:
            db.session.add(RoleGroupMenuPermission(role_group_id=group.id, menu_key=key))
    if "cluster_permissions" in payload:
        cluster_permissions = payload.get("cluster_permissions") or []
        RoleGroupClusterPermission.query.filter_by(role_group_id=group.id).delete(synchronize_session=False)
        for item in cluster_permissions:
            try:
                cluster_id = int(item.get("cluster_id"))
            except (TypeError, ValueError):
                continue
            if not DatabaseCluster.query.get(cluster_id):
                continue
            db.session.add(
                RoleGroupClusterPermission(
                    role_group_id=group.id,
                    cluster_id=cluster_id,
                    can_query=bool(item.get("can_query")),
                    can_change=bool(item.get("can_change")),
                )
            )
    db.session.commit()
    log_audit(user_id=None, action="role_group.update", target_type="role_group", target_id=str(group.id), detail=payload)
    return ok_response(data=group.to_dict())


@bp.delete("/role-groups/<int:group_id>")
@admin_required
def delete_role_group(group_id: int):
    group = RoleGroup.query.get_or_404(group_id)
    RoleGroupMenuPermission.query.filter_by(role_group_id=group.id).delete(synchronize_session=False)
    RoleGroupClusterPermission.query.filter_by(role_group_id=group.id).delete(synchronize_session=False)
    UserRoleGroup.query.filter_by(role_group_id=group.id).delete(synchronize_session=False)
    db.session.delete(group)
    db.session.commit()
    log_audit(user_id=None, action="role_group.delete", target_type="role_group", target_id=str(group_id))
    return ok_response(message="deleted")


@bp.post("/<int:user_id>/api-key")
@admin_required
def create_api_key(user_id: int):
    user = User.query.get_or_404(user_id)
    token = secrets.token_urlsafe(32)
    api_key = ApiKey(user_id=user.id, token=token, status="active")
    db.session.add(api_key)
    db.session.commit()
    log_audit(user_id=None, action="user.api_key.create", target_type="user", target_id=str(user.id))
    return ok_response(data=api_key.to_dict(), code=201)


@bp.delete("/<int:user_id>/api-key/<int:key_id>")
@admin_required
def delete_api_key(user_id: int, key_id: int):
    user = User.query.get_or_404(user_id)
    api_key = ApiKey.query.filter_by(id=key_id, user_id=user.id).first()
    if not api_key:
        return error_response("api key not found", code=404)
    db.session.delete(api_key)
    db.session.commit()
    log_audit(user_id=None, action="user.api_key.delete", target_type="user", target_id=str(user.id))
    return ok_response(message="deleted")
