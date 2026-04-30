from app.extensions import db
from app.models.base import TimestampMixin
from app.models.backup_agent import BackupAgent


class BackupToolConfig(db.Model, TimestampMixin):
    __tablename__ = "backup_tool_configs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, unique=True)
    db_type = db.Column(db.String(32), nullable=False)
    tool_path = db.Column(db.String(512), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    backup_agent_id = db.Column(db.Integer, db.ForeignKey("backup_agents.id"), nullable=True)

    agent = db.relationship("BackupAgent", backref=db.backref("tool_configs", lazy="dynamic"))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "db_type": self.db_type,
            "tool_path": self.tool_path,
            "description": self.description,
            "enabled": self.enabled,
            "backup_agent_id": self.backup_agent_id,
            "agent_name": self.agent.name if self.agent else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
