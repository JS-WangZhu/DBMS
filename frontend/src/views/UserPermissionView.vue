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

import { listUsers } from "../api/modules/users";
import { createUserApiKey, deleteUserApiKey, listUserPermissions, updateUserPermissions } from "../api/modules/backups";
import { buildMenuPermissionTree } from "../utils/menuPermissionTree";

const users = ref([]);
const selectedUserId = ref(null);
const saving = ref(false);
const apiKeys = ref([]);

const form = reactive({
  menu_keys: [],
});

const menuTreeRef = ref(null);
const menuCatalog = ref([]);
const menuTreeData = ref([]);
const menuLeafKeys = ref([]);

const selectedUser = computed(() => users.value.find((item) => Number(item.id) === Number(selectedUserId.value)) || null);
const isAdminUser = computed(() => selectedUser.value?.role === "admin");
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

async function loadPermissions() {
  if (!selectedUserId.value) return;
  const { data } = await listUserPermissions(selectedUserId.value);
  const payload = data.data || {};
  const catalog = Array.isArray(payload.menu_catalog) ? payload.menu_catalog : [];
  menuCatalog.value = catalog;
  const tree = buildMenuPermissionTree(catalog, { disabled: isAdminUser.value });
  menuTreeData.value = tree.nodes;
  menuLeafKeys.value = tree.leafKeys;
  const allKeys = catalog.map((item) => item.key);
  form.menu_keys = isAdminUser.value ? allKeys : (payload.menu_keys || []);
  await nextTick();
  if (menuTreeRef.value) {
    menuTreeRef.value.setCheckedKeys(form.menu_keys);
  }
  apiKeys.value = payload.api_keys || [];

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
    });
    ElMessage.success("权限已保存");
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "保存失败");
  } finally {
    saving.value = false;
  }
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
  await loadUsers();
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

</style>
