from app.models.ai_config import AIModelConfig
from app.models.audit_log import AuditLog
from app.models.backup import BackupLog, BackupPolicy
from app.models.backup_agent import BackupAgent
from app.models.backup_tool_config import BackupToolConfig
from app.models.backup_key import BackupKey
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.models.ha_config import HAConfig
from app.models.inspection import InspectionAlert, InspectionConfig
from app.models.monitor_snapshot import (
    MonitorSnapshotDoris,
    MonitorSnapshotMongoDB,
    MonitorSnapshotMySQL,
    MonitorSnapshotRedis,
)
from app.models.notify_target import BackupNotifyTarget
from app.models.s3_storage_config import S3StorageConfig
from app.models.user import User
from app.models.user_permission import (
    ApiKey,
    RoleGroup,
    RoleGroupClusterPermission,
    RoleGroupMenuPermission,
    UserClusterPermission,
    UserMenuPermission,
    UserRoleGroup,
)

__all__ = [
    "AIModelConfig",
    "AuditLog",
    "BackupLog",
    "BackupPolicy",
    "BackupAgent",
    "BackupToolConfig",
    "BackupKey",
    "BackupNotifyTarget",
    "DatabaseCluster",
    "DatabaseInstance",
    "HAConfig",
    "InspectionConfig",
    "InspectionAlert",
    "MonitorSnapshotMySQL",
    "MonitorSnapshotMongoDB",
    "MonitorSnapshotRedis",
    "MonitorSnapshotDoris",
    "S3StorageConfig",
    "User",
    "UserMenuPermission",
    "UserClusterPermission",
    "ApiKey",
    "RoleGroup",
    "RoleGroupMenuPermission",
    "RoleGroupClusterPermission",
    "UserRoleGroup",
]
