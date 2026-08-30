from datetime import datetime, timezone

from app.extensions import db
from app.models.user_permission import UserClusterPermission
from app.services.audit import log_audit


def revoke_expired_data_source_permissions(now=None):
    """Remove only expired direct grants; inherited grants are untouched."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    expired = UserClusterPermission.query.filter(
        UserClusterPermission.expires_at.isnot(None),
        UserClusterPermission.expires_at <= now,
    ).all()
    for permission in expired:
        log_audit(
            user_id=None,
            action="data_source_permission.expired_revoke",
            target_type="user_cluster_permission",
            target_id=str(permission.id),
            detail={"user_id": permission.user_id, "cluster_id": permission.cluster_id, "expires_at": permission.expires_at.isoformat()},
        )
        db.session.delete(permission)
    if expired:
        db.session.commit()
    return len(expired)
