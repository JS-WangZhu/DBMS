from app.extensions import db
from app.models.base import TimestampMixin

class AIModelConfig(db.Model, TimestampMixin):
    __tablename__ = "ai_model_configs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, unique=True)
    api_url = db.Column(db.String(255), nullable=False)  # OpenAI compatible URL
    api_key = db.Column(db.String(255), nullable=False)
    model_name = db.Column(db.String(128), nullable=False)
    is_default = db.Column(db.Boolean, default=False)
    enabled = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "api_url": self.api_url,
            "api_key": self.api_key[:8] + "******" if self.api_key else "",
            "model_name": self.model_name,
            "is_default": self.is_default,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
