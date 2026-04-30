from flask import Blueprint, request

from app.api.routes.common import active_user_required
from app.extensions import db
from app.models.db_asset import DatabaseInstance
from app.services.audit import log_audit
from app.services.dns_resolver import refresh_all_dns
from app.utils.response import ok_response

bp = Blueprint("dns", __name__, url_prefix="/dns")


@bp.post("/refresh")
@active_user_required
def refresh_dns():
    payload = request.get_json(silent=True) or {}
    instance_id = payload.get("instance_id")

    query = DatabaseInstance.query
    if instance_id:
        query = query.filter_by(id=int(instance_id))

    items = query.all()
    refreshed = refresh_all_dns(items)
    db.session.commit()

    log_audit(user_id=None, action="dns.refresh.manual", detail={"count": len(refreshed), "instance_id": instance_id})
    return ok_response(data={"count": len(refreshed), "items": refreshed})
