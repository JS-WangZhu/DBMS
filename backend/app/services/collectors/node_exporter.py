import math
import re
import time
from urllib.error import URLError
from urllib.request import Request, urlopen


LINE_RE = re.compile(
    r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?|[+-]Inf|NaN)\s*$"
)
LABEL_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:\\.|[^"\\])*)"')

IGNORED_FS_TYPES = {
    "autofs",
    "binfmt_misc",
    "cgroup",
    "cgroup2",
    "configfs",
    "debugfs",
    "devpts",
    "devtmpfs",
    "fusectl",
    "hugetlbfs",
    "mqueue",
    "nsfs",
    "overlay",
    "proc",
    "pstore",
    "ramfs",
    "securityfs",
    "selinuxfs",
    "squashfs",
    "sysfs",
    "tmpfs",
    "tracefs",
}
IGNORED_MOUNT_PREFIXES = ("/proc", "/sys", "/dev", "/run")
CPU_SNAPSHOT_CACHE = {}
NET_SNAPSHOT_CACHE = {}
DISK_IO_SNAPSHOT_CACHE = {}


def _clamp_pct(value):
    if value is None:
        return None
    return round(max(0.0, min(float(value), 100.0)), 2)


def _to_float(raw):
    try:
        val = float(raw)
        if math.isnan(val):
            return None
        return val
    except (TypeError, ValueError):
        return None


def _parse_labels(raw_blob):
    if not raw_blob:
        return {}

    labels = {}
    content = raw_blob[1:-1]
    for match in LABEL_RE.finditer(content):
        key = match.group(1)
        value = match.group(2).replace('\\"', '"').replace("\\\\", "\\")
        labels[key] = value
    return labels


def _parse_text_exposition(text):
    result = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = LINE_RE.match(stripped)
        if not match:
            continue
        name, labels_raw, value_raw = match.groups()
        labels = _parse_labels(labels_raw)
        value = _to_float(value_raw)
        if value is None:
            continue
        result.setdefault(name, []).append((labels, value))
    return result


def _metric_single(metrics, metric_name):
    rows = metrics.get(metric_name, [])
    if not rows:
        return None
    return rows[0][1]


def _normalize_endpoint(address):
    raw = str(address or "").strip()
    if not raw:
        return ""

    if raw.startswith("http://") or raw.startswith("https://"):
        if raw.endswith("/metrics"):
            return raw
        return raw.rstrip("/") + "/metrics"

    if raw.endswith("/metrics"):
        return f"http://{raw}"
    return f"http://{raw.rstrip('/')}/metrics"


def _node_exporter_config(instance):
    extra_json = instance.extra_json or {}
    node_exporter = extra_json.get("node_exporter") if isinstance(extra_json, dict) else {}
    cfg = node_exporter if isinstance(node_exporter, dict) else {}

    enabled = cfg.get("enabled", True)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() in {"1", "true", "yes", "on"}
    else:
        enabled = bool(enabled)

    mode = str(cfg.get("mode") or "same_host").strip().lower()
    if mode not in {"same_host", "custom"}:
        mode = "same_host"

    if mode == "custom":
        endpoint = _normalize_endpoint(cfg.get("address") or "")
    else:
        host = (instance.resolved_ip or instance.host_input or "").strip()
        port = cfg.get("port", 9100)
        try:
            port = int(port)
        except (TypeError, ValueError):
            port = 9100
        endpoint = f"http://{host}:{port}/metrics" if host else ""

    return {
        "enabled": enabled,
        "mode": mode,
        "endpoint": endpoint,
    }


def _cpu_usage_pct(metrics, cache_key):
    rows = metrics.get("node_cpu_seconds_total", [])
    if not rows:
        return None

    total = 0.0
    idle = 0.0
    for labels, value in rows:
        total += value
        if labels.get("mode") == "idle":
            idle += value

    if total <= 0:
        return None

    now = time.time()
    prev = CPU_SNAPSHOT_CACHE.get(cache_key)
    CPU_SNAPSHOT_CACHE[cache_key] = {"ts": now, "total": total, "idle": idle}
    if not prev:
        return _clamp_pct((1 - (idle / total)) * 100)

    delta_total = total - prev["total"]
    delta_idle = idle - prev["idle"]
    if delta_total > 0 and delta_idle >= 0:
        return _clamp_pct((1 - (delta_idle / delta_total)) * 100)

    return _clamp_pct((1 - (idle / total)) * 100)


def _memory_usage_pct(metrics):
    total = _metric_single(metrics, "node_memory_MemTotal_bytes")
    available = _metric_single(metrics, "node_memory_MemAvailable_bytes")
    if total is None or available is None or total <= 0:
        return None
    used = max(0.0, total - available)
    return _clamp_pct((used / total) * 100)


def _cpu_core_count(metrics):
    rows = metrics.get("node_cpu_seconds_total", [])
    if not rows:
        return None
    cores = set()
    for labels, _value in rows:
        cpu = labels.get("cpu")
        if cpu is not None:
            cores.add(cpu)
    return len(cores) if cores else None


def _filesystem_entries(metrics):
    size_rows = metrics.get("node_filesystem_size_bytes", [])
    if not size_rows:
        return []

    avail_map = {}
    for labels, value in metrics.get("node_filesystem_avail_bytes", []):
        key = (labels.get("device"), labels.get("mountpoint"), labels.get("fstype"))
        avail_map[key] = value

    files_map = {}
    for labels, value in metrics.get("node_filesystem_files", []):
        key = (labels.get("device"), labels.get("mountpoint"), labels.get("fstype"))
        files_map[key] = value

    files_free_map = {}
    for labels, value in metrics.get("node_filesystem_files_free", []):
        key = (labels.get("device"), labels.get("mountpoint"), labels.get("fstype"))
        files_free_map[key] = value

    entries = []
    for labels, size in size_rows:
        if size is None or size <= 0:
            continue
        mount = labels.get("mountpoint") or ""
        fstype = labels.get("fstype") or ""
        device = labels.get("device") or ""
        if not mount or not device:
            continue
        if fstype in IGNORED_FS_TYPES:
            continue
        if mount.startswith(IGNORED_MOUNT_PREFIXES):
            continue

        key = (device, mount, fstype)
        avail = avail_map.get(key)
        used = max(0.0, size - avail) if avail is not None else None
        usage_pct = _clamp_pct((used / size) * 100) if used is not None and size > 0 else None
        inode_total = files_map.get(key)
        inode_free = files_free_map.get(key)
        inode_used = max(0.0, inode_total - inode_free) if inode_total is not None and inode_free is not None else None
        inode_pct = (
            _clamp_pct((inode_used / inode_total) * 100)
            if inode_used is not None and inode_total not in (None, 0)
            else None
        )
        entries.append(
            {
                "device": device,
                "mountpoint": mount,
                "fstype": fstype,
                "size_bytes": int(size),
                "avail_bytes": int(avail) if avail is not None else None,
                "used_bytes": int(used) if used is not None else None,
                "usage_pct": usage_pct,
                "inode_total": int(inode_total) if inode_total is not None else None,
                "inode_free": int(inode_free) if inode_free is not None else None,
                "inode_used": int(inode_used) if inode_used is not None else None,
                "inode_usage_pct": inode_pct,
            }
        )

    return entries


def _data_disk_usage(entries):
    best = None
    for entry in entries:
        size = entry.get("size_bytes")
        if size is None:
            continue
        if best is None or size > best.get("size_bytes", 0):
            best = entry
    return best


def _network_rates(metrics, cache_key):
    rx_rows = metrics.get("node_network_receive_bytes_total", [])
    tx_rows = metrics.get("node_network_transmit_bytes_total", [])
    if not rx_rows and not tx_rows:
        return []

    now = time.time()
    rx_map = {}
    for labels, value in rx_rows:
        device = labels.get("device")
        if not device or device == "lo":
            continue
        rx_map[device] = value

    tx_map = {}
    for labels, value in tx_rows:
        device = labels.get("device")
        if not device or device == "lo":
            continue
        tx_map[device] = value

    prev = NET_SNAPSHOT_CACHE.get(cache_key)
    NET_SNAPSHOT_CACHE[cache_key] = {"ts": now, "rx": rx_map, "tx": tx_map}
    if not prev:
        return []

    dt = now - prev.get("ts", now)
    if dt <= 0:
        return []

    rates = []
    devices = set(rx_map.keys()) | set(tx_map.keys())
    for device in devices:
        rx_now = rx_map.get(device)
        tx_now = tx_map.get(device)
        rx_prev = prev.get("rx", {}).get(device)
        tx_prev = prev.get("tx", {}).get(device)
        rx_bps = (rx_now - rx_prev) / dt if rx_now is not None and rx_prev is not None else None
        tx_bps = (tx_now - tx_prev) / dt if tx_now is not None and tx_prev is not None else None
        rates.append(
            {
                "device": device,
                "rx_bps": round(rx_bps, 2) if rx_bps is not None and rx_bps >= 0 else None,
                "tx_bps": round(tx_bps, 2) if tx_bps is not None and tx_bps >= 0 else None,
            }
        )

    return sorted(rates, key=lambda item: item.get("device") or "")


def _disk_metric_map(metrics, metric_name):
    return {
        labels.get("device"): value
        for labels, value in metrics.get(metric_name, [])
        if labels.get("device") and value is not None
    }


def _disk_io_latency_ms(metrics, cache_key, target_device=None):
    reads = _disk_metric_map(metrics, "node_disk_reads_completed_total")
    read_seconds = _disk_metric_map(metrics, "node_disk_read_time_seconds_total")
    writes = _disk_metric_map(metrics, "node_disk_writes_completed_total")
    write_seconds = _disk_metric_map(metrics, "node_disk_write_time_seconds_total")
    devices = set(reads) | set(read_seconds) | set(writes) | set(write_seconds)
    current = {
        device: {
            "operations": reads.get(device, 0.0) + writes.get(device, 0.0),
            "seconds": read_seconds.get(device, 0.0) + write_seconds.get(device, 0.0),
        }
        for device in devices
        if not str(device).startswith(("loop", "ram", "fd", "sr"))
    }
    snapshot = DISK_IO_SNAPSHOT_CACHE.get(cache_key) or {}
    previous = snapshot.get("counters")
    last_result = snapshot.get("result")
    if not previous:
        DISK_IO_SNAPSHOT_CACHE[cache_key] = {"counters": current, "result": None}
        return None
    if current == previous:
        return last_result

    candidates = []
    for device, counters in current.items():
        old = previous.get(device)
        if not old:
            continue
        operation_delta = counters["operations"] - old["operations"]
        seconds_delta = counters["seconds"] - old["seconds"]
        if operation_delta <= 0 or seconds_delta < 0:
            continue
        candidates.append({
            "device": device,
            "latency_ms": round(seconds_delta * 1000 / operation_delta, 2),
        })
    if not candidates:
        DISK_IO_SNAPSHOT_CACHE[cache_key] = {"counters": current, "result": None}
        return None

    target = str(target_device or "").strip().rsplit("/", 1)[-1]
    if target:
        matched = next((item for item in candidates if item["device"] == target), None)
        if matched:
            DISK_IO_SNAPSHOT_CACHE[cache_key] = {"counters": current, "result": matched}
            return matched
    result = max(candidates, key=lambda item: item["latency_ms"])
    DISK_IO_SNAPSHOT_CACHE[cache_key] = {"counters": current, "result": result}
    return result


def collect_node_exporter_metrics(instance):
    cfg = _node_exporter_config(instance)
    base = {
        "node_exporter_enabled": cfg["enabled"],
        "node_exporter_mode": cfg["mode"],
        "node_exporter_endpoint": cfg["endpoint"],
        "node_exporter_status": "disabled" if not cfg["enabled"] else "unknown",
        "node_exporter_error": None,
        "host_cpu_usage_pct": None,
        "host_cpu_cores": None,
        "host_memory_usage_pct": None,
        "host_memory_total_bytes": None,
        "host_data_disk_usage_pct": None,
        "host_data_disk_mountpoint": None,
        "host_data_disk_device": None,
        "host_data_disk_size_bytes": None,
        "host_disk_io_latency_ms": None,
        "host_disk_io_device": None,
        "host_disk_entries": [],
        "host_net_rates": [],
    }

    if not cfg["enabled"]:
        return base
    if not cfg["endpoint"]:
        base["node_exporter_status"] = "error"
        base["node_exporter_error"] = "node_exporter endpoint is empty"
        return base

    try:
        req = Request(cfg["endpoint"], headers={"User-Agent": "dbms-platform/1.0"})
        with urlopen(req, timeout=3) as resp:
            text = resp.read().decode("utf-8", errors="replace")
    except URLError as exc:
        base["node_exporter_status"] = "error"
        base["node_exporter_error"] = f"node_exporter request failed: {exc}"
        return base
    except Exception as exc:
        base["node_exporter_status"] = "error"
        base["node_exporter_error"] = f"node_exporter collect failed: {exc}"
        return base

    metrics = _parse_text_exposition(text)
    base["node_exporter_status"] = "ok"
    base["host_cpu_cores"] = _cpu_core_count(metrics)
    base["host_cpu_usage_pct"] = _cpu_usage_pct(metrics, cache_key=cfg["endpoint"])
    base["host_memory_usage_pct"] = _memory_usage_pct(metrics)
    base["host_memory_total_bytes"] = _metric_single(metrics, "node_memory_MemTotal_bytes")

    disk_entries = _filesystem_entries(metrics)
    base["host_disk_entries"] = disk_entries
    disk = _data_disk_usage(disk_entries)
    if disk:
        base["host_data_disk_usage_pct"] = disk.get("usage_pct")
        base["host_data_disk_mountpoint"] = disk.get("mountpoint")
        base["host_data_disk_device"] = disk.get("device")
        base["host_data_disk_size_bytes"] = disk.get("size_bytes")

    io_latency = _disk_io_latency_ms(metrics, cache_key=cfg["endpoint"], target_device=base["host_data_disk_device"])
    if io_latency:
        base["host_disk_io_latency_ms"] = io_latency["latency_ms"]
        base["host_disk_io_device"] = io_latency["device"]

    base["host_net_rates"] = _network_rates(metrics, cache_key=cfg["endpoint"])

    return base
