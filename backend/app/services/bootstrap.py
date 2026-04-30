from sqlalchemy import inspect, text

from app.extensions import db
from app.models.user import User


def ensure_admin_user(username: str, password: str):
    existing = User.query.filter_by(username=username).first()
    if existing:
        return existing

    user = User(username=username, role="admin", status="active", auth_source="local")
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def ensure_backup_extra_columns():
    engine = db.engine
    inspector = inspect(engine)

    table_columns = {}
    for table in [
        "db_clusters",
        "backup_policies",
        "backup_logs",
        "backup_notify_targets",
        "ha_configs",
        "monitor_snapshots",
        "audit_logs",
        "user_menu_permissions",
        "user_cluster_permissions",
        "api_keys",
    ]:
        try:
            table_columns[table] = {col["name"] for col in inspector.get_columns(table)}
        except Exception:
            table_columns[table] = set()

    statements = []
    if table_columns["db_clusters"] and "namespace" not in table_columns["db_clusters"]:
        statements.append("ALTER TABLE db_clusters ADD COLUMN namespace VARCHAR(64) NOT NULL DEFAULT 'default'")
    if table_columns["db_clusters"] and "business_line" not in table_columns["db_clusters"]:
        statements.append("ALTER TABLE db_clusters ADD COLUMN business_line VARCHAR(64) NULL")
    if table_columns["db_clusters"] and "environment" not in table_columns["db_clusters"]:
        statements.append("ALTER TABLE db_clusters ADD COLUMN environment VARCHAR(64) NULL")
    if table_columns["db_clusters"] and "namespace" in table_columns["db_clusters"]:
        statements.append("ALTER TABLE db_clusters MODIFY COLUMN namespace VARCHAR(64) NULL")
    if table_columns["db_clusters"] and "ha_domain" not in table_columns["db_clusters"]:
        statements.append("ALTER TABLE db_clusters ADD COLUMN ha_domain VARCHAR(255) NULL")
    if table_columns["db_clusters"] and "ha_status_json" not in table_columns["db_clusters"]:
        statements.append("ALTER TABLE db_clusters ADD COLUMN ha_status_json JSON NULL")
    if table_columns["db_clusters"] and "ha_switch_enabled" not in table_columns["db_clusters"]:
        statements.append("ALTER TABLE db_clusters ADD COLUMN ha_switch_enabled BOOLEAN NOT NULL DEFAULT FALSE")

    if "extra_json" not in table_columns["backup_policies"]:
        statements.append("ALTER TABLE backup_policies ADD COLUMN extra_json JSON NULL")

    if "extra_json" not in table_columns["backup_logs"]:
        statements.append("ALTER TABLE backup_logs ADD COLUMN extra_json JSON NULL")

    # Legacy schema compatibility: old backup_logs table lacks updated_at.
    if "updated_at" not in table_columns["backup_logs"]:
        statements.append(
            "ALTER TABLE backup_logs ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
        )

    # Notification target compatibility for old schemas.
    if table_columns["backup_notify_targets"]:
        if "extra_json" not in table_columns["backup_notify_targets"]:
            statements.append("ALTER TABLE backup_notify_targets ADD COLUMN extra_json JSON NULL")
        if "created_at" not in table_columns["backup_notify_targets"]:
            statements.append(
                "ALTER TABLE backup_notify_targets ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP"
            )
        if "updated_at" not in table_columns["backup_notify_targets"]:
            statements.append(
                "ALTER TABLE backup_notify_targets ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
            )

    if table_columns["ha_configs"] and "notify_target_ids" not in table_columns["ha_configs"]:
        statements.append("ALTER TABLE ha_configs ADD COLUMN notify_target_ids JSON NULL")
    if table_columns["ha_configs"] and "command_template" not in table_columns["ha_configs"]:
        statements.append("ALTER TABLE ha_configs ADD COLUMN command_template TEXT NULL")

    # Monitor and audit models use TimestampMixin.
    if "created_at" not in table_columns["monitor_snapshots"]:
        statements.append("ALTER TABLE monitor_snapshots ADD COLUMN created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP")
    if "updated_at" not in table_columns["monitor_snapshots"]:
        statements.append(
            "ALTER TABLE monitor_snapshots ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
        )

    if "updated_at" not in table_columns["audit_logs"]:
        statements.append(
            "ALTER TABLE audit_logs ADD COLUMN updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
        )

    for sql in statements:
        try:
            db.session.execute(text(sql))
            db.session.commit()
        except Exception:
            db.session.rollback()

    # Ensure audit FK keeps history on user deletion.
    try:
        row = db.session.execute(
            text(
                """
                SELECT DELETE_RULE
                FROM information_schema.REFERENTIAL_CONSTRAINTS
                WHERE CONSTRAINT_SCHEMA = DATABASE()
                  AND TABLE_NAME = 'audit_logs'
                  AND CONSTRAINT_NAME = 'fk_audit_user'
                """
            )
        ).fetchone()
        if row and str(row[0]).upper() != "SET NULL":
            db.session.execute(text("ALTER TABLE audit_logs DROP FOREIGN KEY fk_audit_user"))
            db.session.execute(
                text(
                    "ALTER TABLE audit_logs "
                    "ADD CONSTRAINT fk_audit_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL"
                )
            )
            db.session.commit()
    except Exception:
        db.session.rollback()
