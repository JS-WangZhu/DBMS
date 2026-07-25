from app.extensions import db
from app.models.base import TimestampMixin


class AuthSession(db.Model, TimestampMixin):
    __tablename__ = "auth_sessions"

    id = db.Column(db.String(36), primary_key=True)
    # Production users.id is BIGINT (see sql/init.sql). Keep SQLite's INTEGER
    # affinity in tests so generated primary keys continue to work there.
    user_id = db.Column(
        db.BigInteger().with_variant(db.Integer, "sqlite"),
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    last_activity_at = db.Column(db.DateTime, nullable=False, index=True)
    revoked_at = db.Column(db.DateTime, nullable=True)
    revoke_reason = db.Column(db.String(64), nullable=True)
    ip_address = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(255), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "last_activity_at": self.last_activity_at.isoformat() if self.last_activity_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "revoke_reason": self.revoke_reason,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
