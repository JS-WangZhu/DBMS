from app.services.collectors import node_exporter


def _metrics(reads, read_seconds, writes, write_seconds):
    labels = {"device": "sdb"}
    return {
        "node_disk_reads_completed_total": [(labels, reads)],
        "node_disk_read_time_seconds_total": [(labels, read_seconds)],
        "node_disk_writes_completed_total": [(labels, writes)],
        "node_disk_write_time_seconds_total": [(labels, write_seconds)],
    }


def test_disk_io_latency_uses_average_over_the_previous_ten_minutes(monkeypatch):
    node_exporter.DISK_IO_SNAPSHOT_CACHE.clear()
    monotonic = iter((1000, 1300, 1600))
    monkeypatch.setattr(node_exporter.time, "monotonic", lambda: next(monotonic))

    assert node_exporter._disk_io_latency_ms(_metrics(100, 2, 50, 1), "host-a", "/dev/sdb") is None
    # The intermediate 100ms result must not be used as the final value.
    assert node_exporter._disk_io_latency_ms(_metrics(110, 3, 60, 2), "host-a", "/dev/sdb") is None
    result = node_exporter._disk_io_latency_ms(_metrics(130, 3.6, 70, 2.4), "host-a", "/dev/sdb")

    assert result == {"device": "sdb", "latency_ms": 60.0}


def test_disk_io_latency_ignores_counter_reset(monkeypatch):
    node_exporter.DISK_IO_SNAPSHOT_CACHE.clear()
    monotonic = iter((1000, 1600))
    monkeypatch.setattr(node_exporter.time, "monotonic", lambda: next(monotonic))
    node_exporter._disk_io_latency_ms(_metrics(100, 2, 50, 1), "host-b", "/dev/sdb")

    assert node_exporter._disk_io_latency_ms(_metrics(1, 0.1, 1, 0.1), "host-b", "/dev/sdb") is None
