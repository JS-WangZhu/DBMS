from app.extensions import db
from app.models.base import TimestampMixin


SUPPORTED_DIAGNOSIS_DB_TYPES = ("mysql", "postgresql", "mongodb", "redis", "doris")


class ParameterCollectionConfig(db.Model, TimestampMixin):
    __tablename__ = "parameter_collection_configs"

    id = db.Column(db.Integer, primary_key=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    cron_expr = db.Column(db.String(64), nullable=False, default="0 0 * * *")
    db_types_json = db.Column(db.JSON, nullable=True)
    timeout_seconds = db.Column(db.Integer, nullable=False, default=15)
    max_workers = db.Column(db.Integer, nullable=False, default=5)
    retention_versions = db.Column(db.Integer, nullable=False, default=3)
    last_run_at = db.Column(db.DateTime, nullable=True)
    last_status = db.Column(db.String(32), nullable=True)
    last_message = db.Column(db.String(512), nullable=True)

    def selected_db_types(self):
        values = self.db_types_json if isinstance(self.db_types_json, list) else []
        selected = [item for item in values if item in SUPPORTED_DIAGNOSIS_DB_TYPES]
        return selected or list(SUPPORTED_DIAGNOSIS_DB_TYPES)

    def to_dict(self):
        return {
            "id": self.id,
            "enabled": bool(self.enabled),
            "cron_expr": self.cron_expr or "0 0 * * *",
            "db_types": self.selected_db_types(),
            "timeout_seconds": int(self.timeout_seconds or 15),
            "max_workers": int(self.max_workers or 5),
            "retention_versions": max(1, int(self.retention_versions or 3)),
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_status": self.last_status,
            "last_message": self.last_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ParameterCollectionSnapshot(db.Model):
    __tablename__ = "parameter_collection_snapshots"

    id = db.Column(db.Integer, primary_key=True)
    # Production db_instances.id is BIGINT (see sql/init.sql). SQLite keeps
    # INTEGER affinity so its in-memory foreign-key tests remain compatible.
    instance_id = db.Column(
        db.BigInteger().with_variant(db.Integer, "sqlite"),
        db.ForeignKey("db_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    collected_at = db.Column(db.DateTime, nullable=False, index=True)
    status = db.Column(db.String(32), nullable=False, default="success")
    error_message = db.Column(db.Text, nullable=True)
    parameter_count = db.Column(db.Integer, nullable=False, default=0)
    parameters_json = db.Column(db.JSON, nullable=True)
    source = db.Column(db.String(16), nullable=False, default="server")
    duration_ms = db.Column(db.Integer, nullable=True)

    instance = db.relationship("DatabaseInstance")

    def to_dict(self, include_parameters=True):
        data = {
            "id": self.id,
            "instance_id": self.instance_id,
            "collected_at": self.collected_at.isoformat() if self.collected_at else None,
            "status": self.status,
            "error_message": self.error_message,
            "parameter_count": int(self.parameter_count or 0),
            "source": self.source or "server",
            "duration_ms": self.duration_ms,
        }
        if include_parameters:
            data["parameters"] = self.parameters_json if isinstance(self.parameters_json, list) else []
        return data
