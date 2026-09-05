<template>
  <div class="session-probe-page">
    <el-card shadow="never">
      <template #header>
        <div class="header-row">
          <div><div class="page-title">PostgreSQL 会话探测</div><div class="page-subtitle">点击开始后实时读取 pg_stat_activity，探测连接最长保留 5 分钟</div></div>
          <div class="probe-state"><el-tag :type="active ? 'success' : 'info'">{{ active ? '正在抓取' : '未开始' }}</el-tag><span v-if="active" class="countdown">剩余 {{ countdownText }}</span></div>
        </div>
      </template>
      <div class="filters">
        <el-select v-model="businessLine" filterable clearable :disabled="active" placeholder="选择项目" @change="resetCluster"><el-option v-for="item in businessLines" :key="item" :label="item" :value="item" /></el-select>
        <el-select v-model="environment" filterable clearable :disabled="active" placeholder="选择环境" @change="resetCluster"><el-option v-for="item in environments" :key="item" :label="item" :value="item" /></el-select>
        <el-select v-model="clusterId" filterable clearable :disabled="active" placeholder="检索集群名称" @change="syncInstance"><el-option v-for="item in filteredClusters" :key="item.id" :label="clusterLabel(item)" :value="item.id" /></el-select>
        <el-select v-model="instanceId" filterable clearable :disabled="active" class="instance-select" placeholder="选择 PostgreSQL 实例"><el-option v-for="item in filteredInstances" :key="item.id" :label="`${item.name} (${item.resolved_ip || item.host_input}:${item.port})`" :value="item.id" /></el-select>
        <el-button v-if="!active" type="primary" :loading="starting" :disabled="!instanceId" @click="startProbe">开始抓取</el-button>
        <el-button v-else type="danger" plain :loading="stopping" @click="stopProbe(true)">停止抓取</el-button>
        <el-button :disabled="!active" :loading="fetching" @click="fetchSessions(true)">立即刷新</el-button>
      </div>
    </el-card>
    <el-card v-loading="fetching" shadow="never" class="table-card">
      <template #header><div class="table-header"><span>业务运行会话</span><span class="summary">会话 {{ visibleSessions.length }}，活跃 {{ activeCount }}<template v-if="collectedAt">，采集于 {{ dateTime(collectedAt) }}</template></span></div></template>
      <el-empty v-if="!active && !visibleSessions.length" description="请选择实例并点击“开始抓取”" />
      <el-table v-else :key="tableRevision" :data="visibleSessions" row-key="id" border stripe size="small" empty-text="当前没有可展示的业务会话">
        <el-table-column prop="id" label="PID" width="90" fixed="left" />
        <el-table-column prop="user" label="用户" min-width="110" show-overflow-tooltip><template #default="{ row }">{{ row.user || '-' }}</template></el-table-column>
        <el-table-column prop="database" label="数据库" min-width="120" show-overflow-tooltip><template #default="{ row }">{{ row.database || '-' }}</template></el-table-column>
        <el-table-column prop="client" label="客户端" min-width="135" show-overflow-tooltip><template #default="{ row }">{{ row.client || '本地' }}</template></el-table-column>
        <el-table-column prop="application_name" label="应用" min-width="130" show-overflow-tooltip><template #default="{ row }">{{ row.application_name || '-' }}</template></el-table-column>
        <el-table-column label="状态" width="110"><template #default="{ row }"><el-tag size="small" :type="stateTag(row.state)">{{ stateText(row.state) }}</el-tag></template></el-table-column>
        <el-table-column label="等待事件" min-width="150" show-overflow-tooltip><template #default="{ row }">{{ waitEvent(row) }}</template></el-table-column>
        <el-table-column prop="time_seconds" label="持续时间" width="110" sortable><template #default="{ row }">{{ duration(row.time_seconds) }}</template></el-table-column>
        <el-table-column prop="sql" label="SQL" min-width="380" show-overflow-tooltip><template #default="{ row }"><code class="sql-text">{{ row.sql || '-' }}</code></template></el-table-column>
        <el-table-column label="操作" width="90" fixed="right"><template #default="{ row }"><el-button v-if="canKill" link type="danger" :loading="killingId === row.id" @click="confirmKill(row)">Kill</el-button><span v-else class="readonly-text">只读</span></template></el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onDeactivated, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { listClusters } from "../api/modules/clusters";
import { listInstances } from "../api/modules/instances";
import { getPostgreSQLSessions, killPostgreSQLSession, startPostgreSQLSessionProbe, stopPostgreSQLSessionProbe } from "../api/modules/postgresql";

const clusters = ref([]), instances = ref([]), businessLine = ref(null), environment = ref(null), clusterId = ref(null), instanceId = ref(null), probeToken = ref(""), expiresAt = ref(null), sessions = ref([]), hiddenIds = ref(new Set()), collectedAt = ref(null), remainingSeconds = ref(0), starting = ref(false), stopping = ref(false), fetching = ref(false), killingId = ref(null), tableRevision = ref(0), canKill = ref(false);
let pollTimer = null, countdownTimer = null, refreshQueued = false;
const active = computed(() => Boolean(probeToken.value));
const businessLines = computed(() => [...new Set(clusters.value.map((item) => item.business_line || item.namespace).filter(Boolean))].sort());
const environments = computed(() => [...new Set(clusters.value.filter((item) => !businessLine.value || (item.business_line || item.namespace) === businessLine.value).map((item) => item.environment).filter(Boolean))].sort());
const filteredClusters = computed(() => clusters.value.filter((item) => (!businessLine.value || (item.business_line || item.namespace) === businessLine.value) && (!environment.value || item.environment === environment.value)));
const filteredInstances = computed(() => { if (clusterId.value) return instances.value.filter((item) => item.cluster_id === clusterId.value); if (!businessLine.value && !environment.value) return instances.value; const ids = new Set(filteredClusters.value.map((item) => item.id)); return instances.value.filter((item) => item.cluster_id && ids.has(item.cluster_id)); });
const visibleSessions = computed(() => sessions.value.filter((item) => !item.is_probe_connection && !hiddenIds.value.has(item.id)));
const activeCount = computed(() => visibleSessions.value.filter((item) => String(item.state || "").toLowerCase() === "active").length);
const countdownText = computed(() => `${String(Math.floor(remainingSeconds.value / 60)).padStart(2, "0")}:${String(remainingSeconds.value % 60).padStart(2, "0")}`);
function clusterLabel(item) { return [item.business_line || item.namespace, item.environment, item.name].filter(Boolean).join("/") || item.name; }
function syncInstance() { if (!filteredInstances.value.some((item) => item.id === instanceId.value)) instanceId.value = filteredInstances.value[0]?.id || null; }
function resetCluster() { environment.value = businessLine.value ? environment.value : null; clusterId.value = null; syncInstance(); }
function duration(value) { const total = Math.max(0, Number(value) || 0); return total < 60 ? `${total}秒` : total < 3600 ? `${Math.floor(total / 60)}分${total % 60}秒` : `${Math.floor(total / 3600)}时${Math.floor((total % 3600) / 60)}分`; }
function dateTime(value) { return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "-"; }
function stateText(value) { return ({ active: "执行中", idle: "空闲", "idle in transaction": "事务空闲", disabled: "禁用" })[String(value || "").toLowerCase()] || value || "未知"; }
function stateTag(value) { const state = String(value || "").toLowerCase(); return state === "active" ? "success" : state.includes("transaction") ? "warning" : "info"; }
function waitEvent(row) { return [row.wait_event_type, row.wait_event].filter(Boolean).join(" / ") || "-"; }
function clearTimers() { if (pollTimer) window.clearInterval(pollTimer); if (countdownTimer) window.clearInterval(countdownTimer); pollTimer = null; countdownTimer = null; }
function clearState(keepOutput = false) { clearTimers(); probeToken.value = ""; expiresAt.value = null; remainingSeconds.value = 0; canKill.value = false; refreshQueued = false; if (!keepOutput) { sessions.value = []; hiddenIds.value = new Set(); collectedAt.value = null; } }
function updateCountdown() { if (!expiresAt.value) return; remainingSeconds.value = Math.max(0, Math.ceil((new Date(expiresAt.value).getTime() - Date.now()) / 1000)); if (!remainingSeconds.value) { clearState(true); ElMessage.warning("会话探测已达 5 分钟，连接已自动关闭，已保留当前输出"); } }
async function startProbe() { if (!instanceId.value || starting.value) return; starting.value = true; clearState(); try { const { data: response } = await startPostgreSQLSessionProbe(instanceId.value); const data = response.data || {}; probeToken.value = data.token || ""; expiresAt.value = data.expires_at || null; canKill.value = Boolean(data.can_kill); updateCountdown(); countdownTimer = window.setInterval(updateCountdown, 1000); pollTimer = window.setInterval(fetchSessions, 3000); await fetchSessions(); ElMessage.success("会话抓取已开始"); } catch (error) { clearState(); ElMessage.error(error.response?.data?.message || "启动会话探测失败"); } finally { starting.value = false; } }
async function fetchSessions(force = false) { const token = probeToken.value; if (!token) return; if (fetching.value) { if (force) refreshQueued = true; return; } fetching.value = true; try { const { data: response } = await getPostgreSQLSessions(token); const data = response.data || {}; if (token !== probeToken.value) return; const next = data.sessions || []; const ids = new Set(next.map((item) => item.id)); hiddenIds.value = new Set([...hiddenIds.value].filter((id) => ids.has(id))); sessions.value = next; collectedAt.value = data.collected_at || null; expiresAt.value = data.expires_at || expiresAt.value; } catch (error) { if (token !== probeToken.value) return; if ([403, 410, 502].includes(error.response?.status)) clearState(true); ElMessage.error(error.response?.data?.message || "抓取 pg_stat_activity 失败"); } finally { fetching.value = false; if (refreshQueued && probeToken.value) { refreshQueued = false; window.setTimeout(fetchSessions, 0); } } }
async function stopProbe(showMessage = false) { const token = probeToken.value; if (!token || stopping.value) return; stopping.value = true; clearState(true); try { await stopPostgreSQLSessionProbe(token); if (showMessage) ElMessage.success("会话探测连接已关闭，已保留当前输出"); } catch (error) { if (showMessage && error.response?.status !== 410) ElMessage.warning(error.response?.data?.message || "连接已在服务端关闭"); } finally { stopping.value = false; } }
async function confirmKill(row) { try { await ElMessageBox.confirm(`确认 Kill 会话 ${row.id}（${row.user || "unknown"}@${row.client || "local"}）？该操作会中断当前连接及其事务。`, "Kill 会话二次确认", { type: "warning", confirmButtonText: "确认 Kill", cancelButtonText: "取消" }); } catch { return; } killingId.value = row.id; try { await killPostgreSQLSession(probeToken.value, row.id); hiddenIds.value = new Set([...hiddenIds.value, row.id]); sessions.value = sessions.value.filter((item) => item.id !== row.id); tableRevision.value += 1; ElMessage.success(`会话 ${row.id} 已终止`); await fetchSessions(true); } catch (error) { ElMessage.error(error.response?.data?.message || "终止会话失败"); } finally { killingId.value = null; } }
function closeOnPageHide() { const token = probeToken.value; if (!token) return; const authToken = localStorage.getItem("dbms_token") || ""; fetch(`/api/v1/postgresql/session-probes/${token}/stop`, { method: "POST", headers: authToken ? { Authorization: `Bearer ${authToken}` } : {}, keepalive: true }).catch(() => {}); clearState(); }
onMounted(async () => { window.addEventListener("pagehide", closeOnPageHide); try { const [clusterResponse, instanceResponse] = await Promise.all([listClusters("postgresql", { action: "query" }), listInstances("postgresql", { action: "query" })]); clusters.value = clusterResponse.data?.data || []; instances.value = instanceResponse.data?.data || []; syncInstance(); } catch (error) { ElMessage.error(error.response?.data?.message || "PostgreSQL 实例与集群加载失败"); } });
onDeactivated(() => stopProbe(false)); onBeforeUnmount(() => { window.removeEventListener("pagehide", closeOnPageHide); stopProbe(false); });
</script>

<style scoped>
.session-probe-page { display: flex; flex-direction: column; gap: 16px; } .header-row, .table-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; } .page-title { color: #303133; font-size: 20px; font-weight: 700; } .page-subtitle { color: #909399; font-size: 13px; margin-top: 5px; } .probe-state, .filters { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; } .countdown { color: #e6a23c; font-variant-numeric: tabular-nums; font-weight: 600; } .filters > .el-select { width: 150px; } .filters .instance-select { width: 280px; } .table-card { min-height: 320px; } .table-header { font-weight: 600; } .summary, .readonly-text { color: #909399; font-size: 13px; font-weight: 400; } .sql-text { color: #303133; font-family: Consolas, "SFMono-Regular", monospace; white-space: nowrap; } @media (max-width: 900px) { .header-row, .table-header { align-items: flex-start; flex-direction: column; } .filters > .el-select, .filters .instance-select { width: 100%; } }
</style>
