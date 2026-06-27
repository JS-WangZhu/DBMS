<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>用户权限管理</span>
          <div class="header-actions">
            <el-button @click="loadUsers">刷新用户</el-button>
          </div>
        </div>
      </template>

      <el-form :model="form" label-width="110px">
        <el-form-item label="选择用户">
          <el-select v-model="selectedUserId" filterable style="width: 260px" @change="loadPermissions">
            <el-option v-for="user in users" :key="user.id" :label="`${user.username} (${user.role})`" :value="user.id" />
          </el-select>
        </el-form-item>

        <el-form-item label="菜单权限">
          <el-tree
            v-if="selectedUserId"
            ref="menuTreeRef"
            class="menu-tree"
            node-key="key"
            show-checkbox
            default-expand-all
            :data="menuTreeData"
            :props="{ label: 'label', children: 'children', disabled: 'disabled' }"
            :empty-text="'暂无菜单可分配'"
          />
          <el-text v-else type="info">请选择用户后进行菜单授权</el-text>
        </el-form-item>

        <el-form-item label="数据访问">
          <div v-if="selectedUserId" class="cluster-access-wrap">
            <div class="cluster-access-toolbar">
              <el-input
                v-model="clusterSearchKeyword"
                clearable
                placeholder="搜索集群"
                style="width: 260px"
                @input="onClusterSearchInput"
              />
              <div class="cluster-access-bulk">
                <div class="bulk-item">
                  <span class="bulk-label">所有查询</span>
                  <el-switch
                    v-model="allCanQuery"
                    :disabled="isAdminUser || !clusterPermissions.length"
                    active-color="#10b981"
                    inline-prompt
                    active-text="开"
                    inactive-text="关"
                  />
                </div>
                <div class="bulk-item">
                  <span class="bulk-label">所有变更</span>
                  <el-switch
                    v-model="allCanChange"
                    :disabled="isAdminUser || !clusterPermissions.length"
                    active-color="#ef4444"
                    inline-prompt
                    active-text="开"
                    inactive-text="关"
                  />
                </div>
              </div>
            </div>
            <el-table :data="pagedClusterPermissions" size="small" stripe>
              <el-table-column prop="label" label="集群" min-width="220" />
              <el-table-column label="查询">
                <template #default="scope">
                  <el-switch v-model="scope.row.can_query" :disabled="isAdminUser" />
                </template>
              </el-table-column>
              <el-table-column label="变更">
                <template #default="scope">
                  <el-switch v-model="scope.row.can_change" :disabled="isAdminUser" />
                </template>
              </el-table-column>
            </el-table>
            <div class="cluster-access-pager">
              <el-pagination
                v-model:current-page="clusterPager.page"
                v-model:page-size="clusterPager.pageSize"
                :page-sizes="[10, 20, 50, 100]"
                layout="total, sizes, prev, pager, next, jumper"
                :total="filteredClusterPermissions.length"
              />
            </div>
          </div>
          <el-text v-else type="info">请选择用户后设置数据访问权限</el-text>
        </el-form-item>

        <el-form-item label="API Key">
          <div class="api-key-actions" v-if="selectedUserId">
            <el-button type="primary" @click="createApiKey" :disabled="!selectedUserId || isAdminUser">生成API Key</el-button>
          </div>
          <el-table v-if="selectedUserId" :data="apiKeys" size="small" stripe>
            <el-table-column prop="token" label="Token" min-width="240" />
            <el-table-column prop="status" label="状态" width="120" />
            <el-table-column label="操作" width="120">
              <template #default="scope">
                <el-button link type="danger" :disabled="isAdminUser" @click="removeApiKey(scope.row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-text v-else type="info">请选择用户后管理 API Key</el-text>
        </el-form-item>
      </el-form>

      <div class="action-row">
        <el-button type="primary" :loading="saving" @click="savePermissions" :disabled="!selectedUserId || isAdminUser">保存权限</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { listClusters } from "../api/modules/clusters";
import { listUsers } from "../api/modules/users";
import { createUserApiKey, deleteUserApiKey, listUserPermissions, updateUserPermissions } from "../api/modules/backups";

const users = ref([]);
const clusters = ref([]);
const selectedUserId = ref(null);
const saving = ref(false);
const apiKeys = ref([]);
const clusterSearchKeyword = ref("");
const clusterPager = reactive({
  page: 1,
  pageSize: 10,
});

const form = reactive({
  menu_keys: [],
});

const clusterPermissions = ref([]);

const menuTreeRef = ref(null);
const menuCatalog = ref([]);
const menuTreeData = ref([]);
const menuLeafKeys = ref([]);

const selectedUser = computed(() => users.value.find((item) => Number(item.id) === Number(selectedUserId.value)) || null);
const isAdminUser = computed(() => selectedUser.value?.role === "admin");
const filteredClusterPermissions = computed(() => {
  const keyword = clusterSearchKeyword.value.trim().toLowerCase();
  if (!keyword) {
    return clusterPermissions.value;
  }
  return clusterPermissions.value.filter((item) => String(item.label || "").toLowerCase().includes(keyword));
});
const pagedClusterPermissions = computed(() => {
  const start = (clusterPager.page - 1) * clusterPager.pageSize;
  return filteredClusterPermissions.value.slice(start, start + clusterPager.pageSize);
});

// 批量开关：所有查询 / 所有变更
const allCanQuery = computed({
  get: () => clusterPermissions.value.length > 0 && clusterPermissions.value.every((item) => item.can_query),
  set: (val) => {
    clusterPermissions.value.forEach((item) => { item.can_query = !!val; });
  },
});
const allCanChange = computed({
  get: () => clusterPermissions.value.length > 0 && clusterPermissions.value.every((item) => item.can_change),
  set: (val) => {
    clusterPermissions.value.forEach((item) => { item.can_change = !!val; });
  },
});

async function loadUsers() {
  const { data } = await listUsers();
  users.value = data.data?.items || [];
  if (!selectedUserId.value) {
    const adminUser = users.value.find((item) => item.role === "admin");
    const fallback = adminUser || users.value[0];
    selectedUserId.value = fallback ? fallback.id : null;
  } else {
    const exists = users.value.some((item) => Number(item.id) === Number(selectedUserId.value));
    if (!exists) {
      const adminUser = users.value.find((item) => item.role === "admin");
      const fallback = adminUser || users.value[0];
      selectedUserId.value = fallback ? fallback.id : null;
    }
  }
}

async function loadClusters() {
  const tasks = ["mysql", "mongodb", "redis", "doris"].map((dbType) => listClusters(dbType));
  const results = await Promise.all(tasks);
  clusters.value = results.flatMap((res) => res.data?.data || []);
}

async function loadPermissions() {
  if (!selectedUserId.value) return;
  const { data } = await listUserPermissions(selectedUserId.value);
  const payload = data.data || {};
  const catalog = Array.isArray(payload.menu_catalog) ? payload.menu_catalog : [];
  menuCatalog.value = catalog;
  const tree = buildMenuTree(catalog, isAdminUser.value);
  menuTreeData.value = tree.nodes;
  menuLeafKeys.value = tree.leafKeys;
  const allKeys = catalog.map((item) => item.key);
  form.menu_keys = isAdminUser.value ? allKeys : (payload.menu_keys || []);
  await nextTick();
  if (menuTreeRef.value) {
    menuTreeRef.value.setCheckedKeys(form.menu_keys);
  }
  apiKeys.value = payload.api_keys || [];

  const perms = payload.cluster_permissions || [];
  clusterPermissions.value = clusters.value.map((cluster) => {
    const matched = perms.find((p) => p.cluster_id === cluster.id);
    return {
      cluster_id: cluster.id,
      label: [cluster.business_line || cluster.namespace, cluster.environment, cluster.name].filter(Boolean).join("/"),
      can_query: matched ? matched.can_query : false,
      can_change: matched ? matched.can_change : false,
    };
  });
  clusterPager.page = 1;
  clusterSearchKeyword.value = "";
}

function onClusterSearchInput() {
  clusterPager.page = 1;
}

async function savePermissions() {
  if (!selectedUserId.value) return;
  saving.value = true;
  try {
    const checkedKeys = menuTreeRef.value ? menuTreeRef.value.getCheckedKeys(false) : [];
    const checkedLeafKeys = checkedKeys.filter((key) => menuLeafKeys.value.includes(key));
    form.menu_keys = checkedLeafKeys;
    await updateUserPermissions(selectedUserId.value, {
      menu_keys: checkedLeafKeys,
      cluster_permissions: clusterPermissions.value.map((item) => ({
        cluster_id: item.cluster_id,
        can_query: item.can_query,
        can_change: item.can_change,
      })),
    });
    ElMessage.success("权限已保存");
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "保存失败");
  } finally {
    saving.value = false;
  }
}

function buildMenuTree(catalog, disabled) {
  const leafMap = new Map((catalog || []).map((item) => [item.key, { key: item.key, label: item.label, disabled }]));
  const rootNodes = [
    { key: "dashboard", label: "总览", children: ["dashboard"] },
    { key: "service_manage", label: "服务管理", children: [
      { key: "mysql", label: "MySQL", children: ["mysql_instances", "mysql_clusters", "mysql_connections"] },
      { key: "mongodb", label: "MongoDB", children: ["mongodb_instances", "mongodb_clusters"] },
      { key: "redis", label: "Redis", children: ["redis_instances", "redis_clusters"] },
      { key: "doris", label: "Doris", children: ["doris_instances", "doris_clusters"] },
    ] },
    { key: "data_access", label: "数据访问", children: ["data_query", "data_change", "data_history"] },
    { key: "task_management", label: "任务管理", children: ["task_schedule", "task_results"] },
    { key: "backup", label: "备份管理", children: [
      { key: "backup_policies", label: "策略管理", children: ["backup_mysql_policies", "backup_mongo_policies"] },
      "backup_records",
      { key: "backup_config", label: "配置管理", children: ["backup_tool_configs", "backup_s3_storage", "backup_keys"] },
    ] },
    { key: "config", label: "配置管理", children: ["ai_model_config", "backup_agents", "ha_config", "instance_status_config", "inspection_param_config", "data_query_op_config", "backup_notify_targets", "mcp_platform", "sso_config"] },
    { key: "users", label: "用户管理", children: ["users_info", "users_permissions", "users_role_groups"] },
  ];

  function convert(node) {
    if (typeof node === "string") {
      return leafMap.get(node) || null;
    }
    const children = (node.children || []).map(convert).filter(Boolean);
    if (!children.length) {
      return null;
    }
    return { key: node.key, label: node.label, disabled, children };
  }

  const nodes = rootNodes.map(convert).filter(Boolean);
  const leafKeys = Array.from(leafMap.keys());
  return { nodes, leafKeys };
}

async function createApiKey() {
  if (!selectedUserId.value) return;
  try {
    const { data } = await createUserApiKey(selectedUserId.value);
    apiKeys.value = [...apiKeys.value, data.data];
    ElMessage.success("API Key 已生成");
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "创建失败");
  }
}

async function removeApiKey(row) {
  try {
    await ElMessageBox.confirm("确认删除该 API Key 吗", "提示", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await deleteUserApiKey(selectedUserId.value, row.id);
    apiKeys.value = apiKeys.value.filter((item) => item.id !== row.id);
    ElMessage.success("API Key 已删除");
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.message || "删除失败");
    }
  }
}

onMounted(async () => {
  await Promise.all([loadUsers(), loadClusters()]);
  if (selectedUserId.value) {
    await loadPermissions();
  }
});
</script>

<style scoped>
.page {
  padding: 20px;
}

.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-actions {
  display: flex;
  gap: 10px;
}

.action-row {
  margin-top: 12px;
}

.api-key-actions {
  margin-bottom: 8px;
}

.cluster-access-wrap {
  width: 100%;
}

.cluster-access-toolbar {
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
}

.cluster-access-bulk {
  display: inline-flex;
  align-items: center;
  gap: 18px;
  padding: 6px 14px;
  background: linear-gradient(90deg, #f0fdf4 0%, #fef2f2 100%);
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.bulk-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.bulk-label {
  font-size: 13px;
  color: #475569;
  font-weight: 500;
}

.cluster-access-pager {
  margin-top: 10px;
  display: flex;
  justify-content: flex-end;
}
</style>
