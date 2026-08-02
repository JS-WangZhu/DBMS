from app.extensions import db
from app.models.base import TimestampMixin


class SqlRelease(db.Model, TimestampMixin):
    __tablename__ = "sql_releases"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    # Production users/db_clusters/db_instances primary keys are BIGINT in
    # sql/init.sql. SQLite keeps INTEGER affinity for in-memory tests.
    applicant_id = db.Column(
        db.BigInteger().with_variant(db.Integer, "sqlite"),
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    cluster_id = db.Column(
        db.BigInteger().with_variant(db.Integer, "sqlite"),
        db.ForeignKey("db_clusters.id"),
        nullable=False,
        index=True,
    )
    instance_id = db.Column(
        db.BigInteger().with_variant(db.Integer, "sqlite"),
        db.ForeignKey("db_instances.id"),
        nullable=True,
    )
    db_type = db.Column(db.String(32), nullable=False, default="mysql", index=True)
    database_name = db.Column(db.String(128), nullable=False)
    sql_text = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(32), nullable=False, default="pending", index=True)
    ai_passed = db.Column(db.Boolean, nullable=False, default=False)
    force_submitted = db.Column(db.Boolean, nullable=False, default=False)
    ai_summary = db.Column(db.Text, nullable=True)
    review_json = db.Column(db.JSON, nullable=False)
    execution_result_json = db.Column(db.JSON, nullable=True)
    rollback_backup_path = db.Column(db.String(512), nullable=True)
    executed_by = db.Column(
        db.BigInteger().with_variant(db.Integer, "sqlite"),
        db.ForeignKey("users.id"),
        nullable=True,
    )
    executed_at = db.Column(db.DateTime, nullable=True)

    applicant = db.relationship("User", foreign_keys=[applicant_id])
    executor = db.relationship("User", foreign_keys=[executed_by])
    cluster = db.relationship("DatabaseCluster")
    instance = db.relationship("DatabaseInstance")

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "applicant_id": self.applicant_id,
            "applicant_name": self.applicant.display_name or self.applicant.username if self.applicant else None,
            "cluster_id": self.cluster_id,
            "cluster_name": self.cluster.name if self.cluster else None,
            "instance_id": self.instance_id,
            "instance_name": self.instance.name if self.instance else None,
            "db_type": self.db_type or "mysql",
            "database": self.database_name,
            "sql": self.sql_text,
            "status": self.status,
            "ai_passed": bool(self.ai_passed),
            "force_submitted": bool(self.force_submitted),
            "ai_summary": self.ai_summary,
            "reviews": self.review_json or [],
            "execution_result": self.execution_result_json,
            "rollback_backup_path": self.rollback_backup_path,
            "executed_by": self.executed_by,
            "executor_name": self.executor.display_name or self.executor.username if self.executor else None,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
