<template>
  <el-container class="layout-shell">
    <el-aside :width="sidebarCollapsed ? '72px' : '248px'" class="sidebar" :class="{ 'is-collapsed': sidebarCollapsed }">
      <div class="logo">
        <div class="logo-mark">D</div>
        <div class="logo-copy">
          <strong>DBMS 数据库管理平台</strong>
        </div>
      </div>
      <el-menu
        :default-active="route.path"
        :collapse="sidebarCollapsed"
        :collapse-transition="true"
        @select="onMenuSelect"
      >
        <el-menu-item v-if="hasMenu('dashboard')" index="/dashboard">
          <el-icon><Odometer /></el-icon>
          <span>总览</span>
        </el-menu-item>

        <el-sub-menu v-if="hasAnyMenu(['database_apply','database_recycle','application_history'])" index="resource-management">
          <template #title>
            <el-icon><Briefcase /></el-icon>
            <span>资源管理</span>
          </template>
          <el-menu-item v-if="hasMenu('database_apply')" index="/resources/database-apply">
            <el-icon><CirclePlus /></el-icon><span>数据库申请</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('database_recycle')" index="/resources/database-recycle">
            <el-icon><Delete /></el-icon><span>数据库回收</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('application_history')" index="/resources/application-history">
            <el-icon><Document /></el-icon><span>申请流水</span>
          </el-menu-item>
        </el-sub-menu>

        <el-sub-menu v-if="hasAnyMenu(['mysql_instances','mysql_instance_detail','mysql_clusters','mysql_connections','mysql_session_probe','mongodb_instances','mongodb_instance_detail','mongodb_clusters','mongodb_connections','mongodb_session_probe','redis_instances','redis_clusters','redis_connections','postgresql_instances','postgresql_clusters','doris_instances','doris_clusters'])" index="service-manage">
          <template #title>
            <el-icon><Menu /></el-icon>
            <span>服务管理</span>
          </template>

          <el-sub-menu v-if="hasAnyMenu(['mysql_instances','mysql_instance_detail','mysql_clusters','mysql_connections','mysql_session_probe'])" index="db-mysql">
            <template #title>
              <el-icon class="db-brand-icon"><MysqlIcon /></el-icon>
              <span>MySQL</span>
            </template>
            <el-menu-item v-if="hasMenu('mysql_instances')" index="/databases/mysql/instances">
              <el-icon class="db-brand-icon"><MysqlIcon /></el-icon>
              <span>实例管理</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('mysql_instance_detail')" index="/databases/mysql/instance-detail">
              <el-icon><TrendCharts /></el-icon>
              <span>实例详情</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('mysql_clusters')" index="/databases/mysql/clusters">
              <el-icon><Share /></el-icon>
              <span>集群管理</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('mysql_connections')" index="/databases/mysql/connections">
              <el-icon><Connection /></el-icon>
              <span>连接管理</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('mysql_session_probe')" index="/databases/mysql/session-probe">
              <el-icon><View /></el-icon>
              <span>会话探测</span>
            </el-menu-item>
          </el-sub-menu>

          <el-sub-menu v-if="hasAnyMenu(['mongodb_instances','mongodb_instance_detail','mongodb_clusters','mongodb_connections','mongodb_session_probe'])" index="db-mongodb">
            <template #title>
              <el-icon class="db-brand-icon"><MongoIcon /></el-icon>
              <span>MongoDB</span>
            </template>
            <el-menu-item v-if="hasMenu('mongodb_instances')" index="/databases/mongodb/instances">
              <el-icon class="db-brand-icon"><MongoIcon /></el-icon>
              <span>实例管理</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('mongodb_instance_detail')" index="/databases/mongodb/instance-detail">
              <el-icon><TrendCharts /></el-icon>
              <span>实例详情</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('mongodb_clusters')" index="/databases/mongodb/clusters">
              <el-icon><FolderOpened /></el-icon>
              <span>集群管理</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('mongodb_connections')" index="/databases/mongodb/connections">
              <el-icon><Link /></el-icon>
              <span>连接管理</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('mongodb_session_probe')" index="/databases/mongodb/session-probe">
              <el-icon><View /></el-icon><span>会话探测</span>
            </el-menu-item>
          </el-sub-menu>

          <el-sub-menu v-if="hasAnyMenu(['redis_instances','redis_clusters','redis_connections'])" index="db-redis">
            <template #title>
              <el-icon class="db-brand-icon"><RedisIcon /></el-icon>
              <span>Redis</span>
            </template>
            <el-menu-item v-if="hasMenu('redis_instances')" index="/databases/redis/instances">
              <el-icon class="db-brand-icon"><RedisIcon /></el-icon>
              <span>实例管理</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('redis_clusters')" index="/databases/redis/clusters">
              <el-icon><Coin /></el-icon>
              <span>集群管理</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('redis_connections')" index="/databases/redis/connections">
              <el-icon><Promotion /></el-icon>
              <span>连接管理</span>
            </el-menu-item>
          </el-sub-menu>

          <el-sub-menu v-if="hasAnyMenu(['postgresql_instances','postgresql_clusters'])" index="db-postgresql">
            <template #title>
              <el-icon class="db-brand-icon"><PostgreSQLIcon /></el-icon>
              <span>PostgreSQL</span>
            </template>
            <el-menu-item v-if="hasMenu('postgresql_instances')" index="/databases/postgresql/instances">
              <el-icon class="db-brand-icon"><PostgreSQLIcon /></el-icon>
              <span>&#23454;&#20363;&#31649;&#29702;</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('postgresql_clusters')" index="/databases/postgresql/clusters">
              <el-icon><Coin /></el-icon>
              <span>&#38598;&#32676;&#31649;&#29702;</span>
            </el-menu-item>
          </el-sub-menu>

          <el-sub-menu v-if="hasAnyMenu(['doris_instances','doris_clusters'])" index="db-doris">
            <template #title>
              <el-icon class="db-brand-icon"><DorisIcon /></el-icon>
              <span>Doris</span>
            </template>
            <el-menu-item v-if="hasMenu('doris_instances')" index="/databases/doris/instances">
              <el-icon class="db-brand-icon"><DorisIcon /></el-icon>
              <span>实例管理</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('doris_clusters')" index="/databases/doris/clusters">
              <el-icon><Histogram /></el-icon>
              <span>集群管理</span>
            </el-menu-item>
          </el-sub-menu>
        </el-sub-menu>
        <el-sub-menu v-if="hasAnyMenu(['inspection_manage','inspection_param_config'])" index="inspection-manage">
          <template #title>
            <el-icon><CircleCheck /></el-icon>
            <span>巡检管理</span>
          </template>
          <el-menu-item v-if="hasMenu('inspection_manage')" index="/service/inspection">
            <el-icon><CircleCheck /></el-icon>
            <span>巡检状态</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('inspection_param_config')" index="/config/inspection">
            <el-icon><Setting /></el-icon>
            <span>巡检参数</span>
          </el-menu-item>
        </el-sub-menu>
        <el-sub-menu v-if="hasAnyMenu(['data_query','data_change','data_history','data_permission_apply'])" index="data-access">
          <template #title>
            <el-icon><View /></el-icon>
            <span>数据访问</span>
          </template>
          <el-menu-item v-if="hasMenu('data_query')" index="/data-access/query">
            <el-icon><Search /></el-icon>
            <span>数据查询</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('data_change')" index="/data-access/change">
            <el-icon><EditPen /></el-icon>
            <span>数据变更</span>
          </el-menu-item>
          <!-- <el-menu-item v-if="hasMenu('ai_analysis')" index="/data-access/ai-analysis">
            <el-icon><Cpu /></el-icon>
            <span>智能分析</span>
          </el-menu-item> -->
          <el-menu-item v-if="hasMenu('data_history')" index="/data-access/history">
            <el-icon><Clock /></el-icon>
            <span>历史记录</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('data_permission_apply')" index="/data-access/permission-apply">
            <el-icon><Key /></el-icon>
            <span>权限申请</span>
          </el-menu-item>
        </el-sub-menu>

        <el-sub-menu v-if="hasAnyMenu(['sql_release_apply','sql_release_history'])" index="data-release">
          <template #title>
            <el-icon><Promotion /></el-icon>
            <span>数据发布</span>
          </template>
          <el-menu-item v-if="hasMenu('sql_release_apply')" index="/data-release/apply">
            <el-icon><EditPen /></el-icon>
            <span>SQL上线</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('sql_release_history')" index="/data-release/history">
            <el-icon><Clock /></el-icon>
            <span>工单历史</span>
          </el-menu-item>
        </el-sub-menu>

        <el-sub-menu v-if="hasAnyMenu(['data_copy_tasks','data_copy_config'])" index="data-copy">
          <template #title>
            <el-icon><Connection /></el-icon>
            <span>数据复制</span>
          </template>
          <el-menu-item v-if="hasMenu('data_copy_tasks')" index="/data-copy/tasks">
            <el-icon><Operation /></el-icon>
            <span>任务管理</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('data_copy_config')" index="/data-copy/config">
            <el-icon><Setting /></el-icon>
            <span>配置中心</span>
          </el-menu-item>
        </el-sub-menu>

        <el-sub-menu v-if="hasAnyMenu(['task_schedule','task_results'])" index="task-management">
          <template #title>
            <el-icon><Calendar /></el-icon>
            <span>任务管理</span>
          </template>
          <el-menu-item v-if="hasMenu('task_schedule')" index="/tasks/schedules">
            <el-icon><Operation /></el-icon>
            <span>调度管理</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('task_results')" index="/tasks/results">
            <el-icon><Tickets /></el-icon>
            <span>结果查询</span>
          </el-menu-item>
        </el-sub-menu>

        <el-sub-menu v-if="hasAnyMenu(['aliyun_dns_tool'])" index="quick-tools">
          <template #title>
            <el-icon><Aim /></el-icon>
            <span>快捷工具</span>
          </template>
          <el-menu-item v-if="hasMenu('aliyun_dns_tool')" index="/tools/aliyun-dns">
            <el-icon><Position /></el-icon>
            <span>阿里云域名工具</span>
          </el-menu-item>
        </el-sub-menu>

        <el-sub-menu v-if="hasAnyMenu(['backup_mysql_policies','backup_postgresql_policies','backup_mongo_policies','backup_records','backup_tool_configs','backup_s3_storage','backup_keys','backup_overview'])" index="backup">
          <template #title>
            <el-icon><Collection /></el-icon>
            <span>备份管理</span>
          </template>
          <el-menu-item v-if="hasMenu('backup_overview')" index="/backups/overview">
            <el-icon><Notebook /></el-icon>
            <span>备份总览</span>
          </el-menu-item>
          <el-sub-menu v-if="hasAnyMenu(['backup_mysql_policies','backup_postgresql_policies','backup_mongo_policies'])" index="backup-policies">
            <template #title>
              <el-icon><PieChart /></el-icon>
              <span>策略管理</span>
            </template>
            <el-menu-item v-if="hasMenu('backup_mysql_policies')" index="/backups/mysql-policies">
              <el-icon class="db-brand-icon"><MysqlIcon /></el-icon>
              <span>MySQL策略</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('backup_postgresql_policies')" index="/backups/postgresql-policies">
              <el-icon class="db-brand-icon"><PostgreSQLIcon /></el-icon>
              <span>PostgreSQL策略</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('backup_mongo_policies')" index="/backups/mongo-policies">
              <el-icon class="db-brand-icon"><MongoIcon /></el-icon>
              <span>MongoDB策略</span>
            </el-menu-item>
          </el-sub-menu>
          <el-menu-item v-if="hasMenu('backup_records')" index="/backups/records">
            <el-icon><Files /></el-icon>
            <span>备份记录</span>
          </el-menu-item>
          <el-sub-menu v-if="hasAnyMenu(['backup_tool_configs','backup_s3_storage','backup_keys'])" index="backup-config">
            <template #title>
              <el-icon><SwitchButton /></el-icon>
              <span>备份配置</span>
            </template>
            <el-menu-item v-if="hasMenu('backup_tool_configs')" index="/backups/tool-configs">
              <el-icon><Tools /></el-icon>
              <span>备份工具管理</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('backup_s3_storage')" index="/backups/s3-storage">
              <el-icon><Box /></el-icon>
              <span>存储配置管理</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('backup_keys')" index="/backups/keys">
              <el-icon><Key /></el-icon>
              <span>备份密钥管理</span>
            </el-menu-item>
          </el-sub-menu>
        </el-sub-menu>

        <el-sub-menu v-if="hasAnyMenu(['users_info','users_permissions','users_role_groups','users_data_sources'])" index="users">
          <template #title>
            <el-icon><User /></el-icon>
            <span>用户管理</span>
          </template>
          <el-menu-item v-if="hasMenu('users_info')" index="/users/info">
            <el-icon><UserFilled /></el-icon>
            <span>用户信息管理</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('users_role_groups')" index="/users/role-groups">
            <el-icon><Avatar /></el-icon>
            <span>角色组管理</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('users_permissions')" index="/users/permissions">
            <el-icon><Lock /></el-icon>
            <span>用户权限管理</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('users_data_sources')" index="/users/data-sources">
            <el-icon><Connection /></el-icon>
            <span>数据源权限管理</span>
          </el-menu-item>
        </el-sub-menu>

        <el-sub-menu v-if="hasAnyMenu(['ai_model_config', 'ha_config', 'instance_status_config', 'physical_discovery_manage', 'data_query_op_config', 'backup_notify_targets', 'backup_agents', 'domain_config', 'mcp_platform', 'sso_config', 'jumpserver_config'])" index="config">
          <template #title>
            <el-icon><Management /></el-icon>
            <span>配置管理</span>
          </template>
          <el-menu-item v-if="hasMenu('backup_agents')" index="/config/agents">
            <el-icon><Monitor /></el-icon>
            <span>Agent管理</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('ai_model_config')" index="/config/ai-models">
            <el-icon><TrendCharts /></el-icon>
            <span>AI模型管理</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('ha_config')" index="/config/ha">
            <el-icon><Lightning /></el-icon>
            <span>高可用配置管理</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('instance_status_config')" index="/config/instance-status">
            <el-icon><Timer /></el-icon>
            <span>实例状态检测管理</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('physical_discovery_manage')" index="/config/physical-discovery">
            <el-icon><Monitor /></el-icon>
            <span>物理机探测管理</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('data_query_op_config')" index="/config/data-query-ops">
            <el-icon><DataAnalysis /></el-icon>
            <span>数据查询操作配置</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('backup_notify_targets')" index="/backups/notify-targets">
            <el-icon><Bell /></el-icon>
            <span>通知地址管理</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('domain_config')" index="/config/domain">
            <el-icon><Location /></el-icon>
            <span>域名配置管理</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('mcp_platform')" index="/config/mcp-platform">
            <el-icon><SetUp /></el-icon>
            <span>MCP开放平台</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('sso_config')" index="/config/sso">
            <el-icon><Key /></el-icon>
            <span>SSO登录管理</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('jumpserver_config')" index="/config/jumpserver">
            <el-icon><Monitor /></el-icon>
            <span>JumpServer管理</span>
          </el-menu-item>
        </el-sub-menu>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="topbar">
        <div class="topbar-leading">
          <el-button class="sidebar-toggle" text circle :aria-label="sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'" @click="sidebarCollapsed = !sidebarCollapsed">
            <el-icon><Expand v-if="sidebarCollapsed" /><Fold v-else /></el-icon>
          </el-button>
          <div class="page-identity">
            <div class="title">{{ currentPageTitle }}</div>
            <div class="subtitle">DBMS 数据库管理平台</div>
          </div>
        </div>
        <el-popover placement="bottom-end" trigger="hover" :show-arrow="false" popper-class="user-action-popover">
          <template #reference>
            <div class="user-block" tabindex="0">
              <el-avatar :size="34" :src="displayAvatarUrl || undefined" @error="onAvatarError">
                {{ userInitial }}
              </el-avatar>
              <div class="user-copy">
                <strong>{{ username }}</strong>
                <span>{{ currentRole }}</span>
              </div>
            </div>
          </template>
          <el-button class="logout-button" text @click="logout">退出登录</el-button>
        </el-popover>
      </el-header>
      <el-main class="main-area">
        <div class="tabs-wrap">
          <el-tabs v-model="activeTabId" type="card" @tab-change="onTabChange" @tab-remove="removeTab">
            <el-tab-pane v-for="tab in tabs" :key="tab.id" :name="tab.id" :closable="tabs.length > 1">
              <template #label>
                <span
                  class="tab-label"
                  :title="tab.title"
                  draggable="true"
                  @dragstart="onTabDragStart($event, tab)"
                  @dragover.prevent
                  @drop.prevent="onTabDrop(tab)"
                  @dragend="onTabDragEnd"
                  @contextmenu.prevent="onTabRightClick($event, tab)"
                >
                  <el-icon class="tab-icon" aria-hidden="true">
                    <component :is="tabIcon(tab.path)" />
                  </el-icon>
                  <span class="tab-title">{{ tab.title }}</span>
                </span>
              </template>
            </el-tab-pane>
          </el-tabs>

          <Teleport to="body">
            <div v-if="contextMenu.visible" class="context-menu" :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }" @click.stop>
              <div class="menu-item" @click="closeLeft">关闭左侧</div>
              <div class="menu-item" @click="closeRight">关闭右侧</div>
              <div class="menu-item" @click="closeOthers">关闭其他</div>
              <div class="menu-item" @click="closeAll">关闭全部</div>
            </div>
          </Teleport>
        </div>
        <div class="route-content" :class="{ 'is-entering': contentEntering }">
          <router-view v-slot="{ Component }">
            <keep-alive>
              <component :is="Component" :key="route.path" />
            </keep-alive>
          </router-view>
        </div>
      </el-main>
    </el-container>
    <QuickJump :items="quickJumpMenus" @select="onQuickJumpSelect" />
  </el-container>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import {
  Avatar,
  Aim,
  Bell,
  Box,
  Briefcase,
  Calendar,
  Clock,
  CircleCheck,
  CirclePlus,
  Coin,
  Collection,
  Connection,
  Cpu,
  DataAnalysis,
  Delete,
  Document,
  EditPen,
  Expand,
  Files,
  Fold,
  FolderOpened,
  Histogram,
  Key,
  Lightning,
  Link,
  Lock,
  Management,
  Menu,
  Monitor,
  Notebook,
  Odometer,
  Operation,
  PieChart,
  Promotion,
  Position,
  SetUp,
  Search,
  Share,
  Setting,
  Tickets,
  Location,
  TrendCharts,
  SwitchButton,
  Timer,
  Tools,
  User,
  UserFilled,
  View,
} from "@element-plus/icons-vue";
import MysqlIcon from "../components/icons/MysqlIcon.vue";
import MongoIcon from "../components/icons/MongoIcon.vue";
import RedisIcon from "../components/icons/RedisIcon.vue";
import PostgreSQLIcon from "../components/icons/PostgreSQLIcon.vue";
import DorisIcon from "../components/icons/DorisIcon.vue";
import QuickJump from "../components/QuickJump.vue";
import { listMyUserPermissions } from "../api/modules/backups";
import { logoutCurrentSession, startSessionMonitor } from "../services/authSession";
import { QUICK_JUMP_MENUS } from "../utils/quickJump";

const router = useRouter();
const route = useRoute();

const tabs = ref([]);
const activeTabId = ref("");
const sidebarCollapsed = ref(false);
const avatarLoadFailed = ref(false);
const contentEntering = ref(false);
let tabSeq = 0;
let stopSessionMonitor = null;
let contentAnimationTimer = null;

const contextMenu = ref({
  visible: false,
  x: 0,
  y: 0,
  targetTab: null,
});
const draggingTabId = ref("");

function readStoredUser() {
  try {
    return JSON.parse(localStorage.getItem("dbms_user") || "{}");
  } catch {
    return {};
  }
}

const currentUser = ref(readStoredUser());

const username = computed(() => {
  const user = currentUser.value || {};
  return String(user.display_name || "").trim() || user.username || "unknown";
});

const currentPageTitle = computed(() => route.meta?.title || "总览");

const currentRole = computed(() => {
  const user = currentUser.value || {};
  const roleLabels = { admin: "管理员", api: "API 用户", user: "普通用户" };
  return roleLabels[user.role] || user.role || "当前用户";
});

const userInitial = computed(() => String(username.value || "U").slice(0, 1).toUpperCase());

const avatarUrl = computed(() => {
  try {
    const user = currentUser.value || {};
    const value = String(user.avatar_url || "").trim();
    if (!value) {
      return "";
    }
    const parsed = new URL(value, window.location.origin);
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : "";
  } catch {
    return "";
  }
});

const displayAvatarUrl = computed(() => (avatarLoadFailed.value ? "" : avatarUrl.value));

function onAvatarError() {
  avatarLoadFailed.value = true;
}

const userId = computed(() => {
  return currentUser.value?.id || null;
});

const menuKeys = ref([]);
const permissionsLoaded = ref(false);
const permissionsAvailable = ref(false);
const quickJumpMenus = computed(() => QUICK_JUMP_MENUS.filter((item) => hasMenu(item.permission)));
const routePermissionMap = {
  "/dashboard": "dashboard",
  "/resources/database-apply": "database_apply",
  "/resources/database-recycle": "database_recycle",
  "/resources/application-history": "application_history",
  "/databases/mysql/instances": "mysql_instances",
  "/databases/mysql/instance-detail": "mysql_instance_detail",
  "/databases/mysql/clusters": "mysql_clusters",
  "/databases/mysql/connections": "mysql_connections",
  "/databases/mysql/session-probe": "mysql_session_probe",
  "/databases/mongodb/instances": "mongodb_instances",
  "/databases/mongodb/instance-detail": "mongodb_instance_detail",
  "/databases/mongodb/clusters": "mongodb_clusters",
  "/databases/mongodb/connections": "mongodb_connections",
  "/databases/mongodb/session-probe": "mongodb_session_probe",
  "/databases/redis/instances": "redis_instances",
  "/databases/redis/clusters": "redis_clusters",
  "/databases/redis/connections": "redis_connections",
  "/databases/postgresql/instances": "postgresql_instances",
  "/databases/postgresql/clusters": "postgresql_clusters",
  "/databases/doris/instances": "doris_instances",
  "/databases/doris/clusters": "doris_clusters",
  "/service/inspection": "inspection_manage",
  "/data-access/query": "data_query",
  "/data-access/change": "data_change",
  "/data-access/history": "data_history",
  "/data-access/ai-analysis": "ai_analysis",
  "/data-access/permission-apply": "data_permission_apply",
  "/data-release/apply": "sql_release_apply",
  "/data-release/history": "sql_release_history",
  "/data-copy/tasks": "data_copy_tasks",
  "/data-copy/config": "data_copy_config",
  "/tasks/schedules": "task_schedule",
  "/tasks/results": "task_results",
  "/tools/aliyun-dns": "aliyun_dns_tool",
  "/backups/mysql-policies": "backup_mysql_policies",
  "/backups/postgresql-policies": "backup_postgresql_policies",
  "/backups/mongo-policies": "backup_mongo_policies",
  "/backups/records": "backup_records",
  "/backups/tool-configs": "backup_tool_configs",
  "/config/agents": "backup_agents",
  "/backups/notify-targets": "backup_notify_targets",
  "/backups/s3-storage": "backup_s3_storage",
  "/backups/keys": "backup_keys",
  "/users/info": "users_info",
  "/users/role-groups": "users_role_groups",
  "/users/permissions": "users_permissions",
  "/users/data-sources": "users_data_sources",
  "/config/ai-models": "ai_model_config",
  "/config/ha": "ha_config",
  "/config/instance-status": "instance_status_config",
  "/config/physical-discovery": "physical_discovery_manage",
  "/config/inspection": "inspection_param_config",
  "/config/data-query-ops": "data_query_op_config",
  "/config/domain": "domain_config",
  "/config/mcp-platform": "mcp_platform",
  "/config/sso": "sso_config",
  "/config/jumpserver": "jumpserver_config",
};

function hasMenu(key) {
  if (!permissionsLoaded.value || !permissionsAvailable.value) {
    return false;
  }
  if (currentUser.value?.role === "admin") {
    return true;
  }
  return menuKeys.value.includes(key);
}

function hasAnyMenu(keys) {
  return Array.isArray(keys) && keys.some((key) => hasMenu(key));
}

function routeAllowed(path) {
  const key = routePermissionMap[path];
  if (!key) {
    return true;
  }
  return hasMenu(key);
}

function firstAllowedPath() {
  for (const path of Object.keys(routePermissionMap)) {
    if (routeAllowed(path)) {
      return path;
    }
  }
  return "";
}

function newTabId() {
  tabSeq += 1;
  return `tab_${Date.now()}_${tabSeq}`;
}

function tabTitle(routeLike) {
  return routeLike.meta?.title || routeLike.path || "页面";
}

const tabIconMap = {
  "/dashboard": Odometer,
  "/resources/database-apply": CirclePlus,
  "/resources/database-recycle": Delete,
  "/resources/application-history": Document,
  "/databases/mysql/instances": MysqlIcon,
  "/databases/mysql/instance-detail": TrendCharts,
  "/databases/mysql/clusters": Share,
  "/databases/mysql/connections": Connection,
  "/databases/mysql/session-probe": View,
  "/databases/mongodb/instances": MongoIcon,
  "/databases/mongodb/instance-detail": TrendCharts,
  "/databases/mongodb/clusters": FolderOpened,
  "/databases/mongodb/connections": Link,
  "/databases/mongodb/session-probe": View,
  "/databases/redis/instances": RedisIcon,
  "/databases/redis/clusters": Coin,
  "/databases/redis/connections": Promotion,
  "/databases/postgresql/instances": PostgreSQLIcon,
  "/databases/postgresql/clusters": Coin,
  "/databases/doris/instances": DorisIcon,
  "/databases/doris/clusters": Histogram,
  "/service/inspection": CircleCheck,
  "/data-access/query": Search,
  "/data-access/change": EditPen,
  "/data-access/history": Clock,
  "/data-access/ai-analysis": Cpu,
  "/data-access/permission-apply": Key,
  "/data-release/apply": EditPen,
  "/data-release/history": Clock,
  "/data-copy/tasks": Operation,
  "/data-copy/config": Setting,
  "/tasks/schedules": Operation,
  "/tasks/results": Tickets,
  "/tools/aliyun-dns": Position,
  "/backups/overview": Notebook,
  "/backups/mysql-policies": MysqlIcon,
  "/backups/postgresql-policies": PostgreSQLIcon,
  "/backups/mongo-policies": MongoIcon,
  "/backups/records": Files,
  "/backups/tool-configs": Tools,
  "/backups/notify-targets": Bell,
  "/backups/s3-storage": Box,
  "/backups/keys": Key,
  "/users/info": UserFilled,
  "/users/role-groups": Avatar,
  "/users/permissions": Lock,
  "/users/data-sources": Connection,
  "/config/agents": Monitor,
  "/config/ai-models": TrendCharts,
  "/config/ha": Lightning,
  "/config/instance-status": Timer,
  "/config/physical-discovery": Monitor,
  "/config/inspection": Setting,
  "/config/data-query-ops": DataAnalysis,
  "/config/domain": Location,
  "/config/mcp-platform": SetUp,
  "/config/sso": Key,
  "/config/jumpserver": Monitor,
};

function tabIcon(path) {
  return tabIconMap[path] || Document;
}

function findTabByPath(path) {
  return tabs.value.find((item) => item.path === path);
}

function ensureRouteTab(routeLike) {
  if (!routeLike?.path || routeLike.path === "/login") {
    return;
  }

  const path = routeLike.path;
  const fullPath = routeLike.fullPath || path;
  let existed = findTabByPath(path);
  if (!existed) {
    existed = {
      id: newTabId(),
      path,
      fullPath,
      title: tabTitle(routeLike),
    };
    tabs.value.push(existed);
  } else {
    existed.fullPath = fullPath;
    existed.title = tabTitle(routeLike);
  }
  activeTabId.value = existed.id;
}

function onMenuSelect(index) {
  const path = String(index || "");
  if (!path.startsWith("/")) {
    return;
  }

  const existed = findTabByPath(path);
  if (existed) {
    activeTabId.value = existed.id;
  }
  if (route.path !== path) {
    router.push(path);
  }
}

function onQuickJumpSelect(item) {
  if (item?.path && item.path !== route.path) {
    router.push(item.path);
  }
}

function onTabChange(tabId) {
  const target = tabs.value.find((item) => item.id === tabId);
  if (!target || target.path === route.path) {
    return;
  }
  router.push(target.fullPath || target.path);
}

function removeTab(tabId) {
  const idx = tabs.value.findIndex((item) => item.id === tabId);
  if (idx < 0) {
    return;
  }

  const wasActive = activeTabId.value === tabId;
  tabs.value.splice(idx, 1);

  if (!tabs.value.length) {
    router.push("/dashboard");
    return;
  }

  if (wasActive) {
    const fallback = tabs.value[idx] || tabs.value[idx - 1];
    if (fallback) {
      activeTabId.value = fallback.id;
      router.push(fallback.fullPath || fallback.path);
    }
  }
}

function onTabRightClick(event, tab) {
  contextMenu.value = {
    visible: true,
    x: event.clientX,
    y: event.clientY,
    targetTab: tab,
  };
}

function closeLeft() {
  const targetIdx = tabs.value.findIndex((t) => t.id === contextMenu.value.targetTab.id);
  if (targetIdx > 0) {
    tabs.value.splice(0, targetIdx);
  }
  contextMenu.value.visible = false;
}

function closeRight() {
  const targetIdx = tabs.value.findIndex((t) => t.id === contextMenu.value.targetTab.id);
  if (targetIdx >= 0 && targetIdx < tabs.value.length - 1) {
    tabs.value.splice(targetIdx + 1);
  }
  contextMenu.value.visible = false;
}

function closeOthers() {
  const targetTab = contextMenu.value.targetTab;
  tabs.value = [targetTab];
  activeTabId.value = targetTab.id;
  contextMenu.value.visible = false;
  router.push(targetTab.fullPath || targetTab.path);
}

function closeAll() {
  tabs.value = [];
  activeTabId.value = "";
  contextMenu.value.visible = false;
  router.push("/dashboard");
}

async function loadMenuPermissions() {
  if (!userId.value) {
    menuKeys.value = [];
    permissionsAvailable.value = false;
    permissionsLoaded.value = true;
    return;
  }
  try {
    const { data } = await listMyUserPermissions();
    const payload = data.data || {};
    const serverUser = payload.user || {};
    currentUser.value = { ...(currentUser.value || {}), ...serverUser };
    localStorage.setItem("dbms_user", JSON.stringify(currentUser.value));
    menuKeys.value = payload.menu_keys || [];
    permissionsAvailable.value = true;
  } catch {
    menuKeys.value = [];
    permissionsAvailable.value = false;
  } finally {
    permissionsLoaded.value = true;
    enforceRoutePermission();
  }
}

function enforceRoutePermission() {
  if (!permissionsLoaded.value) {
    return;
  }
  if (permissionsAvailable.value && currentUser.value?.role === "admin") {
    return;
  }
  if (routeAllowed(route.path)) {
    return;
  }
  const nextPath = firstAllowedPath();
  if (nextPath) {
    if (nextPath !== route.path) {
      router.replace(nextPath);
    }
    return;
  }
  tabs.value = [];
  activeTabId.value = "";
  router.replace("/login");
}

function onDocumentClick() {
  contextMenu.value.visible = false;
}

function onTabDragStart(event, tab) {
  draggingTabId.value = tab.id;
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", tab.id);
}

function onTabDrop(targetTab) {
  const sourceId = draggingTabId.value;
  if (!sourceId || sourceId === targetTab.id) {
    return;
  }

  const sourceIndex = tabs.value.findIndex((item) => item.id === sourceId);
  const targetIndex = tabs.value.findIndex((item) => item.id === targetTab.id);
  if (sourceIndex < 0 || targetIndex < 0) {
    return;
  }

  const [sourceTab] = tabs.value.splice(sourceIndex, 1);
  tabs.value.splice(targetIndex, 0, sourceTab);
}

function onTabDragEnd() {
  draggingTabId.value = "";
}

function playContentTransition() {
  contentEntering.value = false;
  if (contentAnimationTimer) {
    window.clearTimeout(contentAnimationTimer);
  }
  nextTick(() => {
    contentEntering.value = true;
    contentAnimationTimer = window.setTimeout(() => {
      contentEntering.value = false;
      contentAnimationTimer = null;
    }, 280);
  });
}

watch(
  () => route.fullPath,
  () => {
    ensureRouteTab(route);
    enforceRoutePermission();
    playContentTransition();
  },
  { immediate: true },
);

onMounted(() => {
  window.addEventListener("click", onDocumentClick);
  stopSessionMonitor = startSessionMonitor();
  loadMenuPermissions();
});

onUnmounted(() => {
  window.removeEventListener("click", onDocumentClick);
  if (stopSessionMonitor) stopSessionMonitor();
  if (contentAnimationTimer) window.clearTimeout(contentAnimationTimer);
});

async function logout() {
  await logoutCurrentSession();
}
</script>

<style scoped>
.layout-shell {
  height: 100vh;
  background: transparent;
}

.sidebar {
  border-right: 1px solid rgba(45, 127, 249, 0.12);
  background: linear-gradient(180deg, #ffffff 0%, #f2f7ff 100%);
  box-shadow: 1px 0 0 rgba(255, 255, 255, 0.6), 2px 0 10px rgba(30, 48, 80, 0.04);
  overflow-x: hidden;
}

:deep(.sidebar .el-menu) {
  border-right: none;
  background: transparent;
}

:deep(.sidebar .el-menu-item),
:deep(.sidebar .el-sub-menu__title) {
  border-left: 3px solid transparent;
  margin: 2px 8px;
  border-radius: 8px;
  transition: all 0.22s ease;
  position: relative;
  overflow: hidden;
}

:deep(.sidebar .el-menu-item:hover),
:deep(.sidebar .el-sub-menu__title:hover) {
  background: linear-gradient(90deg, rgba(45, 127, 249, 0.10), rgba(56, 189, 248, 0.06));
  color: #1e6fff;
}

:deep(.sidebar .el-menu-item:active),
:deep(.sidebar .el-sub-menu__title:active) {
  transform: scale(0.97);
  transition-duration: 0.08s;
}

:deep(.sidebar .el-menu-item.is-active) {
  background: linear-gradient(90deg, rgba(45, 127, 249, 0.18), rgba(56, 189, 248, 0.10));
  color: #1e6fff;
  font-weight: 600;
  border-left-color: #2d7ff9;
  box-shadow: inset 0 0 0 1px rgba(45, 127, 249, 0.08);
}

:deep(.sidebar .el-sub-menu.is-active > .el-sub-menu__title) {
  color: inherit;
  border-left-color: transparent;
  background: transparent;
  font-weight: normal;
}

:deep(.sidebar .el-menu-item .el-icon),
:deep(.sidebar .el-sub-menu__title .el-icon) {
  transition: transform 0.25s ease, color 0.2s ease;
}

:deep(.sidebar .el-menu-item:hover .el-icon),
:deep(.sidebar .el-sub-menu__title:hover .el-icon) {
  transform: scale(1.12) rotate(-4deg);
  color: #2d7ff9;
}

:deep(.sidebar .el-menu-item.is-active .el-icon) {
  color: #2d7ff9;
}

.logo {
  padding: 20px 18px;
  font-weight: 700;
  font-size: 17px;
  letter-spacing: 0.6px;
  background: linear-gradient(135deg, #1e6fff 0%, #38bdf8 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  user-select: none;
}

.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid rgba(45, 127, 249, 0.10);
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: saturate(180%) blur(10px);
  -webkit-backdrop-filter: saturate(180%) blur(10px);
}

.title {
  font-size: 18px;
  font-weight: 700;
  background: linear-gradient(135deg, #1e6fff 0%, #38bdf8 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.user-block {
  display: flex;
  align-items: center;
  gap: 12px;
  color: #5a6b84;
}

.user-block :deep(.el-button) {
  transition: transform 0.15s ease, color 0.2s ease;
}

.user-block :deep(.el-button:hover) {
  transform: translateY(-1px);
}

.user-block :deep(.el-button:active) {
  transform: scale(0.95);
}

.main-area {
  padding: 10px 12px 16px;
  background: transparent;
  min-width: 0;
  width: 100%;
}

.tabs-wrap {
  position: relative;
  padding: 6px 12px 0;
  margin: 0 0 14px;
  border: none;
  border-radius: 0;
  background: #ffffff;
  box-shadow: none;
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
}

.tabs-wrap::after {
  content: none;
}

.main-area > .el-card,
.main-area > div:not(.tabs-wrap) {
  margin-top: 0;
}

:deep(.tabs-wrap .el-tabs__header) {
  margin: 0;
  border-bottom: none;
}

:deep(.tabs-wrap .el-tabs__nav-wrap::after) {
  background-color: transparent;
}

:deep(.tabs-wrap .el-tabs--card > .el-tabs__header) {
  border-bottom: none;
}

:deep(.tabs-wrap .el-tabs--card > .el-tabs__header .el-tabs__nav) {
  border: none !important;
  border-radius: 0 !important;
  overflow: visible;
}

:deep(.tabs-wrap .el-tabs__nav-wrap.is-scrollable) {
  padding: 0 30px;
}

:deep(.tabs-wrap .el-tabs__nav-prev),
:deep(.tabs-wrap .el-tabs__nav-next) {
  width: 28px;
  height: 32px;
  line-height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  top: 0;
  color: #64748b;
  border: 1px solid #e6ebf2;
  border-top-color: #d8e0ea;
  background: #ffffff;
  box-shadow: inset 0 1px 0 #d8e0ea, 0 2px 8px rgba(15, 23, 42, 0.08);
}

:deep(.tabs-wrap .el-tabs__nav-prev) {
  left: 0;
}

:deep(.tabs-wrap .el-tabs__nav-next) {
  right: 0;
}

:deep(.tabs-wrap .el-tabs--card > .el-tabs__header .el-tabs__item) {
  position: relative;
  height: 32px;
  line-height: 32px;
  min-width: 92px;
  max-width: 190px;
  padding: 0 22px 0 18px !important;
  color: #111827;
  font-size: 14px;
  font-weight: 400;
  background: #ffffff;
  border: 1px solid #e6ebf2 !important;
  border-top-color: #d8e0ea !important;
  border-radius: 0 !important;
  margin-right: 4px;
  box-shadow: inset 0 1px 0 #d8e0ea, 0 2px 8px rgba(15, 23, 42, 0.08);
  transition: color 0.18s ease, background-color 0.18s ease, box-shadow 0.18s ease;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:deep(.tabs-wrap .el-tabs--card > .el-tabs__header .el-tabs__item::after) {
  content: none;
}

:deep(.tabs-wrap .el-tabs--card > .el-tabs__header .el-tabs__item:last-child::after),
:deep(.tabs-wrap .el-tabs--card > .el-tabs__header .el-tabs__item.is-active::after),
:deep(.tabs-wrap .el-tabs--card > .el-tabs__header .el-tabs__item.is-active + .el-tabs__item::after),
:deep(.tabs-wrap .el-tabs--card > .el-tabs__header .el-tabs__item:hover::after),
:deep(.tabs-wrap .el-tabs--card > .el-tabs__header .el-tabs__item:hover + .el-tabs__item::after) {
  opacity: 0;
}

:deep(.tabs-wrap .el-tabs--card > .el-tabs__header .el-tabs__item:hover) {
  color: #1677ff;
  background: #fbfdff;
  border-top-color: #ccd6e3 !important;
  box-shadow: inset 0 1px 0 #ccd6e3, 0 3px 10px rgba(15, 23, 42, 0.10);
}

:deep(.tabs-wrap .el-tabs--card > .el-tabs__header .el-tabs__item:active) {
  transform: none;
}

:deep(.tabs-wrap .el-tabs--card > .el-tabs__header .el-tabs__item.is-active) {
  color: #1677ff;
  background: #ffffff;
  border-color: #dfe7f1 !important;
  border-top-color: #ccd6e3 !important;
  border-radius: 0 !important;
  box-shadow: inset 0 1px 0 #ccd6e3, 0 3px 12px rgba(22, 119, 255, 0.14);
  font-weight: 700;
  z-index: 2;
}

:deep(.tabs-wrap .el-tabs--card > .el-tabs__header .el-tabs__item.is-active::before) {
  content: "";
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: 0;
  height: 2px;
  border-radius: 0;
  background: #1677ff;
  pointer-events: none;
}

:deep(.tabs-wrap .el-tabs--card > .el-tabs__header .el-tabs__item:first-child) {
  border-left: 1px solid #e6ebf2 !important;
}

:deep(.tabs-wrap .el-tabs--card > .el-tabs__header .el-tabs__item:first-child.is-active) {
  border-left: 1px solid #dfe7f1 !important;
}

:deep(.tabs-wrap .tab-label) {
  display: inline-block;
  max-width: 100%;
  cursor: grab;
  user-select: none;
}

:deep(.tabs-wrap .tab-label:active) {
  cursor: grabbing;
}

:deep(.tabs-wrap .el-tabs__item .is-icon-close) {
  color: #8c8c8c;
  transition: background 0.15s ease, color 0.15s ease, transform 0.15s ease;
  border-radius: 50%;
  margin-left: 6px;
  font-size: 12px;
}

:deep(.tabs-wrap .el-tabs__item.is-active .is-icon-close) {
  color: #1677ff;
}

:deep(.tabs-wrap .el-tabs__item .is-icon-close:hover) {
  background: #ef4444 !important;
  color: #fff !important;
  transform: scale(1.15);
}

.context-menu {
  position: fixed;
  z-index: 9999;
  background: #fff;
  border: 1px solid #e4e9f2;
  border-radius: 10px;
  box-shadow: 0 10px 30px rgba(30, 48, 80, 0.15);
  padding: 6px 0;
  min-width: 110px;
  animation: menuPop 0.15s ease-out;
  transform-origin: top left;
}

@keyframes menuPop {
  0% {
    opacity: 0;
    transform: scale(0.92);
  }
  100% {
    opacity: 1;
    transform: scale(1);
  }
}

.context-menu .menu-item {
  padding: 8px 16px;
  cursor: pointer;
  font-size: 13px;
  color: #5a6b84;
  transition: background 0.15s ease, color 0.15s ease, padding-left 0.15s ease;
}

.context-menu .menu-item:hover {
  background: linear-gradient(90deg, rgba(45, 127, 249, 0.10), rgba(56, 189, 248, 0.05));
  color: #1e6fff;
  padding-left: 20px;
}

.context-menu .menu-item:active {
  background: rgba(45, 127, 249, 0.18);
}
</style>

<style scoped>
.layout-shell {
  height: 100vh;
  background: var(--bg-primary);
}

.layout-shell > .el-container {
  height: 100%;
  min-width: 0;
  overflow: hidden;
}

.sidebar {
  position: relative;
  z-index: 3;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #1f2937;
  background: #101828;
  box-shadow: 4px 0 16px rgba(16, 24, 40, 0.08);
  overflow-x: hidden;
  --el-transition-duration: 220ms;
  transition: width 220ms linear;
  will-change: width;
}

.logo {
  flex: 0 0 64px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  background: transparent;
  user-select: none;
  transition: gap 220ms linear, padding 220ms linear;
}

.logo-mark {
  flex: 0 0 36px;
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: 10px;
  color: #fff;
  background: #2563eb;
  box-shadow: 0 6px 14px rgba(37, 99, 235, 0.28);
  font-size: 19px;
  font-weight: 750;
  -webkit-text-fill-color: currentColor;
}

.logo-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  max-width: 180px;
  overflow: hidden;
  line-height: 1.2;
  white-space: nowrap;
  opacity: 1;
  transform: translateX(0);
  transition: max-width 220ms linear, opacity 160ms linear, transform 220ms linear;
}

.logo-copy strong {
  color: #fff;
  font-size: 14px;
  letter-spacing: 0.2px;
  -webkit-text-fill-color: #fff;
}

.sidebar.is-collapsed .logo {
  justify-content: center;
  gap: 0;
  padding: 0;
}

.sidebar.is-collapsed .logo-copy {
  max-width: 0;
  opacity: 0;
  transform: translateX(-6px);
  pointer-events: none;
}

:deep(.sidebar .el-menu) {
  flex: 1;
  padding: 8px;
  border-right: 0;
  background: transparent;
  overflow-y: auto;
  overflow-x: hidden;
  --el-menu-bg-color: transparent;
  --el-menu-text-color: #aeb8c7;
  --el-menu-hover-bg-color: rgba(255, 255, 255, 0.06);
  --el-menu-active-color: #ffffff;
}

:deep(.sidebar .el-menu--collapse) {
  width: auto;
}

:deep(.sidebar .horizontal-collapse-transition) {
  transition: width 220ms linear, padding-left 220ms linear, padding-right 220ms linear;
}

:deep(.sidebar .collapse-transition) {
  transition: height 220ms linear, padding-top 220ms linear, padding-bottom 220ms linear;
}

:deep(.sidebar .el-menu-item),
:deep(.sidebar .el-sub-menu__title) {
  height: 36px;
  margin: 1px 0;
  padding: 0 12px !important;
  border: 0;
  border-radius: 7px;
  color: #aeb8c7;
  font-size: 13px;
  transition: color 0.16s ease, background-color 0.16s ease;
}

:deep(.sidebar > .el-menu > .el-menu-item),
:deep(.sidebar > .el-menu > .el-sub-menu > .el-sub-menu__title) {
  height: 40px;
  margin: 1px 0;
  padding: 0 12px !important;
}

:deep(.sidebar .el-sub-menu .el-menu-item) {
  min-width: 0;
  padding-left: 28px !important;
  background: transparent;
}

:deep(.sidebar .el-sub-menu .el-sub-menu .el-menu-item) {
  padding-left: 38px !important;
}

:deep(.sidebar .el-sub-menu .el-sub-menu__title) {
  padding-left: 28px !important;
}

:deep(.sidebar .el-menu--collapse .el-menu-item),
:deep(.sidebar .el-menu--collapse .el-sub-menu__title) {
  justify-content: center;
  padding: 0 !important;
}

:deep(.sidebar .el-menu-item:hover),
:deep(.sidebar .el-sub-menu__title:hover) {
  color: #fff;
  background: rgba(255, 255, 255, 0.07);
}

:deep(.sidebar .el-menu-item:active),
:deep(.sidebar .el-sub-menu__title:active) {
  transform: none;
}

:deep(.sidebar .el-menu-item.is-active) {
  color: #fff;
  background: #2563eb;
  border: 0;
  box-shadow: 0 5px 12px rgba(37, 99, 235, 0.18);
  font-weight: 600;
}

:deep(.sidebar .el-sub-menu.is-active > .el-sub-menu__title) {
  color: #d0d5dd;
  background: transparent;
  font-weight: 500;
}

:deep(.sidebar .el-menu-item .el-icon),
:deep(.sidebar .el-sub-menu__title .el-icon) {
  width: 18px;
  font-size: 17px;
  color: #7f8da3;
  transition: color 0.16s ease;
}

:deep(.sidebar .el-menu-item:hover .el-icon),
:deep(.sidebar .el-sub-menu__title:hover .el-icon),
:deep(.sidebar .el-menu-item.is-active .el-icon) {
  color: currentColor;
  transform: none;
}

:deep(.sidebar .el-sub-menu__icon-arrow) {
  color: #667085;
}

.topbar {
  position: relative;
  z-index: 2;
  flex: 0 0 64px;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px 0 16px;
  border-bottom: 1px solid var(--border-soft);
  background: rgba(255, 255, 255, 0.96);
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.03);
  backdrop-filter: blur(12px);
}

.topbar-leading {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 12px;
}

.sidebar-toggle {
  width: 36px;
  height: 36px;
  color: #475467;
  font-size: 18px;
}

.sidebar-toggle:hover {
  color: var(--brand);
  background: var(--brand-soft);
  box-shadow: none;
}

.page-identity {
  min-width: 0;
}

.title {
  overflow: hidden;
  color: var(--text-primary);
  font-size: 16px;
  font-weight: 650;
  line-height: 1.3;
  text-overflow: ellipsis;
  white-space: nowrap;
  background: none;
  -webkit-text-fill-color: currentColor;
}

.subtitle {
  margin-top: 2px;
  color: var(--text-placeholder);
  font-size: 11px;
  line-height: 1.2;
}

.user-block {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-regular);
  cursor: default;
  outline: none;
}

.user-block :deep(.el-avatar) {
  color: #fff;
  background: #344054;
  font-size: 13px;
  font-weight: 650;
}

.user-copy {
  display: flex;
  flex-direction: column;
  min-width: 80px;
  line-height: 1.25;
}

.user-copy strong {
  color: var(--text-primary);
  font-size: 13px;
  font-weight: 600;
}

.user-copy span {
  margin-top: 2px;
  color: var(--text-placeholder);
  font-size: 11px;
}

.logout-button {
  color: var(--text-soft);
}

.logout-button:hover {
  color: var(--danger);
  background: #fff5f4;
}

.main-area {
  min-width: 0;
  width: 100%;
  padding: 0 20px 24px;
  background: var(--bg-primary);
  overflow-x: hidden;
  overflow-y: auto;
}

.tabs-wrap {
  position: sticky;
  z-index: 10;
  top: 0;
  margin: 0 -20px 20px;
  padding: 8px 20px 0;
  border-bottom: 1px solid var(--border-soft);
  border-radius: 0;
  background: #fff;
  box-shadow: none;
}

:deep(.tabs-wrap .el-tabs__header) {
  margin: 0;
  border: 0 !important;
}

:deep(.tabs-wrap .el-tabs__nav),
:deep(.tabs-wrap .el-tabs__nav-wrap::after) {
  border: 0 !important;
  background: transparent;
}

:deep(.tabs-wrap .el-tabs--card > .el-tabs__header .el-tabs__item) {
  min-width: auto;
  max-width: 190px;
  height: 36px;
  margin: 0 6px 0 0;
  padding: 0 12px !important;
  border: 1px solid #e4e9f1 !important;
  border-bottom-color: #d8dee8 !important;
  border-radius: 8px 8px 0 0 !important;
  color: var(--text-soft);
  background: #f8fafc;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9);
  font-size: 13px;
  font-weight: 500;
  transition: color 160ms ease, background-color 160ms ease, border-color 160ms ease, box-shadow 160ms ease, transform 160ms ease;
}

:deep(.tabs-wrap .el-tabs--card > .el-tabs__header .el-tabs__item:hover) {
  color: var(--brand);
  background: #fff;
  border-color: #cbd6e5 !important;
  box-shadow: 0 3px 9px rgba(31, 45, 61, 0.08);
}

:deep(.tabs-wrap .el-tabs--card > .el-tabs__header .el-tabs__item.is-active) {
  color: var(--brand);
  background: #fff;
  border-color: #b9c9dd !important;
  border-bottom-color: #fff !important;
  box-shadow: 0 4px 12px rgba(31, 45, 61, 0.12);
  font-weight: 600;
}

:deep(.tabs-wrap .el-tabs--card > .el-tabs__header .el-tabs__item.is-active::before) {
  left: 10px;
  right: 10px;
  bottom: 0;
  height: 2px;
  border-radius: 2px 2px 0 0;
  background: var(--brand);
}

:deep(.tabs-wrap .tab-label) {
  display: inline-flex;
  min-width: 0;
  max-width: 100%;
  align-items: center;
  gap: 7px;
}

:deep(.tabs-wrap .tab-title) {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:deep(.tabs-wrap .tab-icon) {
  width: 15px;
  height: 15px;
  flex: 0 0 15px;
  color: #667085;
  font-size: 15px;
  transition: color 160ms ease, transform 160ms ease;
}

:deep(.tabs-wrap .el-tabs__item:hover .tab-icon) {
  color: var(--brand);
  transform: translateY(-1px);
}

:deep(.tabs-wrap .el-tabs__item.is-active .tab-icon) {
  color: var(--brand);
  transform: scale(1.08);
}

:deep(.tabs-wrap .el-tabs__nav-prev),
:deep(.tabs-wrap .el-tabs__nav-next) {
  border: 0;
  background: #fff;
  box-shadow: none;
}

:deep(.tabs-wrap .el-tabs__item .is-icon-close) {
  width: 0;
  margin-left: 0;
  overflow: hidden;
  color: #98a2b3;
  opacity: 0;
  transform: scale(0.75);
  transform-origin: center;
  transition:
    width 180ms linear,
    margin-left 180ms linear,
    opacity 180ms linear,
    transform 180ms linear,
    color 150ms linear,
    background-color 150ms linear;
}

:deep(.tabs-wrap .el-tabs__item.is-closable:hover .is-icon-close),
:deep(.tabs-wrap .el-tabs__item.is-active.is-closable .is-icon-close) {
  width: 14px;
  margin-left: 6px;
  opacity: 1;
  transform: scale(1);
}

:deep(.tabs-wrap .el-tabs__item .is-icon-close:hover) {
  color: #fff;
  background: #ef4444;
  transform: scale(1.12);
}

.context-menu {
  border: 1px solid var(--border-soft);
  border-radius: 0;
  box-shadow: var(--shadow-lg);
  padding: 5px;
}

.context-menu .menu-item {
  padding: 8px 12px;
  border-radius: 0;
  color: var(--text-regular);
}

.context-menu .menu-item:hover {
  padding-left: 12px;
  color: var(--brand);
  background: var(--brand-soft);
}

.route-content {
  min-width: 0;
  width: 100%;
  transform-origin: top center;
}

.route-content.is-entering {
  animation: routeContentIn 280ms cubic-bezier(0.22, 1, 0.36, 1) both;
}

:deep(.sidebar .el-menu-item.is-active) {
  animation: menuItemSelect 220ms cubic-bezier(0.22, 1, 0.36, 1) both;
}

:deep(.sidebar .el-menu-item.is-active .el-icon) {
  animation: menuIconIn 260ms cubic-bezier(0.22, 1, 0.36, 1) both;
}

@keyframes routeContentIn {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes menuItemSelect {
  from {
    opacity: 0.72;
    transform: translateX(-4px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

@keyframes menuIconIn {
  0% { transform: scale(0.84); }
  70% { transform: scale(1.08); }
  100% { transform: scale(1); }
}

@media (prefers-reduced-motion: reduce) {
  .route-content.is-entering,
  :deep(.sidebar .el-menu-item.is-active),
  :deep(.sidebar .el-menu-item.is-active .el-icon) {
    animation: none;
  }
}

@media (max-width: 900px) {
  .subtitle,
  .user-copy,
  .user-divider {
    display: none;
  }

  .topbar {
    padding-right: 12px;
  }

  .main-area {
    padding-right: 12px;
    padding-left: 12px;
  }

  .tabs-wrap {
    margin-right: -12px;
    margin-left: -12px;
    padding-right: 12px;
    padding-left: 12px;
  }
}
</style>
