<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>MySQL 集群管理</span>
          <div class="actions">
            <el-button type="primary" @click="openClusterDialog">新建集群</el-button>
            <el-button @click="loadClusters">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table :data="clusters" v-loading="clusterLoading" stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="集群名" min-width="180" />
        <el-table-column prop="description" label="描述" min-width="220" />
        <el-table-column prop="created_at" label="创建时间" min-width="180">
          <template #default="scope">
            {{ formatBeijingTime(scope.row.created_at) }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card>
      <template #header>
        <div class="header-row">
          <span>MySQL 实例管理</span>
          <div class="actions">
            <el-button type="primary" @click="openInstanceDialog">新增MySQL实例</el-button>
            <el-button @click="reloadInstances">刷新实例</el-button>
            <el-button @click="refreshReplicationStatus">刷新主从状态</el-button>
          </div>
        </div>
      </template>

      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="实例名" min-width="140" />
        <el-table-column label="所属集群" min-width="140">
          <template #default="scope">
            {{ resolveClusterName(scope.row.cluster_id) }}
          </template>
        </el-table-column>
        <el-table-column prop="host_input" label="地址" min-width="180" />
        <el-table-column prop="port" label="端口" width="90" />
        <el-table-column label="主从角色" width="120">
          <template #default="scope">
            <el-tag :type="roleTagType(replicationFor(scope.row).replication_role)">
              {{ roleText(replicationFor(scope.row).replication_role) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="复制延迟(s)" width="120">
          <template #default="scope">
            {{ replicationFor(scope.row).seconds_behind_master ?? "-" }}
          </template>
        </el-table-column>
        <el-table-column label="IO/SQL线程" min-width="130">
          <template #default="scope">
            {{ threadStateText(replicationFor(scope.row)) }}
          </template>
        </el-table-column>
        <el-table-column label="定制操作" width="150">
          <template #default="scope">
            <el-button link type="primary" @click="viewReplication(scope.row)">查看详情</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="clusterDialogVisible" title="新建MySQL集群" width="520px">
      <el-form :model="clusterForm" label-width="95px">
        <el-form-item label="集群名称"><el-input v-model="clusterForm.name" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="clusterForm.description" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="clusterDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="clusterSaving" @click="onCreateCluster">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="instanceDialogVisible" title="新增MySQL实例" width="620px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="实例名"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="所属集群">
          <el-select v-model="form.cluster_id" clearable style="width: 100%" placeholder="可选：选择已录入集群">
            <el-option v-for="item in clusters" :key="item.id" :label="item.name" :value="item.id" />
          </el-select>
          <div class="hint">主从状态将从数据库实时读取，无需在录入时填写。</div>
        </el-form-item>
        <el-form-item label="地址"><el-input v-model="form.host_input" placeholder="IP或域名" /></el-form-item>
        <el-form-item label="端口"><el-input-number v-model="form.port" :min="1" :max="65535" style="width: 100%" /></el-form-item>
        <el-form-item label="用户名"><el-input v-model="form.username" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="form.password" type="password" show-password /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="instanceDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onCreateInstance">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
  import { ElMessage, ElMessageBox } from "element-plus";

  import { createCluster, listClusters } from "../api/modules/clusters";
  import { createMysqlInstance, listMysqlInstances, mysqlReplication } from "../api/modules/mysql";
  import { formatBeijingTime } from "../utils/time";

const loading = ref(false);
const saving = ref(false);
const rows = ref([]);

const clusterLoading = ref(false);
const clusters = ref([]);
const clusterDialogVisible = ref(false);
const clusterSaving = ref(false);

const instanceDialogVisible = ref(false);
const replicationStatusMap = reactive({});

const clusterForm = reactive({
  name: "",
  description: "",
});

const form = reactive({
  name: "",
  cluster_id: null,
  host_input: "",
  port: 3306,
  username: "",
  password: "",
});

function resetClusterForm() {
  clusterForm.name = "";
  clusterForm.description = "";
}

function resetInstanceForm() {
  form.name = "";
  form.cluster_id = null;
  form.host_input = "";
  form.port = 3306;
  form.username = "";
  form.password = "";
}

function openClusterDialog() {
  resetClusterForm();
  clusterDialogVisible.value = true;
}

async function openInstanceDialog() {
  if (!clusters.value.length) {
    await loadClusters();
  }
  resetInstanceForm();
  instanceDialogVisible.value = true;
}

function resolveClusterName(clusterId) {
  if (!clusterId) {
    return "-";
  }
  const row = clusters.value.find((item) => item.id === clusterId);
  return row?.name || `#${clusterId}`;
}

function replicationFor(row) {
  return replicationStatusMap[row.id] || {};
}

function roleTagType(role) {
  if (role === "mgr_primary") return "success";
  if (role === "mgr_secondary") return "warning";
  if (role === "master_slave" || role === "dual") {
    return "warning";
  }
  if (role === "master") {
    return "success";
  }
  if (role === "slave") {
    return "warning";
  }
  if (role === "read_only") {
    return "info";
  }
  return "danger";
}

function roleText(role) {
  if (role === "mgr_primary") return "MGR-主";
  if (role === "mgr_secondary") return "MGR-从";
  if (role === "master_slave" || role === "dual") {
    return "主/从";
  }
  if (role === "master") {
    return "主库";
  }
  if (role === "slave") {
    return "从库";
  }
  if (role === "read_only") {
    return "只读";
  }
  return "未知";
}

function flagText(value) {
  if (value === true) {
    return "Y";
  }
  if (value === false) {
    return "N";
  }
  return "-";
}

function threadStateText(status) {
  return `${flagText(status.replica_io_running)}/${flagText(status.replica_sql_running)}`;
}

async function loadClusters() {
  clusterLoading.value = true;
  try {
    const { data } = await listClusters("mysql");
    clusters.value = data.data || [];
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载集群失败");
  } finally {
    clusterLoading.value = false;
  }
}

async function loadInstances() {
  loading.value = true;
  try {
    const { data } = await listMysqlInstances();
    rows.value = data.data || [];
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载实例失败");
  } finally {
    loading.value = false;
  }
}

async function refreshReplicationStatus() {
  if (!rows.value.length) {
    return;
  }

  await Promise.allSettled(
    rows.value.map(async (row) => {
      const { data } = await mysqlReplication(row.id, true);
      replicationStatusMap[row.id] = data.data || {};
    }),
  );
}

async function onCreateCluster() {
  if (!clusterForm.name) {
    ElMessage.warning("请填写集群名称");
    return;
  }

  clusterSaving.value = true;
  try {
    await createCluster({
      name: clusterForm.name,
      db_type: "mysql",
      description: clusterForm.description,
    });
    ElMessage.success("集群创建成功");
    clusterDialogVisible.value = false;
    await loadClusters();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "创建集群失败");
  } finally {
    clusterSaving.value = false;
  }
}

async function onCreateInstance() {
  if (!form.name || !form.host_input || !form.port) {
    ElMessage.warning("请填写实例名、地址和端口");
    return;
  }

  saving.value = true;
  try {
    const payload = {
      name: form.name,
      host_input: form.host_input,
      port: form.port,
      username: form.username,
      password: form.password,
      cluster_id: form.cluster_id,
    };

    if (!payload.cluster_id) {
      delete payload.cluster_id;
    }

    await createMysqlInstance(payload);
    ElMessage.success("实例创建成功");
    instanceDialogVisible.value = false;
    await reloadInstances();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "创建实例失败");
  } finally {
    saving.value = false;
  }
}

async function viewReplication(row) {
  try {
    const { data } = await mysqlReplication(row.id, true);
    replicationStatusMap[row.id] = data.data || {};
    await ElMessageBox.alert(`<pre style='white-space:pre-wrap'>${JSON.stringify(data.data, null, 2)}</pre>`, "主从详情", {
      dangerouslyUseHTMLString: true,
    });
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "获取主从状态失败");
  }
}

async function reloadInstances() {
  await loadInstances();
  await refreshReplicationStatus();
}

onMounted(async () => {
  await Promise.all([loadClusters(), loadInstances()]);
  await refreshReplicationStatus();
});
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.actions {
  display: inline-flex;
  gap: 8px;
}

.hint {
  margin-top: 4px;
  color: #8a96a8;
  font-size: 12px;
}
</style>
