<template>
  <el-container class="layout-shell">
    <el-aside width="240px" class="sidebar">
      <div class="logo">DBMS Platform</div>
      <el-menu :default-active="route.path" @select="onMenuSelect">
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

        <el-sub-menu v-if="hasAnyMenu(['mysql_instances','mysql_clusters','mysql_connections','mongodb_instances','mongodb_clusters','mongodb_connections','redis_instances','redis_clusters','redis_connections','postgresql_instances','postgresql_clusters','doris_instances','doris_clusters','inspection_manage'])" index="service-manage">
          <template #title>
            <el-icon><Menu /></el-icon>
            <span>服务管理</span>
          </template>

          <el-sub-menu v-if="hasAnyMenu(['mysql_instances','mysql_clusters','mysql_connections'])" index="db-mysql">
            <template #title>
              <el-icon class="db-brand-icon"><MysqlIcon /></el-icon>
              <span>MySQL</span>
            </template>
            <el-menu-item v-if="hasMenu('mysql_instances')" index="/databases/mysql/instances">
              <el-icon class="db-brand-icon"><MysqlIcon /></el-icon>
              <span>实例管理</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('mysql_clusters')" index="/databases/mysql/clusters">
              <el-icon><Share /></el-icon>
              <span>集群管理</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('mysql_connections')" index="/databases/mysql/connections">
              <el-icon><Connection /></el-icon>
              <span>连接管理</span>
            </el-menu-item>
          </el-sub-menu>

          <el-sub-menu v-if="hasAnyMenu(['mongodb_instances','mongodb_clusters','mongodb_connections'])" index="db-mongodb">
            <template #title>
              <el-icon class="db-brand-icon"><MongoIcon /></el-icon>
              <span>MongoDB</span>
            </template>
            <el-menu-item v-if="hasMenu('mongodb_instances')" index="/databases/mongodb/instances">
              <el-icon class="db-brand-icon"><MongoIcon /></el-icon>
              <span>实例管理</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('mongodb_clusters')" index="/databases/mongodb/clusters">
              <el-icon><FolderOpened /></el-icon>
              <span>集群管理</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('mongodb_connections')" index="/databases/mongodb/connections">
              <el-icon><Link /></el-icon>
              <span>连接管理</span>
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
          <el-menu-item v-if="hasMenu('inspection_manage')" index="/service/inspection">
            <el-icon><CircleCheck /></el-icon>
            <span>巡检管理</span>
          </el-menu-item>
        <el-sub-menu v-if="hasAnyMenu(['data_query','data_change','data_history'])" index="data-access">
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

        <el-sub-menu v-if="hasAnyMenu(['backup_mysql_policies','backup_mongo_policies','backup_records','backup_tool_configs','backup_s3_storage','backup_keys','backup_overview'])" index="backup">
          <template #title>
            <el-icon><Collection /></el-icon>
            <span>备份管理</span>
          </template>
          <el-menu-item v-if="hasMenu('backup_overview')" index="/backups/overview">
            <el-icon><Notebook /></el-icon>
            <span>备份总览</span>
          </el-menu-item>
          <el-sub-menu v-if="hasAnyMenu(['backup_mysql_policies','backup_mongo_policies'])" index="backup-policies">
            <template #title>
              <el-icon><PieChart /></el-icon>
              <span>策略管理</span>
            </template>
            <el-menu-item v-if="hasMenu('backup_mysql_policies')" index="/backups/mysql-policies">
              <el-icon class="db-brand-icon"><MysqlIcon /></el-icon>
              <span>MySQL策略</span>
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

        <el-sub-menu v-if="hasAnyMenu(['users_info','users_permissions','users_role_groups'])" index="users">
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
        </el-sub-menu>

        <el-sub-menu v-if="hasAnyMenu(['ai_model_config', 'ha_config', 'instance_status_config', 'inspection_param_config', 'data_query_op_config', 'backup_notify_targets', 'backup_agents', 'domain_config', 'mcp_platform', 'sso_config'])" index="config">
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
          <el-menu-item v-if="hasMenu('inspection_param_config')" index="/config/inspection">
            <el-icon><Setting /></el-icon>
            <span>巡检参数管理</span>
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
        </el-sub-menu>
      </el-menu>
    </el-aside>

    <el-container>
      <el-header class="topbar">
        <div class="title">DBMS</div>
        <div class="user-block">
          <span>{{ username }}</span>
          <el-button link type="primary" @click="logout">退出</el-button>
        </div>
      </el-header>
      <el-main class="main-area">
        <div class="tabs-wrap">
          <el-tabs v-model="activeTabId" type="card" @tab-change="onTabChange" @tab-remove="removeTab">
            <el-tab-pane v-for="tab in tabs" :key="tab.id" :name="tab.id" :closable="tabs.length > 1">
              <template #label>
                <span
                  class="tab-label"
                  draggable="true"
                  @dragstart="onTabDragStart($event, tab)"
                  @dragover.prevent
                  @drop.prevent="onTabDrop(tab)"
                  @dragend="onTabDragEnd"
                  @contextmenu.prevent="onTabRightClick($event, tab)"
                >
                  {{ tab.title }}
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
        <router-view v-slot="{ Component }">
          <keep-alive>
            <component :is="Component" />
          </keep-alive>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
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
  Files,
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
import { listMyUserPermissions } from "../api/modules/backups";

const router = useRouter();
const route = useRoute();

const tabs = ref([]);
const activeTabId = ref("");
let tabSeq = 0;

const contextMenu = ref({
  visible: false,
  x: 0,
  y: 0,
  targetTab: null,
});
const draggingTabId = ref("");

const username = computed(() => {
  try {
    const user = JSON.parse(localStorage.getItem("dbms_user") || "{}");
    return user.username || "unknown";
  } catch {
    return "unknown";
  }
});

const userId = computed(() => {
  try {
    const user = JSON.parse(localStorage.getItem("dbms_user") || "{}");
    return user.id || null;
  } catch {
    return null;
  }
});

const menuKeys = ref([]);
const permissionsLoaded = ref(false);
const routePermissionMap = {
  "/dashboard": "dashboard",
  "/resources/database-apply": "database_apply",
  "/resources/database-recycle": "database_recycle",
  "/resources/application-history": "application_history",
  "/databases/mysql/instances": "mysql_instances",
  "/databases/mysql/clusters": "mysql_clusters",
  "/databases/mysql/connections": "mysql_connections",
  "/databases/mongodb/instances": "mongodb_instances",
  "/databases/mongodb/clusters": "mongodb_clusters",
  "/databases/mongodb/connections": "mongodb_connections",
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
  "/tasks/schedules": "task_schedule",
  "/tasks/results": "task_results",
  "/tools/aliyun-dns": "aliyun_dns_tool",
  "/backups/mysql-policies": "backup_mysql_policies",
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
  "/config/ai-models": "ai_model_config",
  "/config/ha": "ha_config",
  "/config/instance-status": "instance_status_config",
  "/config/inspection": "inspection_param_config",
  "/config/data-query-ops": "data_query_op_config",
  "/config/domain": "domain_config",
  "/config/mcp-platform": "mcp_platform",
  "/config/sso": "sso_config",
};

function hasMenu(key) {
  try {
    const user = JSON.parse(localStorage.getItem("dbms_user") || "{}");
    if (user.role === "admin") {
      return true;
    }
  } catch {
    // ignore
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

function onTabChange(tabId) {
  const target = tabs.value.find((item) => item.id === tabId);
  if (!target || target.path === route.path) {
    return;
  }
  router.push(target.path);
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
      router.push(fallback.path);
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
  router.push(targetTab.path);
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
    permissionsLoaded.value = true;
    return;
  }
  try {
    const { data } = await listMyUserPermissions();
    menuKeys.value = data.data?.menu_keys || [];
  } catch {
    menuKeys.value = [];
  } finally {
    permissionsLoaded.value = true;
    enforceRoutePermission();
  }
}

function enforceRoutePermission() {
  try {
    const user = JSON.parse(localStorage.getItem("dbms_user") || "{}");
    if (user.role === "admin") {
      return;
    }
  } catch {
  }
  if (!permissionsLoaded.value) {
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

watch(
  () => route.path,
  () => {
    ensureRouteTab(route);
    enforceRoutePermission();
  },
  { immediate: true },
);

onMounted(() => {
  window.addEventListener("click", onDocumentClick);
  loadMenuPermissions();
});

onUnmounted(() => {
  window.removeEventListener("click", onDocumentClick);
});

function logout() {
  localStorage.removeItem("dbms_token");
  localStorage.removeItem("dbms_user");
  router.push("/login");
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
