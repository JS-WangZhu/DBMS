from app.extensions import db
from app.models.base import TimestampMixin


class DataQueryOperationConfig(db.Model, TimestampMixin):
    """数据查询允许操作白名单配置（MySQL/MongoDB/Redis）。"""

    __tablename__ = "data_query_operation_configs"
    __table_args__ = (
        db.UniqueConstraint("db_type", "op_key", name="uq_data_query_op_type_key"),
    )

    id = db.Column(db.Integer, primary_key=True)
    db_type = db.Column(db.String(16), nullable=False, index=True)  # mysql / mongodb / redis
    op_key = db.Column(db.String(64), nullable=False)               # 关键字/命令名，如 SELECT / find / GET
    label = db.Column(db.String(128), nullable=True)                # 中文描述
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    is_builtin = db.Column(db.Boolean, nullable=False, default=False)
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    def to_dict(self):
        return {
            "id": self.id,
            "db_type": self.db_type,
            "op_key": self.op_key,
            "label": self.label or "",
            "enabled": bool(self.enabled),
            "is_builtin": bool(self.is_builtin),
            "sort_order": int(self.sort_order or 0),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
