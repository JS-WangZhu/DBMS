from app.extensions import db
from app.models.base import TimestampMixin


class SqlReleaseConfig(db.Model, TimestampMixin):
    __tablename__ = "sql_release_configs"

    id = db.Column(db.Integer, primary_key=True)
    ai_review_enabled = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self):
        return {
            "id": self.id,
            "ai_review_enabled": bool(self.ai_review_enabled),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
