from datetime import datetime, timezone

from flask import Blueprint, request
from sqlalchemy import or_

from app.api.routes.common import (
    get_current_user,
    get_effective_cluster_permissions,
    require_menu_permission,
)
from app.extensions import db
from app.models.db_asset import DatabaseCluster
from app.models.user import User
from app.models.user_permission import (
    DataSourcePermissionApplication,
    DataSourcePermissionApplicationItem,
    UserClusterPermission,
)
from app.services.audit import log_audit
from app.utils.response import error_response, ok_response


bp = Blueprint(
    "data_source_permission_applications",
    __name__,
    url_prefix="/data-source-permission-applications",
)

PRODUCTION_ENVIRONMENTS = {"prod", "production", "生产", "生产环境"}
VALID_STATUSES = {"pending", "approved", "rejected"}


def _is_production(cluster):
    return str(cluster.environment or "").strip().lower() in PRODUCTION_ENVIRONMENTS


def _cluster_dict(cluster):
    data = cluster.to_dict()
    data["project"] = cluster.business_line or cluster.namespace
    return data


def _application_dict(application):
    applicant = User.query.get(application.applicant_id)
    reviewer = User.query.get(application.reviewer_id) if application.reviewer_id else None
    item_rows = DataSourcePermissionApplicationItem.query.filter_by(
        application_id=application.id
    ).order_by(DataSourcePermissionApplicationItem.id.asc()).all()
    cluster_ids = [item.cluster_id for item in item_rows]
    clusters = {
        cluster.id: cluster
        for cluster in DatabaseCluster.query.filter(DatabaseCluster.id.in_(cluster_ids)).all()
    } if cluster_ids else {}
    return {
        "id": application.id,
        "status": application.status,
        "reason": application.reason,
        "review_comment": application.review_comment,
        "applicant": applicant.to_dict() if applicant else None,
        "reviewer": reviewer.to_dict() if reviewer else None,
        "reviewed_at": application.reviewed_at.isoformat() if application.reviewed_at else None,
        "created_at": application.created_at.isoformat() if application.created_at else None,
        "updated_at": application.updated_at.isoformat() if application.updated_at else None,
        "items": [
            {
                "cluster_id": item.cluster_id,
                "cluster": _cluster_dict(clusters[item.cluster_id]) if item.cluster_id in clusters else None,
                "can_query": bool(item.can_query),
                "can_change": bool(item.can_change),
            }
            for item in item_rows
        ],
    }


def _page_params():
    try:
        page = max(int(request.args.get("page", 1)), 1)
        page_size = min(max(int(request.args.get("page_size", 20)), 1), 100)
    except (TypeError, ValueError):
        page, page_size = 1, 20
    return page, page_size


@bp.get("/sources")
@require_menu_permission("data_permission_apply")
def list_production_sources():
    user = get_current_user()
    clusters = [
        cluster
        for cluster in DatabaseCluster.query.order_by(
            DatabaseCluster.db_type.asc(), DatabaseCluster.business_line.asc(), DatabaseCluster.name.asc()
        ).all()
        if _is_production(cluster)
    ]
    effective = get_effective_cluster_permissions(user.id) if user.role != "admin" else {
        cluster.id: {"can_query": True, "can_change": True, "can_execute": True}
        for cluster in clusters
    }
    return ok_response(data={
        "clusters": [_cluster_dict(cluster) for cluster in clusters],
        "effective_permissions": [
            {"cluster_id": cluster.id, **effective.get(cluster.id, {})}
            for cluster in clusters
        ],
    })


@bp.get("")
@require_menu_permission("data_permission_apply")
def list_applications():
    user = get_current_user()
    page, page_size = _page_params()
    query = DataSourcePermissionApplication.query
    if user.role != "admin":
        query = query.filter_by(applicant_id=user.id)
    status = str(request.args.get("status") or "").strip().lower()
    if status in VALID_STATUSES:
        query = query.filter_by(status=status)
    keyword = str(request.args.get("keyword") or "").strip()
    if keyword and user.role == "admin":
        matched_users = User.query.filter(or_(
            User.username.like(f"%{keyword}%"),
            User.display_name.like(f"%{keyword}%"),
        )).with_entities(User.id)
        query = query.filter(DataSourcePermissionApplication.applicant_id.in_(matched_users))
    total = query.count()
    rows = query.order_by(DataSourcePermissionApplication.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    return ok_response(data={
        "items": [_application_dict(item) for item in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@bp.post("")
@require_menu_permission("data_permission_apply")
def create_application():
    user = get_current_user()
    if user.role == "admin":
        return error_response("系统管理员无需申请数据源权限", code=400)
    payload = request.get_json(silent=True) or {}
    normalized = []
    seen = set()
    effective = get_effective_cluster_permissions(user.id)
    for raw in payload.get("items") if isinstance(payload.get("items"), list) else []:
        try:
            cluster_id = int(raw.get("cluster_id"))
        except (AttributeError, TypeError, ValueError):
            continue
        if cluster_id in seen:
            continue
        cluster = DatabaseCluster.query.get(cluster_id)
        if not cluster or not _is_production(cluster):
            return error_response("只能申请生产环境数据源权限", code=400)
        can_query = raw.get("can_query") is True and not effective.get(cluster_id, {}).get("can_query")
        can_change = raw.get("can_change") is True and not effective.get(cluster_id, {}).get("can_change")
        if not can_query and not can_change:
            continue
        seen.add(cluster_id)
        normalized.append({
            "cluster_id": cluster_id,
            "can_query": can_query,
            "can_change": can_change,
        })
    if not normalized:
        return error_response("请选择至少一项尚未拥有的查询或变更权限", code=400)
    reason = str(payload.get("reason") or "").strip()
    if not reason:
        return error_response("请填写申请原因", code=400)
    application = DataSourcePermissionApplication(
        applicant_id=user.id,
        status="pending",
        reason=reason[:500],
    )
    db.session.add(application)
    db.session.flush()
    for item in normalized:
        db.session.add(DataSourcePermissionApplicationItem(application_id=application.id, **item))
    db.session.commit()
    log_audit(
        user_id=user.id,
        action="data_source_permission.application.create",
        target_type="data_source_permission_application",
        target_id=str(application.id),
        detail={"items": normalized},
    )
    return ok_response(data=_application_dict(application), message="权限申请已提交", code=201)


@bp.patch("/<int:application_id>/review")
@require_menu_permission("data_permission_apply")
def review_application(application_id):
    reviewer = get_current_user()
    if reviewer.role != "admin":
        return error_response("admin required", code=403)
    application = DataSourcePermissionApplication.query.get_or_404(application_id)
    if application.status != "pending":
        return error_response("该申请已完成审核", code=409)
    payload = request.get_json(silent=True) or {}
    decision = str(payload.get("decision") or "").strip().lower()
    if decision not in {"approved", "rejected"}:
        return error_response("decision must be approved or rejected", code=400)
    comment = str(payload.get("comment") or "").strip()
    if decision == "rejected" and not comment:
        return error_response("驳回时请填写审核意见", code=400)

    if decision == "approved":
        items = DataSourcePermissionApplicationItem.query.filter_by(application_id=application.id).all()
        for item in items:
            permission = UserClusterPermission.query.filter_by(
                user_id=application.applicant_id,
                cluster_id=item.cluster_id,
            ).first()
            if not permission:
                permission = UserClusterPermission(
                    user_id=application.applicant_id,
                    cluster_id=item.cluster_id,
                    can_query=False,
                    can_change=False,
                    can_execute=False,
                )
                db.session.add(permission)
            permission.can_query = bool(permission.can_query or item.can_query)
            permission.can_change = bool(permission.can_change or item.can_change)
            # Execution permission is deliberately outside this application flow.

    application.status = decision
    application.review_comment = comment[:500] or None
    application.reviewer_id = reviewer.id
    application.reviewed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.session.commit()
    log_audit(
        user_id=reviewer.id,
        action=f"data_source_permission.application.{decision}",
        target_type="data_source_permission_application",
        target_id=str(application.id),
        detail={"comment": application.review_comment},
    )
    return ok_response(data=_application_dict(application), message="审核已完成")
