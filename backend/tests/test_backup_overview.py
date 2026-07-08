from datetime import datetime, timedelta

from app.api.routes import backups
from app.api.routes.backups import backup_overview
from app.extensions import db
from app.models.backup import BackupLog, BackupPolicy
from app.models.db_asset import DatabaseCluster, DatabaseInstance


def _policy(name, instance_id):
    return BackupPolicy(
        name=name,
        target_type="instance",
        target_id=instance_id,
        db_type="mysql",
        backup_type="full",
        tool_name="xtrabackup",
        cron_expr="0 2 * * *",
        storage_path="/backup",
    )


def test_backup_overview_is_aggregated_by_cluster(app):
    normal_cluster = DatabaseCluster(name="mysql-prod", db_type="mysql")
    empty_cluster = DatabaseCluster(name="redis-cache", db_type="redis")
    hidden_cluster = DatabaseCluster(name="mongo-hidden", db_type="mongodb")
    db.session.add_all([normal_cluster, empty_cluster, hidden_cluster])
    db.session.flush()

    first_node = DatabaseInstance(
        name="mysql-01",
        db_type="mysql",
        host_input="10.0.0.1",
        port=3306,
        cluster_id=normal_cluster.id,
    )
    second_node = DatabaseInstance(
        name="mysql-02",
        db_type="mysql",
        host_input="10.0.0.2",
        port=3306,
        cluster_id=normal_cluster.id,
    )
    hidden_node = DatabaseInstance(
        name="mongo-01",
        db_type="mongodb",
        host_input="10.0.0.3",
        port=27017,
        cluster_id=hidden_cluster.id,
    )
    db.session.add_all([first_node, second_node, hidden_node])
    db.session.flush()

    first_policy = _policy("node-1-backup", first_node.id)
    second_policy = _policy("node-2-backup", second_node.id)
    hidden_policy = BackupPolicy(
        name="mongo-backup",
        target_type="instance",
        target_id=hidden_node.id,
        db_type="mongodb",
        backup_type="full",
        tool_name="mongodump",
        cron_expr="0 2 * * *",
        storage_path="/backup",
    )
    db.session.add_all([first_policy, second_policy, hidden_policy])
    db.session.flush()

    now = datetime.utcnow()
    db.session.add_all(
        [
            BackupLog(
                policy_id=first_policy.id,
                started_at=now - timedelta(hours=3),
                finished_at=now - timedelta(hours=2, minutes=50),
                status="success",
            ),
            BackupLog(
                policy_id=second_policy.id,
                started_at=now - timedelta(hours=1),
                finished_at=now - timedelta(minutes=50),
                status="failed",
                error_message="disk full",
            ),
            BackupLog(
                policy_id=hidden_policy.id,
                started_at=now - timedelta(minutes=30),
                finished_at=now - timedelta(minutes=20),
                status="success",
            ),
        ]
    )
    db.session.commit()

    with app.test_request_context("/api/v1/backups/overview?hours=24"):
        response, status_code = backup_overview.__wrapped__()

    assert status_code == 200
    overview = response.get_json()["data"]
    assert overview["total_clusters"] == 2
    assert overview["normal_backup_sets"] == 1
    assert overview["abnormal_backup_sets"] == 1
    assert overview["normal_ratio"] == 50.0

    rows = {item["cluster_name"]: item for item in overview["items"]}
    assert set(rows) == {"mysql-prod", "redis-cache"}
    assert rows["mysql-prod"]["backup_status"] == "normal"
    assert rows["mysql-prod"]["successful_backup_count"] == 1
    assert rows["mysql-prod"]["latest_backup"]["status"] == "failed"
    assert rows["mysql-prod"]["latest_backup"]["instance_name"] == "mysql-02"
    assert rows["redis-cache"]["backup_status"] == "abnormal"
    assert rows["redis-cache"]["latest_backup"] is None


def test_backup_overview_syncs_running_remote_backups_before_query(app, monkeypatch):
    calls = []

    def sync_running_backups():
        calls.append(True)

    monkeypatch.setattr(backups, "sync_running_remote_backups", sync_running_backups)

    with app.test_request_context("/api/v1/backups/overview?hours=24"):
        response, status_code = backup_overview.__wrapped__()

    assert status_code == 200
    assert response.get_json()["data"]["total_clusters"] == 0
    assert calls == [True]
