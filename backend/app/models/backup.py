from app.extensions import db
from app.models.base import TimestampMixin


def _utc_isoformat(value):
    if not value:
        return None
    if value.tzinfo is None:
        return f"{value.isoformat()}+00:00"
    return value.isoformat()


TARGET_TYPE_ENUM = db.Enum("instance", "cluster", name="backup_target_type", native_enum=False)
BACKUP_TYPE_ENUM = db.Enum("full", "incremental", name="backup_type_enum", native_enum=False)
BACKUP_STATUS_ENUM = db.Enum("running", "success", "failed", "cancelled", name="backup_status_enum", native_enum=False)
DB_TYPE_BACKUP_ENUM = db.Enum("mysql", "mongodb", "postgresql", name="backup_db_type", native_enum=False)


class BackupPolicy(db.Model, TimestampMixin):
    __tablename__ = "backup_policies"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    target_type = db.Column(TARGET_TYPE_ENUM, nullable=False)
    target_id = db.Column(db.Integer, nullable=False)
    db_type = db.Column(DB_TYPE_BACKUP_ENUM, nullable=False)
    backup_type = db.Column(BACKUP_TYPE_ENUM, nullable=False, default="full")
    tool_name = db.Column(db.String(64), nullable=False)
    backup_tool_config_id = db.Column(db.Integer, db.ForeignKey("backup_tool_configs.id"), nullable=True)
    cron_expr = db.Column(db.String(64), nullable=False)
    storage_path = db.Column(db.String(255), nullable=False)
    retain_days = db.Column(db.Integer, nullable=False, default=7)
    compress = db.Column(db.Boolean, nullable=False, default=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    s3_storage_config_id = db.Column(db.Integer, db.ForeignKey("s3_storage_configs.id"), nullable=True)
    backup_agent_id = db.Column(db.Integer, db.ForeignKey("backup_agents.id"), nullable=True)
    extra_json = db.Column(db.JSON, nullable=True)

    logs = db.relationship("BackupLog", back_populates="policy")
    s3_storage_config = db.relationship("S3StorageConfig", backref="backup_policies")
    backup_tool_config = db.relationship("BackupToolConfig", backref="backup_policies")
    agent = db.relationship("BackupAgent", back_populates="policies")

    def to_dict(self) -> dict:
        extra = self.extra_json if isinstance(self.extra_json, dict) else {}
        compress_method = extra.get("compress_method")
        allowed_methods = {"default", "gzip", "lz4", "zstd", "none"} if self.db_type == "postgresql" else {"none", "gzip", "zstd"}
        if compress_method not in allowed_methods:
            compress_method = ("default" if self.compress else "none") if self.db_type == "postgresql" else ("gzip" if self.compress else "none")
        return {
            "id": self.id,
            "name": self.name,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "db_type": self.db_type,
            "backup_type": self.backup_type,
            "tool_name": self.tool_name,
            "backup_tool_config_id": self.backup_tool_config_id,
            "cron_expr": self.cron_expr,
            "storage_path": self.storage_path,
            "retain_days": self.retain_days,
            "compress": self.compress,
            "compress_method": compress_method,
            "enabled": self.enabled,
            "s3_storage_config_id": self.s3_storage_config_id,
            "backup_agent_id": self.backup_agent_id,
            "agent_name": self.agent.name if self.agent else None,
            "extra_json": self.extra_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class BackupLog(db.Model, TimestampMixin):
    __tablename__ = "backup_logs"

    id = db.Column(db.Integer, primary_key=True)
    policy_id = db.Column(db.Integer, db.ForeignKey("backup_policies.id"), nullable=False)
    started_at = db.Column(db.DateTime, nullable=False)
    finished_at = db.Column(db.DateTime, nullable=True)
    file_path = db.Column(db.String(255), nullable=True)
    size_bytes = db.Column(db.Integer, nullable=True)
    status = db.Column(BACKUP_STATUS_ENUM, nullable=False)
    error_message = db.Column(db.Text, nullable=True)
    extra_json = db.Column(db.JSON, nullable=True)

    policy = db.relationship("BackupPolicy", back_populates="logs")

    def to_dict(self) -> dict:
        extra = self.extra_json or {}
        compress_method = extra.get("compress_method")
        if compress_method not in {"default", "none", "gzip", "lz4", "zstd"}:
            path = (self.file_path or "").lower()
            if path.endswith(".gz"):
                compress_method = "gzip"
            elif path.endswith(".zst"):
                compress_method = "zstd"
            else:
                compress_method = "gzip" if extra.get("compress") else "none"
        return {
            "id": self.id,
            "policy_id": self.policy_id,
            "policy_name": self.policy.name if self.policy else None,
            "started_at": _utc_isoformat(self.started_at),
            "finished_at": _utc_isoformat(self.finished_at),
            "file_path": self.file_path,
            "size_bytes": self.size_bytes,
            "status": self.status,
            "compress": extra.get("compress"),
            "compress_method": compress_method,
            "encrypt": extra.get("encrypt"),
            "error_message": self.error_message,
            "extra_json": extra,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
