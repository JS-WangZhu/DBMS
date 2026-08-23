<template>
  <div class="page">
    <div class="page-header">
      <div>
        <div class="page-title">参数检查</div>
        <div class="page-subtitle">定时采集全部数据库实例的运行参数，并按配置保留各实例历史版本</div>
      </div>
      <div class="page-actions">
        <el-button :icon="Refresh" @click="reload">刷新</el-button>
        <el-button v-if="isAdmin" :icon="Setting" @click="configVisible = true">采集配置</el-button>
        <el-button v-if="isAdmin" type="primary" :icon="VideoPlay" :loading="starting" :disabled="config.running" @click="runNow">
          {{ config.running ? "采集中" : "立即采集" }}
        </el-button>
      </div>
    </div>

    <el-row :gutter="14" class="summary-row">
      <el-col :xs="24" :sm="8">
        <el-card shadow="never" class="summary-card">
          <span class="summary-label">定时采集</span>
          <div class="summary-value"><el-tag :type="config.enabled ? 'success' : 'info'">{{ config.enabled ? "已启用" : "已停用" }}</el-tag></div>
          <span class="summary-note">Cron：{{ config.cron_expr || "0 0 * * *" }}</span>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="8">
        <el-card shadow="never" class="summary-card">
          <span class="summary-label">最近采集</span>
          <div class="summary-value small">{{ formatUtcTimeAsBeijing(config.last_run_at) }}</div>
          <span class="summary-note">{{ config.last_message || "尚未执行采集" }}</span>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="8">
        <el-card shadow="never" class="summary-card">
          <span class="summary-label">下次运行</span>
          <div class="summary-value small">{{ config.enabled ? formatUtcTimeAsBeijing(config.next_run_at) : "-" }}</div>
          <span class="summary-note">调度时区：Asia/Shanghai</span>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="content-card">
      <div class="filters">
        <el-input v-model="filters.keyword" clearable placeholder="搜索实例名称" :prefix-icon="Search" @keyup.enter="applyFilters" />
        <el-select v-model="filters.business_line" clearable filterable placeholder="项目" @change="onBusinessLineChange">
          <el-option v-for="item in businessLineOptions" :key="item" :label="item" :value="item" />
        </el-select>
        <el-select v-model="filters.environment" clearable filterable placeholder="环境" @change="onEnvironmentChange">
          <el-option v-for="item in environmentOptions" :key="item" :label="item" :value="item" />
        </el-select>
        <el-select v-model="filters.cluster_id" clearable filterable placeholder="集群" @change="applyFilters">
          <el-option v-for="item in clusterOptions" :key="item.id" :label="clusterOptionLabel(item)" :value="item.id" />
        </el-select>
        <el-select v-model="filters.db_type" clearable placeholder="数据库类型" @change="onDbTypeChange">
          <el-option v-for="item in dbTypeOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
        <el-button type="primary" :icon="Search" @click="applyFilters">查询</el-button>
      </div>

      <el-table v-loading="loading" :data="rows" stripe>
        <el-table-column prop="instance_name" label="实例" min-width="170" />
        <el-table-column prop="business_line" label="项目" min-width="120" show-overflow-tooltip />
        <el-table-column prop="environment" label="环境" width="100" show-overflow-tooltip />
        <el-table-column prop="cluster_name" label="集群" min-width="140" show-overflow-tooltip />
        <el-table-column label="类型" width="120"><template #default="scope"><el-tag effect="plain">{{ dbTypeLabel(scope.row.db_type) }}</el-tag></template></el-table-column>
        <el-table-column label="地址" min-width="180"><template #default="scope">{{ scope.row.host }}:{{ scope.row.port }}</template></el-table-column>
        <el-table-column label="采集方式" width="100"><template #default="scope">{{ scope.row.access_mode === "agent" ? "Agent" : "Server" }}</template></el-table-column>
        <el-table-column label="状态" width="110">
          <template #default="scope">
            <el-tag v-if="scope.row.latest" :type="scope.row.latest.status === 'success' ? 'success' : 'danger'">
              {{ scope.row.latest.status === "success" ? "成功" : "失败" }}
            </el-tag>
            <el-tag v-else type="info">未采集</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="参数数量" width="90"><template #default="scope">{{ scope.row.latest?.parameter_count ?? "-" }}</template></el-table-column>
        <el-table-column label="采集时间" width="190"><template #default="scope">{{ formatUtcTimeAsBeijing(scope.row.latest?.collected_at) }}</template></el-table-column>
        <el-table-column label="操作" width="100" fixed="right"><template #default="scope"><el-button link type="primary" @click="openVersions(scope.row)">查看版本</el-button></template></el-table-column>
      </el-table>
      <div class="pagination"><el-pagination v-model:current-page="page" v-model:page-size="pageSize" layout="total, prev, pager, next" :total="total" @current-change="loadInstances" /></div>
    </el-card>

    <el-dialog v-model="configVisible" title="参数采集配置" width="620px">
      <el-form :model="configForm" label-width="130px">
        <el-form-item label="启用定时采集"><el-switch v-model="configForm.enabled" /></el-form-item>
        <el-form-item label="采集时间 Cron">
          <el-input v-model="configForm.cron_expr" placeholder="0 0 * * *" />
          <div class="form-tip">默认每天 00:00 运行，使用 Asia/Shanghai 时区，支持标准 5 段 Cron。</div>
        </el-form-item>
        <el-form-item label="数据库类型">
          <el-checkbox-group v-model="configForm.db_types">
            <el-checkbox v-for="item in dbTypeOptions" :key="item.value" :value="item.value">{{ item.label }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="单实例超时"><el-input-number v-model="configForm.timeout_seconds" :min="3" :max="120" /><span class="unit">秒</span></el-form-item>
        <el-form-item label="采集并发数"><el-input-number v-model="configForm.max_workers" :min="1" :max="20" /></el-form-item>
        <el-form-item label="版本保留（个/实例）">
          <el-input-number v-model="configForm.retention_versions" :min="1" :max="50" />
          <span class="inline-hint">保存后立即清理超出版本</span>
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="configVisible = false">取消</el-button><el-button type="primary" :loading="saving" @click="saveConfig">保存并更新调度</el-button></template>
    </el-dialog>

    <el-drawer v-model="versionsVisible" :title="`${selectedInstance?.instance_name || ''} · 参数版本`" size="72%">
      <div v-loading="versionsLoading" class="version-panel">
        <el-alert v-if="!versions.length" type="info" :closable="false" title="该实例尚无采集版本" />
        <template v-else>
          <div class="version-toolbar">
            <el-select v-model="selectedVersionId" style="width: 340px">
              <el-option v-for="(version, index) in versions" :key="version.id" :label="`版本 ${versions.length - index} · ${formatUtcTimeAsBeijing(version.collected_at)}`" :value="version.id" />
            </el-select>
            <el-input v-model="parameterKeyword" clearable :prefix-icon="Search" placeholder="搜索参数名或值" style="width: 280px" />
            <el-tag v-if="selectedVersion" :type="selectedVersion.status === 'success' ? 'success' : 'danger'">{{ selectedVersion.status === "success" ? "采集成功" : "采集失败" }}</el-tag>
          </div>
          <el-alert v-if="selectedVersion?.error_message" type="error" :closable="false" :title="selectedVersion.error_message" class="version-error" />
          <el-table :data="filteredParameters" border height="calc(100vh - 210px)">
            <el-table-column type="index" width="60" />
            <el-table-column prop="name" label="参数名" min-width="230" show-overflow-tooltip />
            <el-table-column label="当前值" min-width="300" show-overflow-tooltip><template #default="scope"><span class="mono">{{ displayValue(scope.row.value) }}</span></template></el-table-column>
            <el-table-column prop="source" label="来源" width="120" />
            <el-table-column prop="context" label="上下文" width="120" />
            <el-table-column label="待重启" width="90"><template #default="scope"><span v-if="scope.row.pending_restart != null">{{ scope.row.pending_restart ? "是" : "否" }}</span><span v-else>-</span></template></el-table-column>
          </el-table>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { Refresh, Search, Setting, VideoPlay } from "@element-plus/icons-vue";
import {
  getParameterCollectionConfig,
  listParameterCheckInstances,
  listParameterVersions,
  runParameterCollection,
  updateParameterCollectionConfig,
} from "../api/modules/diagnosis";
import { listClusters } from "../api/modules/clusters";
import { formatUtcTimeAsBeijing } from "../utils/time";

const dbTypeOptions = [
  { value: "mysql", label: "MySQL" }, { value: "postgresql", label: "PostgreSQL" },
  { value: "mongodb", label: "MongoDB" }, { value: "redis", label: "Redis" }, { value: "doris", label: "Doris" },
];
const loading = ref(false); const starting = ref(false); const saving = ref(false);
const rows = ref([]); const total = ref(0); const page = ref(1); const pageSize = ref(20);
const clusters = ref([]);
const filters = reactive({ keyword: "", business_line: "", environment: "", cluster_id: null, db_type: "" });
const config = reactive({ enabled: true, cron_expr: "0 0 * * *", db_types: dbTypeOptions.map((item) => item.value), timeout_seconds: 15, max_workers: 5, retention_versions: 3, running: false });
const configForm = reactive({}); const configVisible = ref(false);
const versionsVisible = ref(false); const versionsLoading = ref(false); const versions = ref([]); const selectedVersionId = ref(null); const selectedInstance = ref(null); const parameterKeyword = ref("");
const isAdmin = computed(() => { try { return JSON.parse(localStorage.getItem("dbms_user") || "{}").role === "admin"; } catch { return false; } });
const selectedVersion = computed(() => versions.value.find((item) => item.id === selectedVersionId.value) || null);
const filteredParameters = computed(() => {
  const keyword = parameterKeyword.value.trim().toLowerCase();
  const items = selectedVersion.value?.parameters || [];
  return keyword ? items.filter((item) => `${item.name} ${displayValue(item.value)}`.toLowerCase().includes(keyword)) : items;
});
const dbTypeScopedClusters = computed(() => filters.db_type ? clusters.value.filter((item) => item.db_type === filters.db_type) : clusters.value);
const businessLineOptions = computed(() => [...new Set(dbTypeScopedClusters.value.map((item) => item.business_line || item.namespace).filter(Boolean))].sort());
const environmentOptions = computed(() => {
  const source = filters.business_line
    ? dbTypeScopedClusters.value.filter((item) => (item.business_line || item.namespace) === filters.business_line)
    : dbTypeScopedClusters.value;
  return [...new Set(source.map((item) => item.environment).filter(Boolean))].sort();
});
const clusterOptions = computed(() => dbTypeScopedClusters.value.filter((item) => {
  if (filters.business_line && (item.business_line || item.namespace) !== filters.business_line) return false;
  if (filters.environment && item.environment !== filters.environment) return false;
  return true;
}));

function dbTypeLabel(value) { return dbTypeOptions.find((item) => item.value === value)?.label || value; }
function clusterOptionLabel(item) { return [item.business_line || item.namespace, item.environment, item.name].filter(Boolean).join(" / "); }
function displayValue(value) { return value && typeof value === "object" ? JSON.stringify(value) : String(value ?? ""); }
function applyConfig(data = {}) { Object.assign(config, data); Object.assign(configForm, { enabled: config.enabled, cron_expr: config.cron_expr, db_types: [...(config.db_types || [])], timeout_seconds: config.timeout_seconds, max_workers: config.max_workers, retention_versions: config.retention_versions || 3 }); }
async function loadConfig() { try { const { data } = await getParameterCollectionConfig(); applyConfig(data?.data || {}); } catch (error) { ElMessage.error(error.response?.data?.message || "加载采集配置失败"); } }
async function loadScopeOptions() { try { const { data } = await listClusters(undefined, { action: "view_instance" }); clusters.value = data?.data || []; } catch (error) { ElMessage.error(error.response?.data?.message || "加载项目与集群选项失败"); } }
async function loadInstances() { loading.value = true; try { const { data } = await listParameterCheckInstances({ page: page.value, page_size: pageSize.value, ...filters }); const payload = data?.data || {}; rows.value = payload.items || []; total.value = payload.total || 0; } catch (error) { ElMessage.error(error.response?.data?.message || "加载实例参数结果失败"); } finally { loading.value = false; } }
async function reload() { await Promise.all([loadConfig(), loadScopeOptions(), loadInstances()]); }
function applyFilters() { page.value = 1; loadInstances(); }
function onBusinessLineChange() { filters.environment = ""; filters.cluster_id = null; applyFilters(); }
function onEnvironmentChange() { filters.cluster_id = null; applyFilters(); }
function onDbTypeChange() { filters.business_line = ""; filters.environment = ""; filters.cluster_id = null; applyFilters(); }
async function saveConfig() { saving.value = true; try { const { data } = await updateParameterCollectionConfig({ ...configForm }); applyConfig(data?.data || {}); configVisible.value = false; ElMessage.success("采集配置已更新"); await loadConfig(); } catch (error) { ElMessage.error(error.response?.data?.message || "保存采集配置失败"); } finally { saving.value = false; } }
async function runNow() { starting.value = true; try { await runParameterCollection(); ElMessage.success("采集任务已启动"); setTimeout(reload, 1200); } catch (error) { ElMessage.error(error.response?.data?.message || "启动采集失败"); } finally { starting.value = false; } }
async function openVersions(row) { selectedInstance.value = row; versionsVisible.value = true; versionsLoading.value = true; parameterKeyword.value = ""; try { const { data } = await listParameterVersions(row.instance_id); versions.value = data?.data?.versions || []; selectedVersionId.value = versions.value[0]?.id || null; } catch (error) { ElMessage.error(error.response?.data?.message || "加载参数版本失败"); } finally { versionsLoading.value = false; } }
watch(configVisible, (visible) => { if (visible) applyConfig(config); });
onMounted(reload);
</script>

<style scoped>
.page { padding: 16px 20px 24px; }
.page-header { display:flex; align-items:flex-end; justify-content:space-between; gap:16px; margin-bottom:14px; padding:14px 16px; background:linear-gradient(135deg,#eef4ff,#f0fdfa); border:1px solid #dbeafe; border-radius:8px; }
.page-title { font-size:18px; font-weight:600; color:#0f172a; }.page-subtitle,.summary-note,.form-tip { margin-top:4px; font-size:12px; color:#64748b; }.page-actions,.filters,.version-toolbar { display:flex; gap:10px; align-items:center; }.summary-row { margin-bottom:14px; }.summary-card { height:130px; overflow:hidden; }.summary-card :deep(.el-card__body) { height:100%; box-sizing:border-box; display:flex; flex-direction:column; justify-content:center; overflow:hidden; }.summary-label { color:#64748b; font-size:13px; }.summary-value { margin:10px 0 7px; font-size:22px; font-weight:600; color:#0f172a; }.summary-value.small { font-size:16px; }.content-card { border:1px solid #e5e7eb; }.filters { margin-bottom:14px; flex-wrap:wrap; }.filters .el-input { width:220px; }.filters .el-select { width:150px; }.pagination { display:flex; justify-content:flex-end; margin-top:14px; }.unit { margin-left:8px; color:#64748b; }.inline-hint { margin-left:10px; color:#94a3b8; font-size:12px; white-space:nowrap; }.version-panel { min-height:200px; }.version-toolbar { margin-bottom:12px; }.version-error { margin-bottom:12px; }.mono { font-family:ui-monospace,SFMono-Regular,Menlo,monospace; font-size:12px; }
@media (max-width: 768px) { .page-header,.filters,.version-toolbar { align-items:stretch; flex-direction:column; }.page-actions { flex-wrap:wrap; }.filters .el-input,.filters .el-select { width:100%; } }
</style>
