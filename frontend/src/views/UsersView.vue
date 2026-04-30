<template>
  <el-card>
    <template #header>
      <div class="header-row">
        <span>用户信息管理</span>
        <div class="actions">
          <el-input v-model="searchKeyword" clearable placeholder="搜索用户名" style="width: 220px" @keyup.enter="onSearch" />
          <el-button type="primary" @click="onSearch">搜索</el-button>
          <el-button type="primary" @click="openCreateDialog">新增用户</el-button>
          <el-button @click="loadUsers">刷新</el-button>
        </div>
      </div>
    </template>

    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="username" label="用户名" min-width="140" />
      <el-table-column
        prop="role"
        label="角色"
        width="110"
        :filters="roleFilters"
        :filter-method="filterByRole"
        :filter-multiple="false"
      />
      <el-table-column
        prop="status"
        label="状态"
        width="100"
        :filters="statusFilters"
        :filter-method="filterByStatus"
        :filter-multiple="false"
      />
      <el-table-column
        prop="auth_source"
        label="认证源"
        width="120"
        :filters="authSourceFilters"
        :filter-method="filterByAuthSource"
        :filter-multiple="false"
      />
      <el-table-column prop="role_group_names" label="角色组" min-width="180">
        <template #default="scope">
          <span>{{ (scope.row.role_group_names || []).join(", ") || "-" }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="320">
        <template #default="scope">
          <el-button link type="primary" @click="openEditDialog(scope.row)">编辑</el-button>
          <el-button
            link
            type="warning"
            :disabled="isCurrentUser(scope.row)"
            @click="toggleStatus(scope.row)"
          >
            {{ scope.row.status === "active" ? "禁用" : "启用" }}
          </el-button>
          <el-button
            link
            type="danger"
            :disabled="isCurrentUser(scope.row)"
            @click="removeUser(scope.row)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>
    <div class="pager-row">
      <el-pagination
        v-model:current-page="pager.page"
        v-model:page-size="pager.pageSize"
        :page-sizes="[10, 20, 50, 100]"
        layout="total, sizes, prev, pager, next, jumper"
        :total="pager.total"
        @current-change="loadUsers"
        @size-change="onPageSizeChange"
      />
    </div>
  </el-card>

  <el-dialog v-model="createVisible" title="新增用户" width="620px">
    <el-form :model="createForm" label-width="110px">
      <el-form-item label="用户名">
        <el-input v-model="createForm.username" placeholder="请输入用户名" />
      </el-form-item>
      <el-form-item label="角色">
        <el-select v-model="createForm.role" style="width: 100%">
          <el-option label="普通用户" value="user" />
          <el-option label="管理员" value="admin" />
          <el-option label="API用户" value="api" />
        </el-select>
      </el-form-item>
      <el-form-item label="状态">
        <el-select v-model="createForm.status" style="width: 100%">
          <el-option label="启用" value="active" />
          <el-option label="禁用" value="disabled" />
        </el-select>
      </el-form-item>
      <el-form-item label="角色组">
        <el-select v-model="createForm.role_group_ids" multiple filterable clearable style="width: 100%">
          <el-option v-for="group in roleGroupOptions" :key="group.id" :label="group.name" :value="group.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="密码">
        <el-input v-model="createForm.password" type="text" placeholder="至少8位" />
      </el-form-item>
      <el-form-item label="快捷操作">
        <div class="quick-actions">
          <el-button @click="generateCreatePassword">生成随机密码</el-button>
          <el-button @click="copyCreateUserInfo">复制用户信息</el-button>
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="createVisible = false">取消</el-button>
      <el-button type="primary" :loading="creating" @click="onCreateUser">创建</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="editVisible" title="编辑用户" width="620px">
    <el-form :model="editForm" label-width="110px">
      <el-form-item label="用户名">
        <el-input v-model="editForm.username" placeholder="请输入用户名" />
      </el-form-item>
      <el-form-item label="角色">
        <el-select v-model="editForm.role" style="width: 100%">
          <el-option label="普通用户" value="user" />
          <el-option label="管理员" value="admin" />
          <el-option label="API用户" value="api" />
        </el-select>
      </el-form-item>
      <el-form-item label="状态">
        <el-select v-model="editForm.status" style="width: 100%" :disabled="isEditingCurrentUser">
          <el-option label="启用" value="active" />
          <el-option label="禁用" value="disabled" />
        </el-select>
      </el-form-item>
      <el-form-item label="角色组">
        <el-select v-model="editForm.role_group_ids" multiple filterable clearable style="width: 100%">
          <el-option v-for="group in roleGroupOptions" :key="group.id" :label="group.name" :value="group.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="新密码">
        <el-input v-model="editForm.password" type="text" placeholder="留空表示不修改" />
      </el-form-item>
      <el-form-item label="快捷操作">
        <div class="quick-actions">
          <el-button @click="generateEditPassword">生成随机密码</el-button>
          <el-button @click="copyEditUserInfo">复制用户信息</el-button>
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="editVisible = false">取消</el-button>
      <el-button type="primary" :loading="updating" @click="onUpdateUser">保存</el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { createUser, deleteUser, listRoleGroupOptions, listUsers, updateUser } from "../api/modules/users";

const rows = ref([]);
const loading = ref(false);
const searchKeyword = ref("");
const roleGroupOptions = ref([]);
const pager = reactive({
  page: 1,
  pageSize: 20,
  total: 0,
});

const createVisible = ref(false);
const creating = ref(false);
const editVisible = ref(false);
const updating = ref(false);

const createForm = reactive({
  username: "",
  role: "user",
  status: "active",
  role_group_ids: [],
  password: "",
});

const editForm = reactive({
  id: null,
  username: "",
  role: "user",
  status: "active",
  role_group_ids: [],
  password: "",
});

const currentUser = computed(() => {
  try {
    return JSON.parse(localStorage.getItem("dbms_user") || "{}");
  } catch {
    return {};
  }
});

const isEditingCurrentUser = computed(() => editForm.id && Number(editForm.id) === Number(currentUser.value.id));

const roleFilters = computed(() => {
  const options = [];
  const seen = new Set();
  let hasEmpty = false;
  rows.value.forEach((row) => {
    const value = row.role;
    if (value === null || value === undefined || value === "") {
      hasEmpty = true;
      return;
    }
    if (seen.has(value)) {
      return;
    }
    seen.add(value);
    let label = "普通用户";
    if (value === "admin") label = "管理员";
    if (value === "api") label = "API用户";
    options.push({ text: label, value });
  });
  if (hasEmpty) {
    options.unshift({ text: "未设置", value: "__empty__" });
  }
  return options;
});

const statusFilters = computed(() => {
  const options = [];
  const seen = new Set();
  let hasEmpty = false;
  rows.value.forEach((row) => {
    const value = row.status;
    if (value === null || value === undefined || value === "") {
      hasEmpty = true;
      return;
    }
    if (seen.has(value)) {
      return;
    }
    seen.add(value);
    options.push({ text: value === "active" ? "启用" : "禁用", value });
  });
  if (hasEmpty) {
    options.unshift({ text: "未知", value: "__empty__" });
  }
  return options;
});

const authSourceFilters = computed(() => {
  const options = [];
  const seen = new Set();
  let hasEmpty = false;
  rows.value.forEach((row) => {
    const value = row.auth_source;
    if (value === null || value === undefined || value === "") {
      hasEmpty = true;
      return;
    }
    if (seen.has(value)) {
      return;
    }
    seen.add(value);
    options.push({ text: String(value), value });
  });
  if (hasEmpty) {
    options.unshift({ text: "未设置", value: "__empty__" });
  }
  return options;
});

function filterByRole(value, row) {
  if (value === "__empty__") {
    return row.role === null || row.role === undefined || row.role === "";
  }
  return row.role === value;
}

function filterByStatus(value, row) {
  if (value === "__empty__") {
    return row.status === null || row.status === undefined || row.status === "";
  }
  return row.status === value;
}

function filterByAuthSource(value, row) {
  if (value === "__empty__") {
    return row.auth_source === null || row.auth_source === undefined || row.auth_source === "";
  }
  return row.auth_source === value;
}

function isCurrentUser(row) {
  return Number(row.id) === Number(currentUser.value.id);
}

function resetCreateForm() {
  createForm.username = "";
  createForm.role = "user";
  createForm.status = "active";
  createForm.role_group_ids = [];
  createForm.password = "";
}

function resetEditForm() {
  editForm.id = null;
  editForm.username = "";
  editForm.role = "user";
  editForm.status = "active";
  editForm.role_group_ids = [];
  editForm.password = "";
}

function openCreateDialog() {
  resetCreateForm();
  createVisible.value = true;
}

function openEditDialog(row) {
  editForm.id = row.id;
  editForm.username = row.username;
  editForm.role = row.role;
  editForm.status = row.status;
  editForm.role_group_ids = (row.role_group_ids || []).slice();
  editForm.password = "";
  editVisible.value = true;
}

function randomPassword(length = 14) {
  const chars = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789!@#$%^&*";
  const bytes = new Uint32Array(length);
  window.crypto.getRandomValues(bytes);
  let out = "";
  for (let i = 0; i < length; i += 1) {
    out += chars[bytes[i] % chars.length];
  }
  return out;
}

function generateCreatePassword() {
  createForm.password = randomPassword();
}

function generateEditPassword() {
  editForm.password = randomPassword();
}

function buildUserInfoText(username, password, role, status) {
  return `username: ${username}\npassword: ${password}\nrole: ${role}\nstatus: ${status}`;
}

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.style.position = "fixed";
  textarea.style.opacity = "0";
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  document.execCommand("copy");
  document.body.removeChild(textarea);
}

async function copyCreateUserInfo() {
  if (!createForm.username || !createForm.password) {
    ElMessage.warning("请先填写用户名和密码");
    return;
  }

  try {
    await copyText(buildUserInfoText(createForm.username, createForm.password, createForm.role, createForm.status));
    ElMessage.success("用户信息已复制");
  } catch {
    ElMessage.error("复制失败，请检查浏览器权限");
  }
}

async function copyEditUserInfo() {
  if (!editForm.username || !editForm.password) {
    ElMessage.warning("请先填写用户名和新密码");
    return;
  }

  try {
    await copyText(buildUserInfoText(editForm.username, editForm.password, editForm.role, editForm.status));
    ElMessage.success("用户信息已复制");
  } catch {
    ElMessage.error("复制失败，请检查浏览器权限");
  }
}

async function loadUsers() {
  loading.value = true;
  try {
    const { data } = await listUsers({
      page: pager.page,
      page_size: pager.pageSize,
      keyword: searchKeyword.value.trim() || undefined,
    });
    const result = data.data || {};
    rows.value = result.items || [];
    pager.total = result.total || 0;
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载用户失败，需要管理员权限");
  } finally {
    loading.value = false;
  }
}

async function onCreateUser() {
  if (!createForm.username || !createForm.password) {
    ElMessage.warning("请填写用户名和密码");
    return;
  }
  if (createForm.password.length < 8) {
    ElMessage.warning("密码至少8位");
    return;
  }

  creating.value = true;
  try {
    await createUser({
      username: createForm.username,
      password: createForm.password,
      role: createForm.role,
      status: createForm.status,
      role_group_ids: createForm.role_group_ids,
    });
    ElMessage.success("用户创建成功");
    createVisible.value = false;
    await loadUsers();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "创建用户失败");
  } finally {
    creating.value = false;
  }
}

async function onUpdateUser() {
  if (!editForm.id) {
    return;
  }
  if (!editForm.username) {
    ElMessage.warning("请输入用户名");
    return;
  }
  if (editForm.password && editForm.password.length < 8) {
    ElMessage.warning("密码至少8位");
    return;
  }

  updating.value = true;
  try {
    const payload = {
      username: editForm.username,
      role: editForm.role,
      status: editForm.status,
      role_group_ids: editForm.role_group_ids,
    };
    if (editForm.password) {
      payload.password = editForm.password;
    }

    await updateUser(editForm.id, payload);
    ElMessage.success("用户更新成功");
    editVisible.value = false;
    await loadUsers();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "更新用户失败");
  } finally {
    updating.value = false;
  }
}

async function toggleStatus(row) {
  try {
    const nextStatus = row.status === "active" ? "disabled" : "active";
    await updateUser(row.id, { status: nextStatus });
    ElMessage.success("状态已更新");
    await loadUsers();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "更新失败");
  }
}

async function removeUser(row) {
  try {
    await ElMessageBox.confirm(`确认删除用户 ${row.username} 吗`, "提示", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });

    await deleteUser(row.id);
    ElMessage.success("用户已删除");
    await loadUsers();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.message || "删除失败");
    }
  }
}

async function loadRoleGroupOptions() {
  try {
    const { data } = await listRoleGroupOptions();
    roleGroupOptions.value = data.data || [];
  } catch {
    roleGroupOptions.value = [];
  }
}

async function onSearch() {
  pager.page = 1;
  await loadUsers();
}

async function onPageSizeChange() {
  pager.page = 1;
  await loadUsers();
}

onMounted(() => {
  loadUsers();
  loadRoleGroupOptions();
});
</script>

<style scoped>
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.actions {
  display: inline-flex;
  gap: 8px;
}

.quick-actions {
  display: inline-flex;
  gap: 8px;
}

.pager-row {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}
</style>
