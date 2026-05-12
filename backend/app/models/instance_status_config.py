from app.extensions import db
from app.models.base import TimestampMixin


class InstanceStatusConfig(db.Model, TimestampMixin):
    __tablename__ = "instance_status_configs"

    id = db.Column(db.Integer, primary_key=True)
    metric_refresh_timeout_seconds = db.Column(db.Integer, nullable=False, default=8)
    probe_poll_interval_seconds = db.Column(db.Integer, nullable=False, default=30)

    def to_dict(self):
        return {
            "id": self.id,
            "metric_refresh_timeout_seconds": int(self.metric_refresh_timeout_seconds or 8),
            "probe_poll_interval_seconds": int(self.probe_poll_interval_seconds or 30),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
