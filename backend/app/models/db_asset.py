from app.extensions import db
from app.models.base import TimestampMixin


DB_TYPE_ENUM = db.Enum("mysql", "redis", "doris", "mongodb", name="db_type_enum", native_enum=False)


class DatabaseCluster(db.Model, TimestampMixin):
    __tablename__ = "db_clusters"

    id = db.Column(db.Integer, primary_key=True)
    namespace = db.Column(db.String(64), nullable=True, default=None)
    business_line = db.Column(db.String(64), nullable=True, default=None)
    environment = db.Column(db.String(64), nullable=True, default=None)
    name = db.Column(db.String(128), nullable=False)
    db_type = db.Column(DB_TYPE_ENUM, nullable=False)
    description = db.Column(db.String(255), nullable=True)
    ha_domain = db.Column(db.String(255), nullable=True)
    ha_status_json = db.Column(db.JSON, nullable=True)
    ha_mode = db.Column(db.String(16), nullable=False, default="none")
    data_access_route_json = db.Column(db.JSON, nullable=True)

    instances = db.relationship("DatabaseInstance", back_populates="cluster")

    def _data_access_route(self) -> dict:
        source = self.data_access_route_json if isinstance(self.data_access_route_json, dict) else {}

        def normalize(key):
            item = source.get(key) if isinstance(source.get(key), dict) else {}
            mode = str(item.get("mode") or "auto").strip().lower()
            if mode not in {"auto", "manual"}:
                mode = "auto"
            instance_id = item.get("instance_id")
            try:
                instance_id = int(instance_id) if instance_id not in (None, "") else None
            except (TypeError, ValueError):
                instance_id = None
            if mode != "manual":
                instance_id = None
            return {"mode": mode, "instance_id": instance_id}

        return {"query": normalize("query"), "change": normalize("change")}

    def to_dict(self) -> dict:
        business_line = self.business_line or self.namespace
        return {
            "id": self.id,
            "namespace": self.namespace,
            "business_line": business_line,
            "environment": self.environment,
            "name": self.name,
            "db_type": self.db_type,
            "description": self.description,
            "ha_domain": self.ha_domain,
            "ha_status_json": self.ha_status_json,
            "ha_mode": self.ha_mode if self.ha_mode in {"none", "orc", "dbms"} else "none",
            "data_access_route_json": self._data_access_route(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class DatabaseInstance(db.Model, TimestampMixin):
    __tablename__ = "db_instances"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    db_type = db.Column(DB_TYPE_ENUM, nullable=False)
    host_input = db.Column(db.String(255), nullable=False)
    resolved_ip = db.Column(db.String(64), nullable=True)
    port = db.Column(db.Integer, nullable=False)
    username = db.Column(db.String(128), nullable=True)
    password_encrypted = db.Column(db.Text, nullable=True)
    cluster_id = db.Column(db.Integer, db.ForeignKey("db_clusters.id"), nullable=True)
    role_label = db.Column(db.String(64), nullable=True)
    is_read_only = db.Column(db.Boolean, nullable=False, default=False)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    extra_json = db.Column(db.JSON, nullable=True)
    running_status = db.Column(db.String(32), nullable=True, default="unknown")

    cluster = db.relationship("DatabaseCluster", back_populates="instances")

    def to_dict(self) -> dict:
        extra = self.extra_json if isinstance(self.extra_json, dict) else {}
        host_domain = str(extra.get("domain") or "").strip() or None
        return {
            "id": self.id,
            "name": self.name,
            "db_type": self.db_type,
            "host_input": self.host_input,
            "host_domain": host_domain,
            "resolved_ip": self.resolved_ip,
            "port": self.port,
            "username": self.username,
            "cluster_id": self.cluster_id,
            "role_label": self.role_label,
            "is_read_only": self.is_read_only,
            "enabled": self.enabled,
            "extra_json": self.extra_json,
            "running_status": self.running_status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
