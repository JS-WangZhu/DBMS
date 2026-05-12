from app.extensions import db
from app.models.instance_status_config import InstanceStatusConfig


DEFAULT_METRIC_REFRESH_TIMEOUT_SECONDS = 8
DEFAULT_PROBE_POLL_INTERVAL_SECONDS = 30
MIN_METRIC_REFRESH_TIMEOUT_SECONDS = 1
MIN_PROBE_POLL_INTERVAL_SECONDS = 10


def get_or_create_instance_status_config():
    cfg = InstanceStatusConfig.query.first()
    if cfg:
        return cfg
    cfg = InstanceStatusConfig(
        metric_refresh_timeout_seconds=DEFAULT_METRIC_REFRESH_TIMEOUT_SECONDS,
        probe_poll_interval_seconds=DEFAULT_PROBE_POLL_INTERVAL_SECONDS,
    )
    db.session.add(cfg)
    db.session.commit()
    return cfg


def update_instance_status_config(cfg: InstanceStatusConfig, payload: dict):
    if "metric_refresh_timeout_seconds" in payload:
        try:
            cfg.metric_refresh_timeout_seconds = max(
                MIN_METRIC_REFRESH_TIMEOUT_SECONDS,
                int(payload.get("metric_refresh_timeout_seconds")),
            )
        except (TypeError, ValueError):
            return "metric_refresh_timeout_seconds must be integer >= 1"
    if "probe_poll_interval_seconds" in payload:
        try:
            cfg.probe_poll_interval_seconds = max(
                MIN_PROBE_POLL_INTERVAL_SECONDS,
                int(payload.get("probe_poll_interval_seconds")),
            )
        except (TypeError, ValueError):
            return "probe_poll_interval_seconds must be integer >= 10"
    return None
