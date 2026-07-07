from app.services.collectors import node_exporter


def _metrics(reads, read_seconds, writes, write_seconds):
    labels = {"device": "sdb"}
    return {
        "node_disk_reads_completed_total": [(labels, reads)],
        "node_disk_read_time_seconds_total": [(labels, read_seconds)],
        "node_disk_writes_completed_total": [(labels, writes)],
        "node_disk_write_time_seconds_total": [(labels, write_seconds)],
    }


def test_disk_io_latency_uses_counter_deltas_in_milliseconds():
    node_exporter.DISK_IO_SNAPSHOT_CACHE.clear()

    assert node_exporter._disk_io_latency_ms(_metrics(100, 2, 50, 1), "host-a", "/dev/sdb") is None
    result = node_exporter._disk_io_latency_ms(_metrics(110, 2.4, 60, 1.2), "host-a", "/dev/sdb")

    assert result == {"device": "sdb", "latency_ms": 30.0}
    assert node_exporter._disk_io_latency_ms(
        _metrics(110, 2.4, 60, 1.2), "host-a", "/dev/sdb",
    ) == result


def test_disk_io_latency_ignores_counter_reset():
    node_exporter.DISK_IO_SNAPSHOT_CACHE.clear()
    node_exporter._disk_io_latency_ms(_metrics(100, 2, 50, 1), "host-b", "/dev/sdb")

    assert node_exporter._disk_io_latency_ms(_metrics(1, 0.1, 1, 0.1), "host-b", "/dev/sdb") is None
