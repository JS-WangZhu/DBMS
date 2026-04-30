from app.extensions import db
from app.models.base import TimestampMixin


NOTIFY_CHANNEL_ENUM = db.Enum("wecom", "email", name="notify_channel_enum", native_enum=False)


class BackupNotifyTarget(db.Model, TimestampMixin):
    __tablename__ = "backup_notify_targets"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    channel = db.Column(NOTIFY_CHANNEL_ENUM, nullable=False)
    address = db.Column(db.String(255), nullable=False)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    extra_json = db.Column(db.JSON, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "channel": self.channel,
            "address": self.address,
            "enabled": self.enabled,
            "extra_json": self.extra_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
