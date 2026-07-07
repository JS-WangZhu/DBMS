from app.extensions import db
from app.models.db_asset import DatabaseInstance
from app.services.inspection_service import DEFAULT_THRESHOLDS, _extract_issues


def _issues(app, payload):
    with app.app_context():
        instance = DatabaseInstance(
            name="redis-cluster-node", db_type="redis", host_input="127.0.0.1", port=6379,
        )
        db.session.add(instance)
        db.session.commit()
        return _extract_issues(instance, payload, DEFAULT_THRESHOLDS)


def test_redis_cluster_state_fail_is_critical_issue(app):
    issues = _issues(app, {
        "ok": True,
        "ping_ok": True,
        "cluster_enabled": 1,
        "cluster_info": {"cluster_state": "fail"},
    })

    issue = next(item for item in issues if item["issue_key"] == "redis_cluster_state")
    assert issue["severity"] == "critical"
    assert "fail" in issue["message"]


def test_redis_cluster_missing_state_is_critical_issue(app):
    issues = _issues(app, {"ok": True, "ping_ok": True, "redis_mode": "cluster", "cluster_info": {}})

    assert any(item["issue_key"] == "redis_cluster_state" for item in issues)


def test_redis_cluster_ok_and_non_cluster_do_not_create_cluster_issue(app):
    ok_issues = _issues(app, {
        "ok": True,
        "ping_ok": True,
        "cluster_enabled": 1,
        "cluster_info": {"cluster_state": "ok"},
    })
    standalone_issues = _issues(app, {"ok": True, "ping_ok": True, "cluster_enabled": 0})

    assert not any(item["issue_key"] == "redis_cluster_state" for item in ok_issues)
    assert not any(item["issue_key"] == "redis_cluster_state" for item in standalone_issues)
