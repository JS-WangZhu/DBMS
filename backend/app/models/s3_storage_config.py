from app.extensions import db
from app.models.base import TimestampMixin


class S3StorageConfig(db.Model, TimestampMixin):
    __tablename__ = "s3_storage_configs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, unique=True)
    description = db.Column(db.String(255), nullable=True)
    bucket = db.Column(db.String(255), nullable=False)
    prefix = db.Column(db.String(255), nullable=True)
    region = db.Column(db.String(64), nullable=True)
    endpoint_url = db.Column(db.String(512), nullable=True)
    access_key = db.Column(db.String(255), nullable=False)
    secret_key = db.Column(db.String(255), nullable=False)
    enabled = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "bucket": self.bucket,
            "prefix": self.prefix,
            "region": self.region,
            "endpoint_url": self.endpoint_url,
            "access_key": self.access_key,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def to_s3_config(self) -> dict:
        return {
            "enabled": self.enabled,
            "bucket": self.bucket,
            "prefix": self.prefix,
            "region": self.region,
            "endpoint_url": self.endpoint_url,
            "access_key": self.access_key,
            "secret_key": self.secret_key,
        }
