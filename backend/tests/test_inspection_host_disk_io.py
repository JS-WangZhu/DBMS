from app.extensions import db
from app.models.db_asset import DatabaseInstance
from app.services.inspection_service import DEFAULT_THRESHOLDS, _extract_issues


def test_host_disk_io_latency_over_threshold_creates_issue(app):
    with app.app_context():
        instance = DatabaseInstance(name="io-latency", db_type="mysql", host_input="127.0.0.1", port=3306)
        db.session.add(instance)
        db.session.commit()

        issues = _extract_issues(instance, {
            "ok": True,
            "ping_ok": True,
            "host_disk_io_latency_ms": 25.5,
            "host_disk_io_device": "sdb",
        }, {**DEFAULT_THRESHOLDS, "host_disk_io_latency_ms": 20})

    issue = next(item for item in issues if item["issue_key"] == "host_disk_io_latency")
    assert issue["severity"] == "warning"
    assert "25.5ms" in issue["message"]
    assert "sdb" in issue["message"]
