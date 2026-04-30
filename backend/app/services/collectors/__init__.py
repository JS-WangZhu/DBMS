from app.services.collectors.doris import collect_doris_status
from app.services.collectors.mongodb import collect_mongodb_status
from app.services.collectors.mysql import collect_mysql_status
from app.services.collectors.redisdb import collect_redis_status


COLLECTOR_MAP = {
    "mysql": collect_mysql_status,
    "doris": collect_doris_status,
    "mongodb": collect_mongodb_status,
    "redis": collect_redis_status,
}


def collect_instance_metrics(instance, password):
    collector = COLLECTOR_MAP.get(instance.db_type)
    if not collector:
        return {"ok": False, "error": f"collector not found for {instance.db_type}"}
    return collector(instance=instance, password=password)
