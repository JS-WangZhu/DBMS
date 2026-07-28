from app.extensions import db
from app.models.base import TimestampMixin


class JumpServerConfig(db.Model, TimestampMixin):
    __tablename__ = "jumpserver_configs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, unique=True)
    base_url = db.Column(db.String(512), nullable=False)
    web_url_template = db.Column(
        db.String(1024),
        nullable=False,
        default="{base_url}/luna/?asset={asset_id}",
    )
    verify_ssl = db.Column(db.Boolean, nullable=False, default=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    last_test_status = db.Column(db.String(32), nullable=True)
    last_test_error = db.Column(db.String(512), nullable=True)
    last_test_at = db.Column(db.DateTime, nullable=True)

    database_instances = db.relationship("DatabaseInstance", back_populates="jumpserver_config")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "base_url": self.base_url,
            "web_url_template": self.web_url_template,
            "verify_ssl": bool(self.verify_ssl),
            "enabled": bool(self.enabled),
            "last_test_status": self.last_test_status,
            "last_test_error": self.last_test_error,
            "last_test_at": self.last_test_at.isoformat() if self.last_test_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
