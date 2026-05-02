from sqlalchemy import inspect, text

from app.extensions import db
from app.models.data_query_op import DataQueryOperationConfig
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


# 数据查询允许操作预置数据
DATA_QUERY_OPERATIONS_SEED = [
    # MySQL
    {"db_type": "mysql", "op_key": "SELECT", "label": "查询数据", "sort_order": 1},
    # MongoDB
    {"db_type": "mongodb", "op_key": "find", "label": "文档查询", "sort_order": 1},
    {"db_type": "mongodb", "op_key": "find_one", "label": "查询单条文档", "sort_order": 2},
    {"db_type": "mongodb", "op_key": "aggregate", "label": "聚合管道", "sort_order": 3},
    {"db_type": "mongodb", "op_key": "count_documents", "label": "文档计数", "sort_order": 4},
    {"db_type": "mongodb", "op_key": "run_command", "label": "执行只读命令", "sort_order": 5},
    {"db_type": "mongodb", "op_key": "buildinfo", "label": "构建信息", "sort_order": 10},
    {"db_type": "mongodb", "op_key": "collstats", "label": "集合统计", "sort_order": 11},
    {"db_type": "mongodb", "op_key": "count", "label": "计数", "sort_order": 12},
    {"db_type": "mongodb", "op_key": "dbstats", "label": "数据库统计", "sort_order": 13},
    {"db_type": "mongodb", "op_key": "distinct", "label": "唯一值", "sort_order": 14},
    {"db_type": "mongodb", "op_key": "listcollections", "label": "列出集合", "sort_order": 15},
    {"db_type": "mongodb", "op_key": "listdatabases", "label": "列出数据库", "sort_order": 16},
    {"db_type": "mongodb", "op_key": "ping", "label": "连通性检测", "sort_order": 17},
    {"db_type": "mongodb", "op_key": "replsetgetstatus", "label": "副本集状态", "sort_order": 18},
    {"db_type": "mongodb", "op_key": "serverstatus", "label": "服务器状态", "sort_order": 19},
    # Redis
    {"db_type": "redis", "op_key": "GET", "label": "获取字符串", "sort_order": 1},
    {"db_type": "redis", "op_key": "MGET", "label": "批量获取字符串", "sort_order": 2},
    {"db_type": "redis", "op_key": "HGET", "label": "获取哈希字段", "sort_order": 3},
    {"db_type": "redis", "op_key": "HGETALL", "label": "获取完整哈希", "sort_order": 4},
    {"db_type": "redis", "op_key": "HEXISTS", "label": "哈希字段存在性", "sort_order": 5},
    {"db_type": "redis", "op_key": "EXISTS", "label": "键存在性", "sort_order": 6},
    {"db_type": "redis", "op_key": "SCARD", "label": "集合元素数", "sort_order": 7},
    {"db_type": "redis", "op_key": "SMEMBERS", "label": "集合所有元素", "sort_order": 8},
    {"db_type": "redis", "op_key": "LRANGE", "label": "列表范围", "sort_order": 9},
    {"db_type": "redis", "op_key": "ZRANGE", "label": "有序集范围", "sort_order": 10},
    {"db_type": "redis", "op_key": "ZRANGEBYSCORE", "label": "有序集按分值范围", "sort_order": 11},
]


def seed_data_query_operations():
    """首次启动写入预置的数据查询允许操作；已存在的不覆盖。"""
    try:
        existing_keys = {
            (row.db_type, row.op_key.lower())
            for row in DataQueryOperationConfig.query.all()
        }
    except Exception:
        db.session.rollback()
        return

    added = 0
    for item in DATA_QUERY_OPERATIONS_SEED:
        key = (item["db_type"], item["op_key"].lower())
        if key in existing_keys:
            continue
        row = DataQueryOperationConfig(
            db_type=item["db_type"],
            op_key=item["op_key"],
            label=item.get("label") or "",
            enabled=True,
            is_builtin=True,
            sort_order=int(item.get("sort_order") or 0),
        )
        db.session.add(row)
        added += 1
    if added:
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
