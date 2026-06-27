from app.extensions import db
from app.models.base import TimestampMixin


class BackupAgent(db.Model, TimestampMixin):
    __tablename__ = "backup_agents"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    url = db.Column(db.String(512), nullable=False)  # Agent URL, e.g., http://192.168.1.100:5001
    api_key = db.Column(db.String(256), nullable=True)  # Agent API Key
    description = db.Column(db.String(255), nullable=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    is_default = db.Column(db.Boolean, nullable=False, default=False)

    # 关联的备份策略
    policies = db.relationship("BackupPolicy", back_populates="agent", lazy="dynamic")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "api_key": self.api_key,
            "description": self.description,
            "enabled": self.enabled,
            "is_default": self.is_default,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AgentInspectionStatus(db.Model, TimestampMixin):
    __tablename__ = "agent_inspection_statuses"

    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, nullable=False, unique=True, index=True)
    status = db.Column(db.String(32), nullable=False, default="unknown", index=True)
    message = db.Column(db.String(512), nullable=True)
    payload_json = db.Column(db.JSON, nullable=True)
    checked_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "status": self.status,
            "message": self.message,
            "payload_json": self.payload_json or {},
            "checked_at": self.checked_at.isoformat() if self.checked_at else None,
        }
