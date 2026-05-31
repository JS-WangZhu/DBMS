from app.extensions import db
from app.models.base import TimestampMixin


class ScheduledTask(db.Model, TimestampMixin):
    __tablename__ = "scheduled_tasks"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    task_type = db.Column(db.String(32), nullable=False)  # shell / python / http / sql
    cron_expr = db.Column(db.String(64), nullable=False)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    timeout_seconds = db.Column(db.Integer, nullable=False, default=300)
    max_retries = db.Column(db.Integer, nullable=False, default=0)
    content_json = db.Column(db.JSON, nullable=True)
    last_run_at = db.Column(db.DateTime, nullable=True)
    last_status = db.Column(db.String(32), nullable=True)
    last_message = db.Column(db.String(512), nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "task_type": self.task_type,
            "cron_expr": self.cron_expr,
            "enabled": bool(self.enabled),
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "content_json": self.content_json if isinstance(self.content_json, dict) else {},
            "last_run_at": self.last_run_at.isoformat() if self.last_run_at else None,
            "last_status": self.last_status,
            "last_message": self.last_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ScheduledTaskRun(db.Model, TimestampMixin):
    __tablename__ = "scheduled_task_runs"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("scheduled_tasks.id"), nullable=False, index=True)
    status = db.Column(db.String(32), nullable=False, default="running")
    trigger_type = db.Column(db.String(32), nullable=False, default="manual")
    retry_of_id = db.Column(db.Integer, nullable=True, index=True)
    attempt = db.Column(db.Integer, nullable=False, default=1)
    started_at = db.Column(db.DateTime, nullable=False)
    finished_at = db.Column(db.DateTime, nullable=True)
    duration_ms = db.Column(db.Integer, nullable=True)
    stdout = db.Column(db.Text, nullable=True)
    stderr = db.Column(db.Text, nullable=True)
    error_message = db.Column(db.Text, nullable=True)
    result_json = db.Column(db.JSON, nullable=True)

    task = db.relationship("ScheduledTask", backref=db.backref("runs", lazy=True))

    def to_dict(self) -> dict:
        task = self.task
        return {
            "id": self.id,
            "task_id": self.task_id,
            "task_name": task.name if task else None,
            "task_type": task.task_type if task else None,
            "status": self.status,
            "trigger_type": self.trigger_type,
            "retry_of_id": self.retry_of_id,
            "attempt": self.attempt,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_ms": self.duration_ms,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "error_message": self.error_message,
            "result_json": self.result_json if isinstance(self.result_json, dict) else {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
