from app.extensions import db
from app.models.base import TimestampMixin


class AliyunDomainConfig(db.Model, TimestampMixin):
    __tablename__ = "aliyun_domain_configs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, unique=True)
    description = db.Column(db.String(255), nullable=True)
    access_key = db.Column(db.String(255), nullable=False)
    secret_key = db.Column(db.String(255), nullable=False)
    domains = db.Column(db.JSON, nullable=False, default=list)
    enabled = db.Column(db.Boolean, nullable=False, default=True)

    def normalized_domains(self):
        values = self.domains if isinstance(self.domains, list) else []
        result = []
        seen = set()
        for item in values:
            domain = str(item or "").strip().lower()
            if not domain or domain in seen:
                continue
            seen.add(domain)
            result.append(domain)
        return result

    def manages_domain(self, domain):
        return str(domain or "").strip().lower() in set(self.normalized_domains())

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "access_key": self.access_key,
            "secret_key_set": bool(self.secret_key),
            "domains": self.normalized_domains(),
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
