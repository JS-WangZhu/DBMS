from app.extensions import db
from app.models.base import TimestampMixin


class PhysicalDiscoveryConfig(db.Model, TimestampMixin):
    __tablename__ = "physical_discovery_configs"

    id = db.Column(db.Integer, primary_key=True)
    enabled = db.Column(db.Boolean, nullable=False, default=False)
    poll_interval_minutes = db.Column(db.Integer, nullable=False, default=30)
    connect_timeout_seconds = db.Column(db.Integer, nullable=False, default=10)
    batch_size = db.Column(db.Integer, nullable=False, default=500)

    def to_dict(self):
        return {
            "id": self.id,
            "enabled": bool(self.enabled),
            "poll_interval_minutes": int(self.poll_interval_minutes or 30),
            "connect_timeout_seconds": int(self.connect_timeout_seconds or 10),
            "batch_size": int(self.batch_size or 500),
        }


class VCenterConfig(db.Model, TimestampMixin):
    __tablename__ = "vcenter_configs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, unique=True)
    address = db.Column(db.String(255), nullable=False)
    port = db.Column(db.Integer, nullable=False, default=443)
    cidrs_json = db.Column(db.JSON, nullable=False)
    username = db.Column(db.String(128), nullable=False)
    password_encrypted = db.Column(db.Text, nullable=False)
    verify_ssl = db.Column(db.Boolean, nullable=False, default=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    deleted = db.Column(db.Boolean, nullable=False, default=False)
    last_test_status = db.Column(db.String(32), nullable=True)
    last_test_message = db.Column(db.String(500), nullable=True)
    last_tested_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (db.UniqueConstraint("address", "port", name="uq_vcenter_address_port"),)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "address": self.address,
            "port": int(self.port or 443),
            "cidrs": list(self.cidrs_json or []),
            "username": self.username,
            "password_configured": bool(self.password_encrypted),
            "verify_ssl": bool(self.verify_ssl),
            "enabled": bool(self.enabled),
            "last_test_status": self.last_test_status,
            "last_test_message": self.last_test_message,
            "last_tested_at": self.last_tested_at.isoformat() if self.last_tested_at else None,
        }


class PhysicalDiscoveryRun(db.Model, TimestampMixin):
    __tablename__ = "physical_discovery_runs"

    id = db.Column(db.Integer, primary_key=True)
    vcenter_id = db.Column(db.Integer, db.ForeignKey("vcenter_configs.id"), nullable=True)
    vcenter_name = db.Column(db.String(128), nullable=True)
    trigger_type = db.Column(db.String(16), nullable=False)
    status = db.Column(db.String(32), nullable=False, default="running")
    started_at = db.Column(db.DateTime, nullable=False)
    finished_at = db.Column(db.DateTime, nullable=True)
    total_count = db.Column(db.Integer, nullable=False, default=0)
    success_count = db.Column(db.Integer, nullable=False, default=0)
    failed_count = db.Column(db.Integer, nullable=False, default=0)
    unmatched_count = db.Column(db.Integer, nullable=False, default=0)
    error_message = db.Column(db.String(500), nullable=True)


class PhysicalDiscoveryDetail(db.Model, TimestampMixin):
    __tablename__ = "physical_discovery_details"

    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey("physical_discovery_runs.id"), nullable=False, index=True)
    instance_id = db.Column(db.Integer, db.ForeignKey("db_instances.id"), nullable=True)
    instance_name = db.Column(db.String(128), nullable=True)
    input_ip = db.Column(db.String(64), nullable=True)
    status = db.Column(db.String(32), nullable=False)
    discovered_address = db.Column(db.String(64), nullable=True)
    error_code = db.Column(db.String(64), nullable=True)
    error_message = db.Column(db.String(500), nullable=True)
