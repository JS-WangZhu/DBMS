from types import SimpleNamespace

import app.services.inspection_service as inspection_service


def _instance(db_type):
    return SimpleNamespace(db_type=db_type)


def test_mysql_aborted_connects_uses_ten_minute_increase(monkeypatch):
    monkeypatch.setattr(inspection_service, "_metric_counter_increase_window", lambda *args: 2)
    payload = {"ok": True, "ping_ok": True, "aborted_connects_total": 102}

    issues = inspection_service._extract_issues(
        _instance("mysql"), payload, dict(inspection_service.DEFAULT_THRESHOLDS)
    )

    assert payload["aborted_connects_increase_10m"] == 2
    assert "mysql_aborted_connects" in {item["issue_key"] for item in issues}


def test_redis_blocked_clients_uses_ten_minute_peak(monkeypatch):
    monkeypatch.setattr(inspection_service, "_metric_max_window", lambda *args: 2)
    payload = {"ok": True, "ping_ok": True, "blocked_clients": 0}

    issues = inspection_service._extract_issues(
        _instance("redis"), payload, dict(inspection_service.DEFAULT_THRESHOLDS)
    )

    assert payload["blocked_clients_max_10m"] == 2
    assert "redis_blocked_clients" in {item["issue_key"] for item in issues}


def test_postgresql_fatal_sessions_uses_ten_minute_increase(monkeypatch):
    monkeypatch.setattr(inspection_service, "_metric_counter_increase_window", lambda *args: 2)
    payload = {"ok": True, "ping_ok": True, "sessions_fatal_total": 12}

    issues = inspection_service._extract_issues(
        _instance("postgresql"), payload, dict(inspection_service.DEFAULT_THRESHOLDS)
    )

    assert payload["sessions_fatal_increase_10m"] == 2
    assert "postgresql_sessions_fatal" in {item["issue_key"] for item in issues}


def test_connection_anomaly_threshold_is_strictly_greater_than_one(monkeypatch):
    monkeypatch.setattr(inspection_service, "_metric_counter_increase_window", lambda *args: 1)
    payload = {"ok": True, "ping_ok": True, "aborted_connects_total": 101}

    issues = inspection_service._extract_issues(
        _instance("mysql"), payload, dict(inspection_service.DEFAULT_THRESHOLDS)
    )

    assert "mysql_aborted_connects" not in {item["issue_key"] for item in issues}


def test_counter_increase_handles_statistics_reset(monkeypatch):
    monkeypatch.setattr(inspection_service, "_metric_window_values", lambda *args: [100, 2])

    increase = inspection_service._metric_counter_increase_window(
        _instance("mysql"), "aborted_connects_total", 2, 10
    )

    assert increase == 2
