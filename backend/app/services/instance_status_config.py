from app.extensions import db
from app.models.instance_status_config import InstanceStatusConfig
from app.services.redis_cache import get_json, set_json


DEFAULT_METRIC_REFRESH_TIMEOUT_SECONDS = 8
DEFAULT_PROBE_POLL_INTERVAL_SECONDS = 30
MIN_METRIC_REFRESH_TIMEOUT_SECONDS = 1
MIN_PROBE_POLL_INTERVAL_SECONDS = 10
CONFIG_CACHE_KEY = "dbms:config:instance_status"


def get_or_create_instance_status_config():
    cached = get_json(CONFIG_CACHE_KEY)
    cfg = InstanceStatusConfig.query.first()
    if cfg:
        if not isinstance(cached, dict):
            set_json(CONFIG_CACHE_KEY, cfg.to_dict())
        return cfg
    cfg = InstanceStatusConfig(
        metric_refresh_timeout_seconds=DEFAULT_METRIC_REFRESH_TIMEOUT_SECONDS,
        probe_poll_interval_seconds=DEFAULT_PROBE_POLL_INTERVAL_SECONDS,
    )
    db.session.add(cfg)
    db.session.commit()
    set_json(CONFIG_CACHE_KEY, cfg.to_dict())
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


def refresh_instance_status_config_cache(cfg: InstanceStatusConfig):
    set_json(CONFIG_CACHE_KEY, cfg.to_dict())
