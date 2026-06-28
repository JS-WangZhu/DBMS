from datetime import datetime
from types import SimpleNamespace

from app.services import monitor_snapshot_service
from app.services import redis_cache


def test_latest_snapshot_cache_uses_ten_minute_ttl_for_failures(monkeypatch):
    calls = []

    def fake_set_json(key, value, ex=None):
        calls.append((key, value, ex))
        return True

    monkeypatch.setattr(redis_cache, "set_json", fake_set_json)
    redis_cache.set_latest_snapshot(
        db_type="mongodb",
        instance_id=7,
        metric_type="status",
        payload_json={"ok": False, "ping_ok": False, "error": "timeout"},
        collected_at=datetime(2026, 1, 2, 3, 4, 5),
        running_status="error",
    )

    assert len(calls) == 2
    assert all(item[2] == 600 for item in calls)
    assert any("latest_snapshot:mongodb:status:7" in item[0] for item in calls)
    assert any("instance_status:7" in item[0] for item in calls)
    assert not any("last_success_snapshot" in item[0] for item in calls)


def test_successful_collection_refreshes_latest_and_last_success_ttl(monkeypatch):
    calls = []
    monkeypatch.setattr(redis_cache, "set_json", lambda key, value, ex=None: calls.append((key, value, ex)) or True)

    redis_cache.set_latest_snapshot(
        db_type="mysql",
        instance_id=9,
        metric_type="status",
        payload_json={"ok": True, "ping_ok": True},
        running_status="running",
    )

    assert len(calls) == 3
    assert all(item[2] == 600 for item in calls)
    assert any("last_success_snapshot:mysql:status:9" in item[0] for item in calls)


def test_latest_snapshot_reads_cache_without_database(monkeypatch):
    cached = SimpleNamespace(instance_id=3, payload_json={"ok": False}, collected_at=datetime.now())
    monkeypatch.setattr(monitor_snapshot_service, "get_latest_snapshot", lambda **_kwargs: cached)
    monkeypatch.setattr(
        monitor_snapshot_service,
        "snapshot_model_for_db",
        lambda _db_type: (_ for _ in ()).throw(AssertionError("database should not be queried")),
    )

    result = monitor_snapshot_service.latest_snapshot_for_instance(3, "mongodb")
    assert result is cached


def test_last_success_reads_cache_without_database(monkeypatch):
    cached = SimpleNamespace(instance_id=3, payload_json={"ok": True}, collected_at=datetime.now())
    monkeypatch.setattr(monitor_snapshot_service, "get_last_success_snapshot", lambda **_kwargs: cached)
    monkeypatch.setattr(
        monitor_snapshot_service,
        "snapshot_model_for_db",
        lambda _db_type: (_ for _ in ()).throw(AssertionError("database should not be queried")),
    )

    result = monitor_snapshot_service.latest_success_snapshot_for_instance(3, "mongodb")
    assert result is cached
