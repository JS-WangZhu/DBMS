from flask import Blueprint, request

from app.api.routes.common import active_user_required
from app.models.db_asset import DatabaseInstance
from app.services.monitor_snapshot_service import latest_snapshot_for_instance
from app.services.audit import log_audit
from app.services.instance_service import create_instance, list_instances_paginated
from app.utils.response import error_response, ok_response

bp = Blueprint("redis", __name__, url_prefix="/redis")


@bp.get("/instances")
@active_user_required
def redis_list_instances():
    page = request.args.get("page", 1)
    page_size = request.args.get("page_size", 20)
    keyword = request.args.get("keyword")
    cluster_id = request.args.get("cluster_id")
    namespace = request.args.get("namespace")
    business_line = request.args.get("business_line")
    environment = request.args.get("environment")
    items, total, page, page_size = list_instances_paginated(
        db_type="redis",
        page=page,
        page_size=page_size,
        keyword=keyword,
        cluster_id=cluster_id,
        namespace=namespace,
        business_line=business_line,
        environment=environment,
    )
    return ok_response(
        data={
            "items": [item.to_dict() for item in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    )


@bp.post("/instances")
@active_user_required
def redis_create_instance():
    payload = request.get_json(silent=True) or {}
    instance, err = create_instance(payload, db_type="redis")
    if err:
        return error_response(err, code=400)

    log_audit(user_id=None, action="redis.instance.create", target_type="instance", target_id=str(instance.id), detail=payload)
    return ok_response(data=instance.to_dict(), code=201)


@bp.get("/instances/<int:instance_id>/cluster-health")
@active_user_required
def redis_cluster_health(instance_id):
    instance = DatabaseInstance.query.filter_by(id=instance_id, db_type="redis").first()
    if not instance:
        return error_response("redis instance not found", code=404)

    snapshot = latest_snapshot_for_instance(instance_id=instance.id, db_type=instance.db_type, metric_type="status")
    payload = snapshot.payload_json if snapshot else {}
    return ok_response(data={"instance_id": instance.id, "cluster_info": payload.get("cluster_info", {})})
