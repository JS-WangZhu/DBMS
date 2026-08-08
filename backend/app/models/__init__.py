from app.models.ai_config import AIModelConfig
from app.models.aliyun_dns import AliyunDomainConfig
from app.models.audit_log import AuditLog
from app.models.auth_session import AuthSession
from app.models.backup import BackupLog, BackupPolicy
from app.models.backup_agent import AgentInspectionStatus, BackupAgent
from app.models.backup_tool_config import BackupToolConfig
from app.models.backup_key import BackupKey
from app.models.data_query_op import DataQueryOperationConfig
from app.models.db_asset import DatabaseCluster, DatabaseInstance
from app.models.ha_config import HAConfig
from app.models.inspection import InspectionAlert, InspectionConfig
from app.models.instance_status_config import InstanceStatusConfig
from app.models.jumpserver_config import JumpServerConfig
from app.models.physical_discovery import (
    PhysicalDiscoveryConfig,
    PhysicalDiscoveryDetail,
    PhysicalDiscoveryRun,
    VCenterConfig,
)
from app.models.monitor_snapshot import (
    MonitorSnapshotDoris,
    MonitorSnapshotMongoDB,
    MonitorSnapshotMySQL,
    MonitorSnapshotPostgreSQL,
    MonitorSnapshotRedis,
)
from app.models.notify_target import BackupNotifyTarget
from app.models.s3_storage_config import S3StorageConfig
from app.models.sso_config import SsoConfig
from app.models.sql_release import SqlRelease, SqlReleaseRollbackBackup
from app.models.task_management import ScheduledTask, ScheduledTaskRun
from app.models.user import User
from app.models.user_permission import (
    ApiKey,
    DataSourceGroup,
    DataSourceGroupClusterPermission,
    RoleGroup,
    RoleGroupClusterPermission,
    RoleGroupMenuPermission,
    UserClusterPermission,
    UserMenuPermission,
    UserRoleGroup,
    UserDataSourceGroup,
)

__all__ = [
    "AIModelConfig",
    "AliyunDomainConfig",
    "AuditLog",
    "AuthSession",
    "BackupLog",
    "BackupPolicy",
    "BackupAgent",
    "AgentInspectionStatus",
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
    "JumpServerConfig",
    "PhysicalDiscoveryConfig",
    "PhysicalDiscoveryDetail",
    "PhysicalDiscoveryRun",
    "VCenterConfig",
    "MonitorSnapshotMySQL",
    "MonitorSnapshotMongoDB",
    "MonitorSnapshotRedis",
    "MonitorSnapshotPostgreSQL",
    "MonitorSnapshotDoris",
    "S3StorageConfig",
    "SsoConfig",
    "SqlRelease",
    "SqlReleaseRollbackBackup",
    "ScheduledTask",
    "ScheduledTaskRun",
    "User",
    "UserMenuPermission",
    "UserClusterPermission",
    "ApiKey",
    "DataSourceGroup",
    "DataSourceGroupClusterPermission",
    "RoleGroup",
    "RoleGroupMenuPermission",
    "RoleGroupClusterPermission",
    "UserRoleGroup",
    "UserDataSourceGroup",
]
