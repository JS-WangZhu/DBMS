<template>
  <el-container class="layout-shell">
    <el-aside width="240px" class="sidebar">
      <div class="logo">DBMS Platform</div>
      <el-menu :default-active="route.path" @select="onMenuSelect">
        <el-menu-item v-if="hasMenu('dashboard')" index="/dashboard">
          <el-icon><Odometer /></el-icon>
          <span>总览</span>
        </el-menu-item>

        <el-sub-menu v-if="hasAnyMenu(['mysql_instances','mysql_clusters','mysql_connections','mongodb_instances','mongodb_clusters','redis_instances','redis_clusters','doris_instances','doris_clusters','inspection_manage'])" index="service-manage">
          <template #title>
            <el-icon><Setting /></el-icon>
            <span>服务管理</span>
          </template>

          <el-sub-menu v-if="hasAnyMenu(['mysql_instances','mysql_clusters','mysql_connections'])" index="db-mysql">
            <template #title>
              <el-icon><Coin /></el-icon>
              <span>MySQL</span>
            </template>
            <el-menu-item v-if="hasMenu('mysql_instances')" index="/databases/mysql/instances">
              <el-icon><Coin /></el-icon>
              <span>实例管理</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('mysql_clusters')" index="/databases/mysql/clusters">
              <el-icon><Grid /></el-icon>
              <span>集群管理</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('mysql_connections')" index="/databases/mysql/connections">
              <el-icon><Link /></el-icon>
              <span>连接管理</span>
            </el-menu-item>
          </el-sub-menu>

          <el-sub-menu v-if="hasAnyMenu(['mongodb_instances','mongodb_clusters'])" index="db-mongodb">
            <template #title>
              <el-icon><Files /></el-icon>
              <span>MongoDB</span>
            </template>
            <el-menu-item v-if="hasMenu('mongodb_instances')" index="/databases/mongodb/instances">
              <el-icon><Files /></el-icon>
              <span>实例管理</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('mongodb_clusters')" index="/databases/mongodb/clusters">
              <el-icon><Grid /></el-icon>
              <span>集群管理</span>
            </el-menu-item>
          </el-sub-menu>

          <el-sub-menu v-if="hasAnyMenu(['redis_instances','redis_clusters'])" index="db-redis">
            <template #title>
              <el-icon><Lightning /></el-icon>
              <span>Redis</span>
            </template>
            <el-menu-item v-if="hasMenu('redis_instances')" index="/databases/redis/instances">
              <el-icon><Lightning /></el-icon>
              <span>实例管理</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('redis_clusters')" index="/databases/redis/clusters">
              <el-icon><Grid /></el-icon>
              <span>集群管理</span>
            </el-menu-item>
          </el-sub-menu>

          <el-sub-menu v-if="hasAnyMenu(['doris_instances','doris_clusters'])" index="db-doris">
            <template #title>
              <el-icon><DataAnalysis /></el-icon>
              <span>Doris</span>
            </template>
            <el-menu-item v-if="hasMenu('doris_instances')" index="/databases/doris/instances">
              <el-icon><DataAnalysis /></el-icon>
              <span>实例管理</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('doris_clusters')" index="/databases/doris/clusters">
              <el-icon><Grid /></el-icon>
              <span>集群管理</span>
            </el-menu-item>
          </el-sub-menu>
        </el-sub-menu>
          <el-menu-item v-if="hasMenu('inspection_manage')" index="/service/inspection">
            <el-icon><Bell /></el-icon>
            <span>巡检管理</span>
          </el-menu-item>
        <el-sub-menu v-if="hasAnyMenu(['data_query','data_change','data_history'])" index="data-access">
          <template #title>
            <el-icon><Search /></el-icon>
            <span>数据访问</span>
          </template>
          <el-menu-item v-if="hasMenu('data_query')" index="/data-access/query">
            <el-icon><Search /></el-icon>
            <span>数据查询</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('data_change')" index="/data-access/change">
            <el-icon><Edit /></el-icon>
            <span>数据变更</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('ai_analysis')" index="/data-access/ai-analysis">
            <el-icon><Cpu /></el-icon>
            <span>智能分析</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('data_history')" index="/data-access/history">
            <el-icon><Timer /></el-icon>
            <span>历史记录</span>
          </el-menu-item>
        </el-sub-menu>

        <el-sub-menu v-if="hasAnyMenu(['backup_mysql_policies','backup_mongo_policies','backup_records','backup_tool_configs','backup_agents','backup_notify_targets','backup_s3_storage','backup_keys'])" index="backup">
          <template #title>
            <el-icon><Collection /></el-icon>
            <span>备份管理</span>
          </template>
          <el-sub-menu v-if="hasAnyMenu(['backup_mysql_policies','backup_mongo_policies'])" index="backup-policies">
            <template #title>
              <el-icon><Notebook /></el-icon>
              <span>策略管理</span>
            </template>
            <el-menu-item v-if="hasMenu('backup_mysql_policies')" index="/backups/mysql-policies">
              <el-icon><Coin /></el-icon>
              <span>MySQL策略</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('backup_mongo_policies')" index="/backups/mongo-policies">
              <el-icon><Files /></el-icon>
              <span>MongoDB策略</span>
            </el-menu-item>
          </el-sub-menu>
          <el-menu-item v-if="hasMenu('backup_records')" index="/backups/records">
            <el-icon><DocumentCopy /></el-icon>
            <span>备份记录</span>
          </el-menu-item>
          <el-sub-menu v-if="hasAnyMenu(['backup_tool_configs','backup_agents','backup_notify_targets','backup_s3_storage','backup_keys'])" index="backup-config">
            <template #title>
              <el-icon><Operation /></el-icon>
              <span>配置管理</span>
            </template>
            <el-menu-item v-if="hasMenu('backup_tool_configs')" index="/backups/tool-configs">
              <el-icon><Tools /></el-icon>
              <span>备份工具管理</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('backup_agents')" index="/backups/agents">
              <el-icon><Monitor /></el-icon>
              <span>Agent管理</span>
            </el-menu-item>
            <el-menu-item v-if="hasMenu('backup_notify_targets')" index="/backups/notify-targets">
              <el-icon><Bell /></el-icon>
              <span>通知地址管理</span>
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

        <el-sub-menu v-if="hasAnyMenu(['ai_model_config', 'ha_config', 'inspection_param_config'])" index="config">
          <template #title>
            <el-icon><Management /></el-icon>
            <span>配置管理</span>
          </template>
          <el-menu-item v-if="hasMenu('ai_model_config')" index="/config/ai-models">
            <el-icon><Monitor /></el-icon>
            <span>AI模型管理</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('ha_config')" index="/config/ha">
            <el-icon><Setting /></el-icon>
            <span>高可用配置管理</span>
          </el-menu-item>
          <el-menu-item v-if="hasMenu('inspection_param_config')" index="/config/inspection">
            <el-icon><Operation /></el-icon>
            <span>巡检参数管理</span>
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
          <el-tabs v-model="activeTabId" type="card" draggable @tab-change="onTabChange" @tab-remove="removeTab" @tab-dragend="onTabDragend">
            <el-tab-pane v-for="tab in tabs" :key="tab.id" :name="tab.id" :closable="tabs.length > 1">
              <template #label>
                <span @contextmenu.prevent="onTabRightClick($event, tab)">{{ tab.title }}</span>
              </template>
            </el-tab-pane>
          </el-tabs>

          <div v-if="contextMenu.visible" class="context-menu" :style="{ top: contextMenu.y + 'px', left: contextMenu.x + 'px' }" @click.stop>
            <div class="menu-item" @click="closeLeft">关闭左侧</div>
            <div class="menu-item" @click="closeRight">关闭右侧</div>
            <div class="menu-item" @click="closeOthers">关闭其他</div>
            <div class="menu-item" @click="closeAll">关闭全部</div>
          </div>
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
  Bell,
  Box,
  Coin,
  Collection,
  Cpu,
  DataAnalysis,
  DocumentCopy,
  Edit,
  Files,
  Grid,
  Key,
  Lightning,
  Link,
  List,
  Lock,
  Management,
  Monitor,
  Notebook,
  Odometer,
  Operation,
  Search,
  Setting,
  Timer,
  Tools,
  User,
  UserFilled,
} from "@element-plus/icons-vue";
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
  "/databases/mysql/instances": "mysql_instances",
  "/databases/mysql/clusters": "mysql_clusters",
  "/databases/mysql/connections": "mysql_connections",
  "/databases/mongodb/instances": "mongodb_instances",
  "/databases/mongodb/clusters": "mongodb_clusters",
  "/databases/redis/instances": "redis_instances",
  "/databases/redis/clusters": "redis_clusters",
  "/databases/doris/instances": "doris_instances",
  "/databases/doris/clusters": "doris_clusters",
  "/service/inspection": "inspection_manage",
  "/data-access/query": "data_query",
  "/data-access/change": "data_change",
  "/data-access/history": "data_history",
  "/data-access/ai-analysis": "ai_analysis",
  "/backups/mysql-policies": "backup_mysql_policies",
  "/backups/mongo-policies": "backup_mongo_policies",
  "/backups/records": "backup_records",
  "/backups/tool-configs": "backup_tool_configs",
  "/backups/agents": "backup_agents",
  "/backups/notify-targets": "backup_notify_targets",
  "/backups/s3-storage": "backup_s3_storage",
  "/backups/keys": "backup_keys",
  "/users/info": "users_info",
  "/users/role-groups": "users_role_groups",
  "/users/permissions": "users_permissions",
  "/config/ai-models": "ai_model_config",
  "/config/ha": "ha_config",
  "/config/inspection": "inspection_param_config",
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

function onTabDragend() {
  // el-tabs 自带拖拽排序
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
  background: #f3f4f6;
}

.sidebar {
  border-right: 1px solid #dfe6f1;
  background: linear-gradient(180deg, #ffffff 0%, #f4f5f7 100%);
}

:deep(.sidebar .el-menu-item),
:deep(.sidebar .el-sub-menu__title) {
  border-left: 1px solid transparent;
}

:deep(.sidebar .el-menu-item.is-active),
:deep(.sidebar .el-sub-menu.is-active > .el-sub-menu__title) {
  border-left-color: #2d79d8;
}

.logo {
  padding: 18px 14px;
  font-weight: 700;
  color: #0b4376;
  letter-spacing: 0.5px;
}

.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #dfe6f1;
  background: #ffffff;
}

.title {
  font-size: 18px;
  font-weight: 600;
}

.user-block {
  display: flex;
  align-items: center;
  gap: 12px;
}

.main-area {
  padding: 10px 12px 16px;
  background: #f3f4f6;
  min-width: 0;
  width: 100%;
}

.tabs-wrap {
  padding: 8px 10px 8px;
  margin: 0 4px 8px;
  border: 1px solid #d7dee8;
  border-radius: 10px;
  background: linear-gradient(180deg, #f9fafc 0%, #f0f3f7 100%);
  box-shadow: inset 0 1px 0 #ffffff, 0 1px 2px rgba(31, 52, 77, 0.06);
}

:deep(.tabs-wrap .el-tabs__header) {
  margin: 0;
}

:deep(.tabs-wrap .el-tabs__nav-wrap::after) {
  background-color: #ccd5e1;
}

:deep(.tabs-wrap .el-tabs--card > .el-tabs__header .el-tabs__item) {
  height: 36px;
  line-height: 36px;
  color: #3a4f67;
  font-weight: 600;
  background: linear-gradient(180deg, #eef3f8 0%, #e4ebf3 100%);
  border: 1px solid #c9d6e5;
  transition: all 0.18s ease;
}

:deep(.tabs-wrap .el-tabs--card > .el-tabs__header .el-tabs__item:hover) {
  color: #224f7d;
  background: linear-gradient(180deg, #f5f8fc 0%, #ebf1f8 100%);
}

:deep(.tabs-wrap .el-tabs--card > .el-tabs__header .el-tabs__item.is-active) {
  color: #15508f;
  background: #ffffff;
  border-top: 2px solid #2d79d8;
  border-bottom-color: #ffffff;
  box-shadow: 0 -1px 0 #ffffff, 0 1px 2px rgba(18, 59, 101, 0.08);
}

:deep(.tabs-wrap .el-tabs__item .el-icon-close) {
  color: #5c7088;
}

:deep(.tabs-wrap .el-tabs__item.is-active .el-icon-close) {
  color: #1f5f9f;
}

.context-menu {
  position: fixed;
  z-index: 9999;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.15);
  padding: 4px 0;
  min-width: 100px;
}

.context-menu .menu-item {
  padding: 8px 16px;
  cursor: pointer;
  font-size: 13px;
  color: #606266;
}

.context-menu .menu-item:hover {
  background: #f5f7fa;
  color: #409eff;
}
</style>
