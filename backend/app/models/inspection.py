from app.extensions import db
from app.models.base import TimestampMixin


class InspectionConfig(db.Model, TimestampMixin):
    __tablename__ = "inspection_configs"

    id = db.Column(db.Integer, primary_key=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    interval_seconds = db.Column(db.Integer, nullable=False, default=60)
    collect_timeout_seconds = db.Column(db.Integer, nullable=False, default=8)
    notify_enabled = db.Column(db.Boolean, nullable=False, default=True)
    notify_recovery = db.Column(db.Boolean, nullable=False, default=True)
    notify_target_ids_json = db.Column(db.JSON, nullable=True)
    muted_cluster_ids_json = db.Column(db.JSON, nullable=True)
    last_run_at = db.Column(db.DateTime, nullable=True)
    last_run_summary_json = db.Column(db.JSON, nullable=True)
    extra_json = db.Column(db.JSON, nullable=True)

    def get_notify_target_ids(self):
        values = self.notify_target_ids_json or []
        if not isinstance(values, list):
            return []
        normalized = []
        for item in values:
            try:
                normalized.append(int(item))
            except (TypeError, ValueError):
                continue
        return sorted(set(normalized))

    def get_muted_cluster_ids(self):
        values = self.muted_cluster_ids_json or []
        if not isinstance(values, list):
            return []
        normalized = []
        for item in values:
            try:
                normalized.append(int(item))
            except (TypeError, ValueError):
                continue
        return sorted(set(normalized))

    def to_dict(self):
        return {
            "id": self.id,
            "enabled": bool(self.enabled),
            "interval_seconds": int(self.interval_seconds or 60),
            "collect_timeout_seconds": int(self.collect_timeout_seconds or 8),
            "notify_enabled": bool(self.notify_enabled),
            "notify_recovery": bool(self.notify_recovery),
            "notify_target_ids": self.get_notify_target_ids(),
            "muted_cluster_ids": self.get_muted_cluster_ids(),
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_run_summary_json": self.last_run_summary_json or {},
            "extra_json": self.extra_json or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class InspectionAlert(db.Model, TimestampMixin):
    __tablename__ = "inspection_alerts"
    __table_args__ = (
        db.UniqueConstraint("instance_id", "issue_key", name="uq_inspection_alert_instance_issue"),
    )

    id = db.Column(db.Integer, primary_key=True)
    instance_id = db.Column(db.Integer, nullable=False, index=True)
    cluster_id = db.Column(db.Integer, nullable=True, index=True)
    db_type = db.Column(db.String(32), nullable=False, index=True)
    issue_key = db.Column(db.String(128), nullable=False)
    issue_name = db.Column(db.String(255), nullable=False)
    severity = db.Column(db.String(32), nullable=False, default="warning")
    status = db.Column(db.String(32), nullable=False, default="open")
    message = db.Column(db.String(512), nullable=True)
    first_seen_at = db.Column(db.DateTime, nullable=True)
    last_seen_at = db.Column(db.DateTime, nullable=True)
    recovered_at = db.Column(db.DateTime, nullable=True)
    last_payload_json = db.Column(db.JSON, nullable=True)
    notify_count = db.Column(db.Integer, nullable=False, default=0)
    last_notified_at = db.Column(db.DateTime, nullable=True)
    recovery_notified_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "instance_id": self.instance_id,
            "cluster_id": self.cluster_id,
            "db_type": self.db_type,
            "issue_key": self.issue_key,
            "issue_name": self.issue_name,
            "severity": self.severity,
            "status": self.status,
            "message": self.message,
            "first_seen_at": self.first_seen_at.isoformat() if self.first_seen_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "recovered_at": self.recovered_at.isoformat() if self.recovered_at else None,
            "last_payload_json": self.last_payload_json or {},
            "notify_count": self.notify_count,
            "last_notified_at": self.last_notified_at.isoformat() if self.last_notified_at else None,
            "recovery_notified_at": self.recovery_notified_at.isoformat() if self.recovery_notified_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
