from app.extensions import db
from app.models.base import TimestampMixin


class MonitorSnapshotBase(db.Model, TimestampMixin):
    __abstract__ = True

    id = db.Column(db.Integer, primary_key=True)

    instance_id = db.Column(db.Integer, nullable=False, index=True)
    metric_type = db.Column(db.String(64), nullable=False, index=True)
    payload_json = db.Column(db.JSON, nullable=False)
    collected_at = db.Column(db.DateTime, nullable=False, server_default=db.func.now(), index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "instance_id": self.instance_id,
            "metric_type": self.metric_type,
            "payload_json": self.payload_json,
            "collected_at": self.collected_at.isoformat() if self.collected_at else None,
        }


class MonitorSnapshotMySQL(MonitorSnapshotBase):
    __tablename__ = "monitor_snapshots_mysql"


class MonitorSnapshotMongoDB(MonitorSnapshotBase):
    __tablename__ = "monitor_snapshots_mongodb"


class MonitorSnapshotRedis(MonitorSnapshotBase):
    __tablename__ = "monitor_snapshots_redis"


class MonitorSnapshotPostgreSQL(MonitorSnapshotBase):
    __tablename__ = "monitor_snapshots_postgresql"


class MonitorSnapshotDoris(MonitorSnapshotBase):
    __tablename__ = "monitor_snapshots_doris"


SNAPSHOT_MODEL_BY_DB_TYPE = {
    "mysql": MonitorSnapshotMySQL,
    "mongodb": MonitorSnapshotMongoDB,
    "redis": MonitorSnapshotRedis,
    "postgresql": MonitorSnapshotPostgreSQL,
    "doris": MonitorSnapshotDoris,
}


def snapshot_model_for_db(db_type: str):
    return SNAPSHOT_MODEL_BY_DB_TYPE.get(db_type)


def snapshot_model_for_instance(instance):
    db_type = getattr(instance, "db_type", None)
    return snapshot_model_for_db(db_type)
