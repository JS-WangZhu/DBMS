import { createRouter, createWebHistory } from "vue-router";

import MainLayout from "../layouts/MainLayout.vue";
import AIAnalysisView from "../views/AIAnalysisView.vue";
import AIModelConfigView from "../views/AIModelConfigView.vue";
import BackupAgentView from "../views/BackupAgentView.vue";
import BackupKeyManageView from "../views/BackupKeyManageView.vue";
import BackupMongoPolicyView from "../views/BackupMongoPolicyView.vue";
import BackupMysqlPolicyView from "../views/BackupMysqlPolicyView.vue";
import BackupNotifyTargetsView from "../views/BackupNotifyTargetsView.vue";
import BackupOverviewView from "../views/BackupOverviewView.vue";
import BackupRecordsView from "../views/BackupRecordsView.vue";
import BackupToolConfigView from "../views/BackupToolConfigView.vue";
import ClusterManageView from "../views/ClusterManageView.vue";
import DashboardView from "../views/DashboardView.vue";
import DataChangeView from "../views/DataChangeView.vue";
import DataAccessHistoryView from "../views/DataAccessHistoryView.vue";
import DataQueryOpConfigView from "../views/DataQueryOpConfigView.vue";
import HAConfigView from "../views/HAConfigView.vue";
import DataQueryView from "../views/DataQueryView.vue";
import InstanceManageView from "../views/InstanceManageView.vue";
import InstanceStatusConfigView from "../views/InstanceStatusConfigView.vue";
import InspectionManageView from "../views/InspectionManageView.vue";
import InspectionParamConfigView from "../views/InspectionParamConfigView.vue";
import LoginView from "../views/LoginView.vue";
import McpPlatformView from "../views/McpPlatformView.vue";
import MysqlConnectionManageView from "../views/MysqlConnectionManageView.vue";
import MongoConnectionManageView from "../views/MongoConnectionManageView.vue";
import RedisConnectionManageView from "../views/RedisConnectionManageView.vue";
import S3StorageConfigView from "../views/S3StorageConfigView.vue";
import SsoCallbackView from "../views/SsoCallbackView.vue";
import SsoConfigView from "../views/SsoConfigView.vue";
import UserRoleGroupView from "../views/UserRoleGroupView.vue";
import UserPermissionView from "../views/UserPermissionView.vue";
import UsersView from "../views/UsersView.vue";

const routes = [
  {
    path: "/login",
    component: LoginView,
    meta: { public: true },
  },
  {
    path: "/sso/callback",
    component: SsoCallbackView,
    meta: { public: true },
  },
  {
    path: "/",
    component: MainLayout,
    children: [
      { path: "", redirect: "/dashboard" },
      { path: "/dashboard", component: DashboardView, meta: { title: "总览" } },

      { path: "/databases/mysql", redirect: "/databases/mysql/instances" },
      { path: "/databases/mysql/clusters", component: ClusterManageView, meta: { title: "MySQL 集群管理", dbType: "mysql", dbLabel: "MySQL" } },
      { path: "/databases/mysql/instances", component: InstanceManageView, meta: { title: "MySQL 实例管理", dbType: "mysql", dbLabel: "MySQL" } },
      { path: "/databases/mysql/connections", component: MysqlConnectionManageView, meta: { title: "MySQL 连接管理", dbType: "mysql", dbLabel: "MySQL" } },

      { path: "/databases/mongodb", redirect: "/databases/mongodb/instances" },
      { path: "/databases/mongodb/clusters", component: ClusterManageView, meta: { title: "MongoDB 集群管理", dbType: "mongodb", dbLabel: "MongoDB" } },
      { path: "/databases/mongodb/instances", component: InstanceManageView, meta: { title: "MongoDB 实例管理", dbType: "mongodb", dbLabel: "MongoDB" } },
      { path: "/databases/mongodb/connections", component: MongoConnectionManageView, meta: { title: "MongoDB 连接管理", dbType: "mongodb", dbLabel: "MongoDB" } },

      { path: "/databases/redis", redirect: "/databases/redis/instances" },
      { path: "/databases/redis/clusters", component: ClusterManageView, meta: { title: "Redis 集群管理", dbType: "redis", dbLabel: "Redis" } },
      { path: "/databases/redis/instances", component: InstanceManageView, meta: { title: "Redis 实例管理", dbType: "redis", dbLabel: "Redis" } },
      { path: "/databases/redis/connections", component: RedisConnectionManageView, meta: { title: "Redis 连接管理", dbType: "redis", dbLabel: "Redis" } },

      { path: "/databases/doris", redirect: "/databases/doris/instances" },
      { path: "/databases/doris/clusters", component: ClusterManageView, meta: { title: "Doris 集群管理", dbType: "doris", dbLabel: "Doris" } },
      { path: "/databases/doris/instances", component: InstanceManageView, meta: { title: "Doris 实例管理", dbType: "doris", dbLabel: "Doris" } },
      { path: "/service/inspection", component: InspectionManageView, meta: { title: "巡检管理" } },

      { path: "/backups/mysql-policies", component: BackupMysqlPolicyView, meta: { title: "MySQL策略" } },
            { path: "/backups/overview", component: BackupOverviewView, meta: { title: "备份总览" } },
      { path: "/backups/mongo-policies", component: BackupMongoPolicyView, meta: { title: "MongoDB策略" } },
      { path: "/backups/records", component: BackupRecordsView, meta: { title: "备份记录" } },
      { path: "/backups/agents", component: BackupAgentView, meta: { title: "备份Agent管理" } },
      { path: "/backups/notify-targets", component: BackupNotifyTargetsView, meta: { title: "通知地址管理" } },
      { path: "/backups/s3-storage", component: S3StorageConfigView, meta: { title: "存储配置管理" } },
      { path: "/backups/tool-configs", component: BackupToolConfigView, meta: { title: "备份工具管理" } },
      { path: "/backups/keys", component: BackupKeyManageView, meta: { title: "备份密钥管理" } },
      { path: "/data-access/query", component: DataQueryView, meta: { title: "数据查询" } },
      { path: "/data-access/change", component: DataChangeView, meta: { title: "数据变更" } },
      { path: "/data-access/ai-analysis", component: AIAnalysisView, meta: { title: "智能分析" } },
      { path: "/data-access/history", component: DataAccessHistoryView, meta: { title: "历史记录" } },
      { path: "/users/info", component: UsersView, meta: { title: "用户信息" } },
      { path: "/users/role-groups", component: UserRoleGroupView, meta: { title: "角色组管理" } },
      { path: "/users/permissions", component: UserPermissionView, meta: { title: "用户权限管理" } },
      { path: "/config/ai-models", component: AIModelConfigView, meta: { title: "AI模型管理" } },
      { path: "/config/ha", component: HAConfigView, meta: { title: "高可用配置管理" } },
      { path: "/config/instance-status", component: InstanceStatusConfigView, meta: { title: "实例状态检测管理" } },
      { path: "/config/inspection", component: InspectionParamConfigView, meta: { title: "巡检参数管理" } },
      { path: "/config/data-query-ops", component: DataQueryOpConfigView, meta: { title: "数据查询操作配置" } },
      { path: "/config/mcp-platform", component: McpPlatformView, meta: { title: "MCP开放平台" } },
      { path: "/config/sso", component: SsoConfigView, meta: { title: "SSO登录管理" } },
    ],
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to, _, next) => {
  if (to.meta.public) {
    next();
    return;
  }
  const token = localStorage.getItem("dbms_token");
  if (!token) {
    next("/login");
    return;
  }
  next();
});

export default router;
