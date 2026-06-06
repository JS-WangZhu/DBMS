from app.models.ai_config import AIModelConfig
from app.models.aliyun_dns import AliyunDomainConfig
from app.models.audit_log import AuditLog
from app.models.backup import BackupLog, BackupPolicy
from app.models.backup_agent import BackupAgent
from app.models.backup_tool_config import BackupToolConfig
from app.models.backup_key import BackupKey
from app.models.data_query_op import DataQueryOperationConfig
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.models.ha_config import HAConfig
from app.models.inspection import InspectionAlert, InspectionConfig
from app.models.instance_status_config import InstanceStatusConfig
from app.models.monitor_snapshot import (
    MonitorSnapshotDoris,
    MonitorSnapshotMongoDB,
    MonitorSnapshotMySQL,
    MonitorSnapshotRedis,
)
from app.models.notify_target import BackupNotifyTarget
from app.models.s3_storage_config import S3StorageConfig
from app.models.sso_config import SsoConfig
from app.models.task_management import ScheduledTask, ScheduledTaskRun
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
    "AliyunDomainConfig",
    "AuditLog",
    "BackupLog",
    "BackupPolicy",
    "BackupAgent",
    "BackupToolConfig",
    "BackupKey",
    "BackupNotifyTarget",
    "DataQueryOperationConfig",
    "DatabaseCluster",
    "DatabaseInstance",
    "HAConfig",
    "InspectionConfig",
    "InspectionAlert",
    "InstanceStatusConfig",
    "MonitorSnapshotMySQL",
    "MonitorSnapshotMongoDB",
    "MonitorSnapshotRedis",
    "MonitorSnapshotDoris",
    "S3StorageConfig",
    "SsoConfig",
    "ScheduledTask",
    "ScheduledTaskRun",
    "User",
    "UserMenuPermission",
    "UserClusterPermission",
    "ApiKey",
    "RoleGroup",
    "RoleGroupMenuPermission",
    "RoleGroupClusterPermission",
    "UserRoleGroup",
]
