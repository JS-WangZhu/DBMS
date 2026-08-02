<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>角色组管理</span>
          <div class="header-actions">
            <el-input v-model="keyword" clearable placeholder="搜索角色组" style="width: 220px" @keyup.enter="onSearch" />
            <el-button type="primary" @click="onSearch">搜索</el-button>
            <el-button type="primary" @click="openCreateDialog">新增角色组</el-button>
            <el-button @click="loadRoleGroups">刷新</el-button>
          </div>
        </div>
      </template>
      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column prop="description" label="描述" min-width="220" />
        <el-table-column prop="user_count" label="关联用户数" width="120" />
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEditDialog(row)">编辑</el-button>
            <el-button link type="danger" @click="removeRoleGroup(row)">删除</el-button>
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
          @current-change="loadRoleGroups"
          @size-change="onPageSizeChange"
        />
      </div>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="isEditing ? '编辑角色组' : '新增角色组'" width="920px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="名称">
          <el-input v-model="form.name" placeholder="请输入角色组名称" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" placeholder="可选" />
        </el-form-item>
        <el-form-item label="菜单权限">
          <el-tree
            ref="menuTreeRef"
            class="menu-tree"
            node-key="key"
            show-checkbox
            default-expand-all
            :data="menuTreeData"
            :props="{ label: 'label', children: 'children' }"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveRoleGroup">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { nextTick, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { createRoleGroup, deleteRoleGroup, listRoleGroups, updateRoleGroup } from "../api/modules/users";

const rows = ref([]);
const loading = ref(false);
const saving = ref(false);
const keyword = ref("");
const dialogVisible = ref(false);
const isEditing = ref(false);
const editingId = ref(null);
const menuCatalog = ref([]);
const menuTreeData = ref([]);
const menuLeafKeys = ref([]);
const menuTreeRef = ref(null);

const pager = reactive({
  page: 1,
  pageSize: 10,
  total: 0,
});

const form = reactive({
  name: "",
  description: "",
});

function buildMenuTree(catalog) {
  const leafMap = new Map((catalog || []).map((item) => [item.key, { key: item.key, label: item.label }]));
  const rootNodes = [
    { key: "dashboard", label: "总览", children: ["dashboard"] },
    { key: "service_manage", label: "服务管理", children: [
      { key: "mysql", label: "MySQL", children: ["mysql_instances", "mysql_instance_detail", "mysql_clusters", "mysql_connections", "mysql_session_probe"] },
      { key: "mongodb", label: "MongoDB", children: ["mongodb_instances", "mongodb_instance_detail", "mongodb_clusters", "mongodb_connections", "mongodb_session_probe"] },
      { key: "redis", label: "Redis", children: ["redis_instances", "redis_clusters"] },
      { key: "doris", label: "Doris", children: ["doris_instances", "doris_clusters"] },
    ] },
    { key: "inspection", label: "巡检管理", children: ["inspection_manage", "inspection_param_config"] },
    { key: "data_access", label: "数据访问", children: ["data_query", "data_change", "data_history"] },
    { key: "data_release", label: "数据发布", children: ["sql_release_apply", "sql_release_history"] },
    { key: "task_management", label: "任务管理", children: ["task_schedule", "task_results"] },
    { key: "backup", label: "备份管理", children: [
      { key: "backup_policies", label: "策略管理", children: ["backup_mysql_policies", "backup_postgresql_policies", "backup_mongo_policies"] },
      "backup_records",
      { key: "backup_config", label: "配置管理", children: ["backup_tool_configs", "backup_s3_storage", "backup_keys"] },
    ] },
    { key: "config", label: "配置管理", children: ["ai_model_config", "backup_agents", "ha_config", "instance_status_config", "data_query_op_config", "backup_notify_targets", "mcp_platform", "sso_config"] },
    { key: "users", label: "用户管理", children: ["users_info", "users_permissions", "users_role_groups", "users_data_sources"] },
  ];
  function convert(node) {
    if (typeof node === "string") return leafMap.get(node) || null;
    const children = (node.children || []).map(convert).filter(Boolean);
    if (!children.length) return null;
    return { key: node.key, label: node.label, children };
  }
  return { nodes: rootNodes.map(convert).filter(Boolean), leafKeys: Array.from(leafMap.keys()) };
}

function resetForm() {
  form.name = "";
  form.description = "";
}

async function loadRoleGroups() {
  loading.value = true;
  try {
    const { data } = await listRoleGroups({
      page: pager.page,
      page_size: pager.pageSize,
      keyword: keyword.value.trim() || undefined,
    });
    const result = data?.data || {};
    rows.value = result.items || [];
    pager.total = result.total || 0;
    if (!menuCatalog.value.length) {
      menuCatalog.value = result.menu_catalog || [];
      const tree = buildMenuTree(menuCatalog.value);
      menuTreeData.value = tree.nodes;
      menuLeafKeys.value = tree.leafKeys;
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载角色组失败");
  } finally {
    loading.value = false;
  }
}

async function onSearch() {
  pager.page = 1;
  await loadRoleGroups();
}

async function onPageSizeChange() {
  pager.page = 1;
  await loadRoleGroups();
}

async function openCreateDialog() {
  isEditing.value = false;
  editingId.value = null;
  resetForm();
  dialogVisible.value = true;
  await nextTick();
  menuTreeRef.value?.setCheckedKeys([]);
}

async function openEditDialog(row) {
  isEditing.value = true;
  editingId.value = row.id;
  form.name = row.name || "";
  form.description = row.description || "";
  dialogVisible.value = true;
  await nextTick();
  menuTreeRef.value?.setCheckedKeys(row.menu_keys || []);
}

async function saveRoleGroup() {
  if (!form.name.trim()) {
    ElMessage.warning("请输入名称");
    return;
  }
  saving.value = true;
  try {
    const checkedKeys = menuTreeRef.value ? menuTreeRef.value.getCheckedKeys(false) : [];
    const checkedLeafKeys = checkedKeys.filter((key) => menuLeafKeys.value.includes(key));
    const payload = {
      name: form.name.trim(),
      description: form.description.trim() || undefined,
      menu_keys: checkedLeafKeys,
    };
    if (isEditing.value && editingId.value) {
      await updateRoleGroup(editingId.value, payload);
      ElMessage.success("角色组已更新");
    } else {
      await createRoleGroup(payload);
      ElMessage.success("角色组已创建");
    }
    dialogVisible.value = false;
    await loadRoleGroups();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "保存失败");
  } finally {
    saving.value = false;
  }
}

async function removeRoleGroup(row) {
  try {
    await ElMessageBox.confirm(`确认删除角色组 ${row.name} 吗？`, "提示", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await deleteRoleGroup(row.id);
    ElMessage.success("删除成功");
    await loadRoleGroups();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.message || "删除失败");
    }
  }
}

onMounted(async () => {
  await loadRoleGroups();
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
  gap: 8px;
  align-items: center;
}

.pager-row {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}

</style>
