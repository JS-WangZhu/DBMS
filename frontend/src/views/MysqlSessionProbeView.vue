<template>
  <div class="session-probe-page">
    <el-card shadow="never">
      <template #header>
        <div class="header-row">
          <div>
            <div class="page-title">MySQL 会话探测</div>
            <div class="page-subtitle">点击开始后实时读取 information_schema.PROCESSLIST，探测连接最长保留 5 分钟</div>
          </div>
          <div class="probe-state">
            <el-tag :type="active ? 'success' : 'info'">{{ active ? '正在抓取' : '未开始' }}</el-tag>
            <span v-if="active" class="countdown">剩余 {{ countdownText }}</span>
          </div>
        </div>
      </template>

      <div class="filters">
        <el-select v-model="selectedBusinessLine" filterable clearable :disabled="active" placeholder="选择项目" @change="onBusinessLineChange">
          <el-option v-for="item in businessLines" :key="item" :label="item" :value="item" />
        </el-select>
        <el-select v-model="selectedEnvironment" filterable clearable :disabled="active" placeholder="选择环境" @change="onEnvironmentChange">
          <el-option v-for="item in environments" :key="item" :label="item" :value="item" />
        </el-select>
        <el-select v-model="selectedClusterId" filterable clearable :disabled="active" placeholder="检索集群名称" @change="syncInstanceSelection">
          <el-option v-for="item in filteredClusters" :key="item.id" :label="clusterOptionLabel(item)" :value="item.id" />
        </el-select>
        <el-select v-model="instanceId" filterable clearable placeholder="选择 MySQL 实例" :disabled="active" class="instance-select">
          <el-option
            v-for="item in filteredInstances"
            :key="item.id"
            :label="`${item.name} (${item.resolved_ip || item.host_input}:${item.port})`"
            :value="item.id"
          />
        </el-select>
        <el-button v-if="!active" type="primary" :loading="starting" :disabled="!instanceId" @click="startProbe">开始抓取</el-button>
        <el-button v-else type="danger" plain :loading="stopping" @click="stopProbe(true)">停止抓取</el-button>
        <el-button :disabled="!active" :loading="fetching" @click="() => fetchSessions()">立即刷新</el-button>
      </div>
    </el-card>

    <el-card shadow="never" v-loading="fetching" class="table-card">
      <template #header>
        <div class="table-header">
          <span>业务运行会话</span>
          <span class="summary">
            会话 {{ businessSessions.length }}，活跃 {{ activeSessionCount }}
            <template v-if="collectedAt">，采集于 {{ formatDateTime(collectedAt) }}</template>
          </span>
        </div>
      </template>

      <el-empty v-if="!active && !businessSessions.length" description="请选择实例并点击“开始抓取”" />
      <el-table
        v-else
        :key="tableRevision"
        :data="businessSessions"
        row-key="id"
        border
        stripe
        size="small"
        empty-text="当前没有可展示的业务会话"
      >
        <el-table-column prop="id" label="会话 ID" width="95" fixed="left" />
        <el-table-column prop="user" label="用户" min-width="110" show-overflow-tooltip />
        <el-table-column prop="host" label="客户端" min-width="170" show-overflow-tooltip />
        <el-table-column prop="database" label="数据库" min-width="120" show-overflow-tooltip>
          <template #default="scope">{{ scope.row.database || "-" }}</template>
        </el-table-column>
        <el-table-column prop="command" label="命令" width="105">
          <template #default="scope">
            <el-tag size="small" :type="commandTagType(scope.row.command)">{{ scope.row.command || "-" }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="time_seconds" label="持续时间" width="110" sortable>
          <template #default="scope">{{ formatDuration(scope.row.time_seconds) }}</template>
        </el-table-column>
        <el-table-column prop="state" label="状态" min-width="170" show-overflow-tooltip>
          <template #default="scope">{{ scope.row.state || "-" }}</template>
        </el-table-column>
        <el-table-column prop="sql" label="SQL" min-width="360" show-overflow-tooltip>
          <template #default="scope"><code class="sql-text">{{ scope.row.sql || "-" }}</code></template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="scope">
            <el-button link type="danger" :loading="killingId === scope.row.id" @click="confirmKill(scope.row)">Kill</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onDeactivated, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { listClusters } from "../api/modules/clusters";
import { listInstances } from "../api/modules/instances";
import {
  getMysqlProcesslist,
  killMysqlProcess,
  startMysqlSessionProbe,
  stopMysqlSessionProbe,
} from "../api/modules/mysql";

const clusters = ref([]);
const instances = ref([]);
const selectedBusinessLine = ref(null);
const selectedEnvironment = ref(null);
const selectedClusterId = ref(null);
const instanceId = ref(null);
const probeToken = ref("");
const expiresAt = ref(null);
const sessions = ref([]);
const hiddenKilledIds = ref(new Set());
const collectedAt = ref(null);
const remainingSeconds = ref(0);
const starting = ref(false);
const stopping = ref(false);
const fetching = ref(false);
const killingId = ref(null);
const tableRevision = ref(0);
let pollTimer = null;
let countdownTimer = null;
let refreshQueued = false;

const active = computed(() => Boolean(probeToken.value));
const businessLines = computed(() => [...new Set(clusters.value.map((item) => item.business_line || item.namespace).filter(Boolean))].sort());
const environments = computed(() => {
  const source = selectedBusinessLine.value
    ? clusters.value.filter((item) => (item.business_line || item.namespace) === selectedBusinessLine.value)
    : clusters.value;
  return [...new Set(source.map((item) => item.environment).filter(Boolean))].sort();
});
const filteredClusters = computed(() => clusters.value.filter((item) => {
  if (selectedBusinessLine.value && (item.business_line || item.namespace) !== selectedBusinessLine.value) return false;
  if (selectedEnvironment.value && item.environment !== selectedEnvironment.value) return false;
  return true;
}));
const filteredInstances = computed(() => {
  if (selectedClusterId.value) return instances.value.filter((item) => item.cluster_id === selectedClusterId.value);
  if (!selectedBusinessLine.value && !selectedEnvironment.value) return instances.value;
  const allowed = new Set(filteredClusters.value.map((item) => item.id));
  return instances.value.filter((item) => item.cluster_id && allowed.has(item.cluster_id));
});
const businessSessions = computed(() => sessions.value.filter(
  (item) => !item.is_probe_connection && !hiddenKilledIds.value.has(item.id),
));
const activeSessionCount = computed(() => businessSessions.value.filter((item) => String(item.command || "").toLowerCase() !== "sleep").length);
const countdownText = computed(() => {
  const minutes = Math.floor(remainingSeconds.value / 60);
  const seconds = remainingSeconds.value % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
});

function clusterOptionLabel(item) {
  return [item.business_line || item.namespace, item.environment, item.name].filter(Boolean).join("/") || item.name;
}

function syncInstanceSelection() {
  if (!filteredInstances.value.some((item) => item.id === instanceId.value)) {
    instanceId.value = filteredInstances.value[0]?.id || null;
  }
}

function onBusinessLineChange() {
  selectedEnvironment.value = null;
  selectedClusterId.value = null;
  syncInstanceSelection();
}

function onEnvironmentChange() {
  selectedClusterId.value = null;
  syncInstanceSelection();
}

function formatDuration(value) {
  const total = Math.max(0, Number(value) || 0);
  if (total < 60) return `${total}秒`;
  if (total < 3600) return `${Math.floor(total / 60)}分${total % 60}秒`;
  return `${Math.floor(total / 3600)}时${Math.floor((total % 3600) / 60)}分`;
}

function formatDateTime(value) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "-";
}

function commandTagType(command) {
  const value = String(command || "").toLowerCase();
  if (value === "query" || value === "execute") return "success";
  if (value === "sleep") return "info";
  if (value === "locked") return "danger";
  return "warning";
}

function clearTimers() {
  if (pollTimer) window.clearInterval(pollTimer);
  if (countdownTimer) window.clearInterval(countdownTimer);
  pollTimer = null;
  countdownTimer = null;
}

function clearProbeState() {
  clearTimers();
  probeToken.value = "";
  expiresAt.value = null;
  remainingSeconds.value = 0;
  sessions.value = [];
  hiddenKilledIds.value = new Set();
  refreshQueued = false;
  collectedAt.value = null;
}

function updateCountdown() {
  if (!expiresAt.value) return;
  remainingSeconds.value = Math.max(0, Math.ceil((new Date(expiresAt.value).getTime() - Date.now()) / 1000));
  if (remainingSeconds.value <= 0) {
    clearProbeState();
    ElMessage.warning("会话探测已达 5 分钟，连接已自动关闭");
  }
}

async function startProbe() {
  if (!instanceId.value || starting.value) return;
  starting.value = true;
  try {
    const response = await startMysqlSessionProbe(instanceId.value);
    const data = response.data?.data || {};
    probeToken.value = data.token || "";
    expiresAt.value = data.expires_at || null;
    updateCountdown();
    countdownTimer = window.setInterval(updateCountdown, 1000);
    pollTimer = window.setInterval(fetchSessions, 3000);
    await fetchSessions();
    ElMessage.success("会话抓取已开始");
  } catch (error) {
    clearProbeState();
    ElMessage.error(error.response?.data?.message || "启动会话探测失败");
  } finally {
    starting.value = false;
  }
}

async function fetchSessions(force = false) {
  const token = probeToken.value;
  if (!token) return;
  if (fetching.value) {
    if (force) refreshQueued = true;
    return;
  }
  fetching.value = true;
  try {
    const response = await getMysqlProcesslist(token);
    const data = response.data?.data || {};
    const nextSessions = data.sessions || [];
    const returnedIds = new Set(nextSessions.map((item) => item.id));
    hiddenKilledIds.value = new Set(
      [...hiddenKilledIds.value].filter((processId) => returnedIds.has(processId)),
    );
    sessions.value = nextSessions;
    collectedAt.value = data.collected_at || null;
    expiresAt.value = data.expires_at || expiresAt.value;
  } catch (error) {
    if ([403, 410, 502].includes(error.response?.status)) clearProbeState();
    ElMessage.error(error.response?.data?.message || "抓取 Processlist 失败");
  } finally {
    fetching.value = false;
    if (refreshQueued && probeToken.value) {
      refreshQueued = false;
      window.setTimeout(() => fetchSessions(), 0);
    }
  }
}

async function stopProbe(showMessage = false) {
  const token = probeToken.value;
  if (!token || stopping.value) return;
  stopping.value = true;
  clearProbeState();
  try {
    await stopMysqlSessionProbe(token);
    if (showMessage) ElMessage.success("会话探测连接已关闭");
  } catch (error) {
    if (showMessage && error.response?.status !== 410) {
      ElMessage.warning(error.response?.data?.message || "连接已在服务端关闭");
    }
  } finally {
    stopping.value = false;
  }
}

async function confirmKill(row) {
  try {
    await ElMessageBox.confirm(
      `确认 Kill 会话 ${row.id}（${row.user || "unknown"}@${row.host || "unknown"}）？该操作会中断当前连接及其事务。`,
      "Kill 会话二次确认",
      { type: "warning", confirmButtonText: "确认 Kill", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  killingId.value = row.id;
  try {
    await killMysqlProcess(probeToken.value, row.id);
    hiddenKilledIds.value = new Set([...hiddenKilledIds.value, row.id]);
    sessions.value = sessions.value.filter((item) => item.id !== row.id);
    tableRevision.value += 1;
    ElMessage.success(`会话 ${row.id} 已 Kill`);
    await fetchSessions(true);
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "Kill 会话失败");
  } finally {
    killingId.value = null;
  }
}

function closeOnPageHide() {
  const token = probeToken.value;
  if (!token) return;
  const authToken = localStorage.getItem("dbms_token") || "";
  fetch(`/api/v1/mysql/session-probes/${token}/stop`, {
    method: "POST",
    headers: authToken ? { Authorization: `Bearer ${authToken}` } : {},
    keepalive: true,
  }).catch(() => {});
  clearProbeState();
}

onMounted(async () => {
  window.addEventListener("pagehide", closeOnPageHide);
  try {
    const [clusterResponse, instanceResponse] = await Promise.all([listClusters("mysql"), listInstances("mysql")]);
    clusters.value = clusterResponse.data?.data || [];
    instances.value = instanceResponse.data?.data || [];
    syncInstanceSelection();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "MySQL 实例与集群加载失败");
  }
});
onDeactivated(() => stopProbe(false));
onBeforeUnmount(() => {
  window.removeEventListener("pagehide", closeOnPageHide);
  stopProbe(false);
});
</script>

<style scoped>
.session-probe-page { display: flex; flex-direction: column; gap: 16px; }
.header-row, .table-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.page-title { color: #303133; font-size: 20px; font-weight: 700; }
.page-subtitle { color: #909399; font-size: 13px; margin-top: 5px; }
.probe-state { display: flex; align-items: center; gap: 10px; white-space: nowrap; }
.countdown { color: #e6a23c; font-variant-numeric: tabular-nums; font-weight: 600; }
.filters { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; }
.filters > .el-select { width: 150px; }
.filters .instance-select { width: 280px; }
.table-card { min-height: 320px; }
.table-header { font-weight: 600; }
.summary { color: #909399; font-size: 13px; font-weight: 400; }
.sql-text { color: #303133; font-family: Consolas, "SFMono-Regular", monospace; white-space: nowrap; }
@media (max-width: 900px) {
  .header-row, .table-header { align-items: flex-start; flex-direction: column; }
  .filters > .el-select, .filters .instance-select { width: 100%; }
}
</style>
