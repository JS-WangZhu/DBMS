from datetime import datetime, timedelta

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
    db.session.add_all([normal_cluster, empty_cluster])
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
    db.session.add_all([first_node, second_node])
    db.session.flush()

    first_policy = _policy("node-1-backup", first_node.id)
    second_policy = _policy("node-2-backup", second_node.id)
    db.session.add_all([first_policy, second_policy])
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
    assert rows["mysql-prod"]["backup_status"] == "normal"
    assert rows["mysql-prod"]["successful_backup_count"] == 1
    assert rows["mysql-prod"]["latest_backup"]["status"] == "failed"
    assert rows["mysql-prod"]["latest_backup"]["instance_name"] == "mysql-02"
    assert rows["redis-cache"]["backup_status"] == "abnormal"
    assert rows["redis-cache"]["latest_backup"] is None
