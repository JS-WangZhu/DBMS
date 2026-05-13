from datetime import datetime

from app.models.backup import BackupLog
from app.tasks.scheduler import _trigger_from_expr


def test_backup_log_execution_times_are_serialized_as_utc():
    log = BackupLog(
        policy_id=1,
        started_at=datetime(2026, 5, 13, 2, 30, 0),
        finished_at=datetime(2026, 5, 13, 2, 45, 0),
        status="success",
    )

    data = log.to_dict()

    assert data["started_at"] == "2026-05-13T02:30:00+00:00"
    assert data["finished_at"] == "2026-05-13T02:45:00+00:00"


def test_backup_cron_trigger_uses_configured_beijing_timezone(app):
    app.config["SCHEDULER_TIMEZONE"] = "Asia/Shanghai"

    with app.app_context():
        trigger = _trigger_from_expr("0 2 * * *")

    assert str(trigger.timezone) == "Asia/Shanghai"
