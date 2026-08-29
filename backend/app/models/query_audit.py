from sqlalchemy.dialects import mysql

from app.extensions import db
from app.models.base import TimestampMixin


class QueryAuditOutbox(db.Model, TimestampMixin):
    __tablename__ = "query_audit_outbox"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(36), nullable=False, unique=True, index=True)
    payload_blob = db.Column(
        db.LargeBinary().with_variant(mysql.LONGBLOB(), "mysql"),
        nullable=False,
    )
    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    next_retry_at = db.Column(db.DateTime, nullable=False, index=True)
    last_error = db.Column(db.Text, nullable=True)
