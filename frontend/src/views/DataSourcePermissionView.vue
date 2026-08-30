<template>
  <div class="page">
    <el-card>
      <template #header><div class="header"><span>数据源权限管理</span><el-button @click="loadOverview">刷新</el-button></div></template>
      <el-tabs v-model="activeTab">
        <el-tab-pane label="用户授权" name="users">
          <el-form label-width="100px">
            <el-form-item label="用户">
              <el-select v-model="selectedUserId" filterable style="width: 320px" @change="loadUserPermissions"><el-option v-for="item in users" :key="item.id" :value="item.id" :label="`${item.display_name || item.username} (${item.role})`" /></el-select>
            </el-form-item>
            <el-form-item label="数据源组">
              <el-select v-model="selectedGroupIds" multiple filterable :disabled="isAdmin" style="width: 100%" placeholder="加入一个或多个数据源组"><el-option v-for="item in groups" :key="item.id" :value="item.id" :label="item.name" /></el-select>
            </el-form-item>
          </el-form>
          <el-alert title="有效权限为“直接授权 + 数据源组 + 兼容的历史角色组授权”的并集；实例查看仅开放对应集群的实例与已采集状态，普通用户为只读访问，页面入口仍需单独授予对应实例管理菜单权限。" type="info" :closable="false" show-icon />
          <el-alert title="可按用户、数据源设置直接权限的持有截止日期和时间（北京时间）；留空表示长期持有。申请审批产生的授权会带入申请人选择的截止日，到期自动回收。" type="info" :closable="false" show-icon style="margin-top: 12px" />
          <permission-table v-model="directPermissions" :clusters="clusters" :effective="effectiveMap" :disabled="isAdmin" show-expiration />
          <div class="actions"><el-button type="primary" :disabled="!selectedUserId || isAdmin" :loading="saving" @click="saveUser">保存用户数据源权限</el-button></div>
        </el-tab-pane>
        <el-tab-pane label="数据源组配置" name="groups">
          <div class="group-toolbar"><el-button type="primary" @click="openGroup()">新建数据源组</el-button></div>
          <el-table :data="groups" stripe>
            <el-table-column prop="name" label="组名" min-width="180" /><el-table-column prop="description" label="说明" min-width="260" /><el-table-column label="数据源数" width="110"><template #default="scope">{{ scope.row.permissions.length }}</template></el-table-column><el-table-column label="用户数" width="100"><template #default="scope">{{ scope.row.user_ids.length }}</template></el-table-column>
            <el-table-column label="操作" width="150"><template #default="scope"><el-button link type="primary" @click="openGroup(scope.row)">编辑</el-button><el-button link type="danger" @click="removeGroup(scope.row)">删除</el-button></template></el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>
    <el-dialog v-model="groupDialog" :title="editingGroupId ? '编辑数据源组' : '新建数据源组'" width="75%">
      <el-form label-width="80px"><el-form-item label="组名"><el-input v-model="groupForm.name" /></el-form-item><el-form-item label="说明"><el-input v-model="groupForm.description" /></el-form-item></el-form>
      <permission-table v-model="groupPermissions" :clusters="clusters" />
      <template #footer><el-button @click="groupDialog = false">取消</el-button><el-button type="primary" :loading="groupSaving" @click="saveGroup">保存</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { createDataSourceGroup, deleteDataSourceGroup, getDataSourcePermissionOverview, getUserDataSourcePermissions, updateDataSourceGroup, updateUserDataSourcePermissions } from "../api/modules/dataSourcePermissions";
import PermissionTable from "../components/DataSourcePermissionTable.vue";

const activeTab = ref("users"), users = ref([]), clusters = ref([]), groups = ref([]), selectedUserId = ref(null), selectedGroupIds = ref([]), directPermissions = ref([]), effectiveMap = ref({}), saving = ref(false);
const groupDialog = ref(false), editingGroupId = ref(null), groupPermissions = ref([]), groupSaving = ref(false), groupForm = reactive({ name: "", description: "" });
const selectedUser = computed(() => users.value.find((item) => item.id === selectedUserId.value));
const isAdmin = computed(() => selectedUser.value?.role === "admin");
const emptyPermissions = (source = []) => clusters.value.map((cluster) => { const found = source.find((item) => item.cluster_id === cluster.id); return { cluster_id: cluster.id, can_query: !!found?.can_query, can_change: !!found?.can_change, can_execute: !!found?.can_execute, can_view_instance: !!found?.can_view_instance, expires_at: found?.expires_at || null }; });
async function loadOverview() { const { data } = await getDataSourcePermissionOverview(); users.value = data.data?.users || []; clusters.value = data.data?.clusters || []; groups.value = data.data?.groups || []; if (!selectedUserId.value && users.value.length) selectedUserId.value = users.value[0].id; if (selectedUserId.value) await loadUserPermissions(); }
async function loadUserPermissions() { if (!selectedUserId.value) return; const { data } = await getUserDataSourcePermissions(selectedUserId.value); const payload = data.data || {}; selectedGroupIds.value = payload.group_ids || []; directPermissions.value = emptyPermissions(payload.direct_permissions || []); effectiveMap.value = Object.fromEntries((payload.effective_permissions || []).map((item) => [item.cluster_id, item])); }
async function saveUser() { saving.value = true; try { await updateUserDataSourcePermissions(selectedUserId.value, { group_ids: selectedGroupIds.value, direct_permissions: directPermissions.value }); ElMessage.success("数据源权限已保存"); await loadUserPermissions(); } finally { saving.value = false; } }
function openGroup(row) { editingGroupId.value = row?.id || null; groupForm.name = row?.name || ""; groupForm.description = row?.description || ""; groupPermissions.value = emptyPermissions(row?.permissions || []); groupDialog.value = true; }
async function saveGroup() { if (!groupForm.name.trim()) return ElMessage.warning("请输入组名"); groupSaving.value = true; try { const payload = { name: groupForm.name, description: groupForm.description, permissions: groupPermissions.value }; if (editingGroupId.value) await updateDataSourceGroup(editingGroupId.value, payload); else await createDataSourceGroup(payload); ElMessage.success("数据源组已保存"); groupDialog.value = false; await loadOverview(); } finally { groupSaving.value = false; } }
async function removeGroup(row) { await ElMessageBox.confirm(`删除数据源组“${row.name}”并解除用户关联？`, "删除确认", { type: "warning" }); await deleteDataSourceGroup(row.id); ElMessage.success("已删除"); await loadOverview(); }
onMounted(loadOverview);
</script>

<style scoped>
.header, .actions, .group-toolbar { display: flex; justify-content: space-between; align-items: center; }
.actions { justify-content: flex-end; margin-top: 16px; }
.group-toolbar { justify-content: flex-end; margin-bottom: 12px; }
</style>
