<template>
  <div class="performance-page">
    <el-card class="toolbar-card" shadow="never">
      <div class="toolbar-header">
        <div>
          <div class="page-title">MySQL 实例详情</div>
          <div class="page-subtitle">性能数据来自实例状态快照</div>
        </div>
      </div>
      <div class="filter-grid">
        <div class="filter-item">
          <label>项目</label>
          <el-select v-model="selectedBusinessLine" filterable clearable placeholder="请选择项目" @change="onBusinessLineChange">
            <el-option v-for="item in businessLines" :key="item" :label="item" :value="item" />
          </el-select>
        </div>
        <div class="filter-item">
          <label>环境</label>
          <el-select v-model="selectedEnvironment" filterable clearable placeholder="请选择环境" @change="onEnvironmentChange">
            <el-option v-for="item in environments" :key="item" :label="item" :value="item" />
          </el-select>
        </div>
        <div class="filter-item">
          <label>集群名称</label>
          <el-select v-model="selectedClusterId" filterable clearable placeholder="请输入或选择集群" @change="onClusterChange">
            <el-option v-for="item in filteredClusters" :key="item.id" :label="clusterOptionLabel(item)" :value="item.id" />
          </el-select>
        </div>
        <div class="filter-item filter-item--instance">
          <label>MySQL 实例</label>
          <el-select v-model="instanceId" filterable placeholder="请选择 MySQL 实例" @change="loadPerformance">
            <el-option
              v-for="item in filteredInstances"
              :key="item.id"
              :label="`${item.name} (${item.resolved_ip || item.host_input}:${item.port})`"
              :value="item.id"
            />
          </el-select>
        </div>
        <div class="filter-item">
          <label>时间范围</label>
          <el-select v-model="hours" @change="loadPerformance">
            <el-option label="最近 1 小时" :value="1" />
            <el-option label="最近 6 小时" :value="6" />
            <el-option label="最近 24 小时" :value="24" />
            <el-option label="最近 3 天" :value="72" />
            <el-option label="最近 7 天" :value="168" />
          </el-select>
        </div>
        <div class="filter-action">
          <el-button type="primary" :loading="loading" @click="loadPerformance">刷新</el-button>
        </div>
      </div>
      <el-alert
        v-if="instanceId && !loading && !points.length"
        title="当前时间范围内暂无实例状态数据"
        description="请确认实例状态检测已启用，且 Node Exporter 配置可正常访问。"
        type="warning"
        show-icon
        :closable="false"
        class="empty-alert"
      />
    </el-card>

    <section class="section-block" v-loading="loading">
      <div class="section-heading">
        <div>
          <h2>基础资源</h2>
          <span>CPU、内存、磁盘与网络趋势</span>
        </div>
        <span v-if="latestTime" class="latest-time">最后采集：{{ formatTime(latestTime) }}</span>
      </div>
      <div class="chart-grid basic-grid">
        <el-card v-for="chart in basicCharts" :key="chart.key" class="chart-card" shadow="hover">
          <template #header>
            <div class="chart-title"><span>{{ chart.title }}</span><strong>{{ latestLabel(chart) }}</strong></div>
          </template>
          <div :ref="(el) => setChartRef(chart.key, el)" class="chart-container"></div>
        </el-card>
      </div>
    </section>

    <section class="section-block" v-loading="loading">
      <div class="section-heading">
        <div><h2>数据库运行指标</h2><span>运行会话与锁等待趋势</span></div>
      </div>
      <div class="chart-grid database-grid">
        <el-card v-for="chart in databaseCharts" :key="chart.key" class="chart-card" shadow="hover">
          <template #header>
            <div class="chart-title"><span>{{ chart.title }}</span><strong>{{ latestLabel(chart) }}</strong></div>
          </template>
          <div :ref="(el) => setChartRef(chart.key, el)" class="chart-container"></div>
        </el-card>
      </div>
    </section>
  </div>
</template>

<script setup>
import * as echarts from "echarts";
import { computed, nextTick, onActivated, onBeforeUnmount, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import { listClusters } from "../api/modules/clusters";
import { listInstances } from "../api/modules/instances";
import { getInstancePerformance } from "../api/modules/monitoring";

const instances = ref([]);
const clusters = ref([]);
const selectedBusinessLine = ref(null);
const selectedEnvironment = ref(null);
const selectedClusterId = ref(null);
const instanceId = ref(null);
const hours = ref(24);
const points = ref([]);
const loading = ref(false);
const chartElements = new Map();
const chartInstances = new Map();

const basicCharts = [
  { key: "cpu", title: "CPU 使用率", fields: [{ key: "cpu_usage_pct", name: "CPU", color: "#409eff" }], unit: "%" },
  { key: "memory", title: "内存使用率", fields: [{ key: "memory_usage_pct", name: "内存", color: "#67c23a" }], unit: "%" },
  { key: "disk", title: "磁盘使用率", fields: [{ key: "disk_usage_pct", name: "磁盘", color: "#e6a23c" }], unit: "%" },
  {
    key: "network",
    title: "网络流量",
    fields: [
      { key: "network_rx_bps", name: "接收", color: "#36cfc9" },
      { key: "network_tx_bps", name: "发送", color: "#9254de" },
    ],
    unit: "B/s",
  },
];
const databaseCharts = [
  {
    key: "sessions",
    title: "运行会话数",
    fields: [
      { key: "sessions", name: "连接会话", color: "#409eff" },
      { key: "running_sessions", name: "运行会话", color: "#f56c6c" },
    ],
    unit: "",
  },
  { key: "locks", title: "锁等待数量", fields: [{ key: "lock_waits", name: "锁等待", color: "#f56c6c" }], unit: "" },
];

const latestPoint = computed(() => points.value.length ? points.value[points.value.length - 1] : null);
const latestTime = computed(() => latestPoint.value?.collected_at || null);
const businessLines = computed(() => [
  ...new Set(clusters.value.map((item) => item.business_line || item.namespace).filter(Boolean)),
].sort());
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
  if (selectedClusterId.value) {
    return instances.value.filter((item) => item.cluster_id === selectedClusterId.value);
  }
  if (!selectedBusinessLine.value && !selectedEnvironment.value) return instances.value;
  const allowedClusterIds = new Set(filteredClusters.value.map((item) => item.id));
  return instances.value.filter((item) => item.cluster_id && allowedClusterIds.has(item.cluster_id));
});

function clusterOptionLabel(item) {
  return [item.business_line || item.namespace, item.environment, item.name].filter(Boolean).join("/") || item.name;
}

async function syncInstanceSelection() {
  const available = filteredInstances.value;
  if (!available.some((item) => item.id === instanceId.value)) {
    instanceId.value = available[0]?.id || null;
  }
  await loadPerformance();
}

async function onBusinessLineChange() {
  selectedEnvironment.value = null;
  selectedClusterId.value = null;
  await syncInstanceSelection();
}

async function onEnvironmentChange() {
  selectedClusterId.value = null;
  await syncInstanceSelection();
}

async function onClusterChange() {
  await syncInstanceSelection();
}

function setChartRef(key, element) {
  if (element) chartElements.set(key, element);
}

function formatTime(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function formatBytes(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  const units = ["B/s", "KB/s", "MB/s", "GB/s"];
  let number = Number(value);
  let index = 0;
  while (number >= 1024 && index < units.length - 1) {
    number /= 1024;
    index += 1;
  }
  return `${number.toFixed(number >= 10 ? 1 : 2)} ${units[index]}`;
}

function latestLabel(chart) {
  const item = latestPoint.value;
  if (!item) return "-";
  const values = chart.fields.map((field) => item[field.key]).filter((value) => value !== null && value !== undefined);
  if (!values.length) return "-";
  if (chart.unit === "B/s") return chart.fields.map((field) => `${field.name} ${formatBytes(item[field.key])}`).join(" / ");
  return `${values[0]}${chart.unit}`;
}

function chartOption(chart) {
  const percent = chart.unit === "%";
  return {
    animationDuration: 350,
    color: chart.fields.map((field) => field.color),
    tooltip: {
      trigger: "axis",
      formatter(params) {
        const time = params[0]?.axisValueLabel || "";
        const rows = params.map((item) => {
          const value = item.data?.[1];
          const text = value === null || value === undefined ? "-" : (chart.unit === "B/s" ? formatBytes(value) : `${value}${chart.unit}`);
          return `${item.marker}${item.seriesName}：${text}`;
        });
        return [time, ...rows].join("<br/>");
      },
    },
    legend: { top: 0, right: 8 },
    grid: { top: 40, left: 48, right: 22, bottom: 42, containLabel: false },
    xAxis: {
      type: "time",
      axisLabel: { color: "#909399", hideOverlap: true },
      splitLine: { show: false },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: percent ? 100 : undefined,
      axisLabel: {
        color: "#909399",
        formatter: chart.unit === "B/s" ? (value) => formatBytes(value).replace("/s", "") : `{value}${chart.unit}`,
      },
      splitLine: { lineStyle: { color: "#ebeef5" } },
    },
    series: chart.fields.map((field) => ({
      name: field.name,
      type: "line",
      smooth: true,
      showSymbol: false,
      connectNulls: false,
      lineStyle: { width: 2 },
      areaStyle: chart.fields.length === 1 ? { opacity: 0.08 } : undefined,
      data: points.value.map((item) => [item.collected_at, item[field.key] ?? null]),
    })),
    graphic: points.value.length ? [] : [{ type: "text", left: "center", top: "middle", style: { text: "暂无数据", fill: "#909399", fontSize: 14 } }],
  };
}

function renderCharts() {
  [...basicCharts, ...databaseCharts].forEach((chart) => {
    const element = chartElements.get(chart.key);
    if (!element) return;
    let instance = chartInstances.get(chart.key);
    if (!instance) {
      instance = echarts.init(element);
      chartInstances.set(chart.key, instance);
    }
    instance.setOption(chartOption(chart), true);
  });
}

function resizeCharts() {
  chartInstances.forEach((chart) => chart.resize());
}

async function loadInstances() {
  try {
    const response = await listInstances("mysql");
    instances.value = response.data?.data || [];
    if (!instanceId.value && instances.value.length) instanceId.value = instances.value[0].id;
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "MySQL 实例加载失败");
  }
}

async function loadClusters() {
  try {
    const response = await listClusters("mysql");
    clusters.value = response.data?.data || [];
  } catch (error) {
    clusters.value = [];
    ElMessage.error(error.response?.data?.message || "MySQL 集群加载失败");
  }
}

async function loadPerformance() {
  if (!instanceId.value) {
    points.value = [];
    await nextTick();
    renderCharts();
    return;
  }
  loading.value = true;
  try {
    const response = await getInstancePerformance(instanceId.value, hours.value);
    points.value = response.data?.data?.points || [];
  } catch (error) {
    points.value = [];
    ElMessage.error(error.response?.data?.message || "性能数据加载失败");
  } finally {
    loading.value = false;
    await nextTick();
    renderCharts();
  }
}

onMounted(async () => {
  window.addEventListener("resize", resizeCharts);
  await Promise.all([loadClusters(), loadInstances()]);
  await loadPerformance();
});
onActivated(() => nextTick(() => resizeCharts()));
onBeforeUnmount(() => {
  window.removeEventListener("resize", resizeCharts);
  chartInstances.forEach((chart) => chart.dispose());
  chartInstances.clear();
});
</script>

<style scoped>
.performance-page { display: flex; flex-direction: column; gap: 18px; }
.toolbar-card { border: 1px solid #e4e7ed; }
.toolbar-header { display: flex; align-items: center; justify-content: space-between; gap: 18px; }
.filter-grid { display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); gap: 12px; align-items: end; margin-top: 18px; }
.filter-item { grid-column: span 2; min-width: 0; }
.filter-item--instance { grid-column: span 3; }
.filter-item label { display: block; color: #606266; font-size: 13px; line-height: 20px; margin-bottom: 6px; }
.filter-item :deep(.el-select) { display: block; width: 100%; }
.filter-action { grid-column: span 1; display: flex; align-items: flex-end; }
.filter-action .el-button { width: 100%; }
.page-title { color: #303133; font-size: 20px; font-weight: 700; }
.page-subtitle { color: #909399; font-size: 13px; margin-top: 5px; }
.empty-alert { margin-top: 16px; }
.section-block { min-height: 180px; }
.section-heading { display: flex; justify-content: space-between; align-items: flex-end; margin: 0 2px 12px; }
.section-heading h2 { color: #303133; font-size: 17px; margin: 0 0 4px; }
.section-heading span { color: #909399; font-size: 13px; }
.latest-time { white-space: nowrap; }
.chart-grid { display: grid; gap: 16px; }
.basic-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.database-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.chart-card :deep(.el-card__header) { padding: 14px 16px; }
.chart-card :deep(.el-card__body) { padding: 8px 12px 12px; }
.chart-title { display: flex; justify-content: space-between; align-items: center; gap: 12px; color: #303133; font-weight: 600; }
.chart-title strong { color: #409eff; font-size: 13px; font-weight: 600; text-align: right; }
.chart-container { width: 100%; height: 280px; }
@media (max-width: 1050px) {
  .basic-grid, .database-grid { grid-template-columns: 1fr; }
  .filter-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .filter-item, .filter-action { grid-column: span 1; }
  .filter-item--instance { grid-column: span 2; }
}
@media (max-width: 640px) {
  .filter-grid { grid-template-columns: minmax(0, 1fr); }
  .filter-item, .filter-item--instance, .filter-action { grid-column: span 1; }
}
</style>
