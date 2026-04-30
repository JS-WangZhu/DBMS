from app.extensions import db
from app.models.base import TimestampMixin


class HAConfig(db.Model, TimestampMixin):
    __tablename__ = "ha_configs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, unique=True)
    script_path = db.Column(db.String(512), nullable=False)
    command_template = db.Column(db.Text, nullable=True)
    description = db.Column(db.String(255), nullable=True)
    enabled = db.Column(db.Boolean, nullable=False, default=True)
    is_default = db.Column(db.Boolean, nullable=False, default=False)
    notify_target_ids = db.Column(db.JSON, nullable=True)

    def get_notify_target_ids(self):
        target_ids = []
        for item in self.notify_target_ids or []:
            try:
                target_ids.append(int(item))
            except (TypeError, ValueError):
                continue
        return target_ids

    def to_dict(self):
        from app.models.notify_target import BackupNotifyTarget

        target_ids = self.get_notify_target_ids()
        notify_targets = []
        if target_ids:
            rows = BackupNotifyTarget.query.filter(BackupNotifyTarget.id.in_(target_ids)).all()
            row_map = {row.id: row for row in rows}
            notify_targets = [
                {
                    "id": row_map[target_id].id,
                    "name": row_map[target_id].name,
                    "channel": row_map[target_id].channel,
                    "address": row_map[target_id].address,
                    "enabled": row_map[target_id].enabled,
                }
                for target_id in target_ids
                if target_id in row_map
            ]
        return {
            "id": self.id,
            "name": self.name,
            "script_path": self.script_path,
            "command_template": self.command_template,
            "description": self.description,
            "enabled": self.enabled,
            "is_default": self.is_default,
            "notify_target_ids": target_ids,
            "notify_targets": notify_targets,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
