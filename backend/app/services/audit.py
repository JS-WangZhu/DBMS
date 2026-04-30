from app.extensions import db
from app.models.audit_log import AuditLog


def log_audit(user_id, action, target_type=None, target_id=None, detail=None):
    item = AuditLog(
        user_id=user_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        detail_json=detail or {},
    )
    db.session.add(item)
    db.session.commit()
    return item
