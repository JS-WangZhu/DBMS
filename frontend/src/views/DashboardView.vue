<template>
  <div class="dashboard-page" v-loading="loading">
    <div class="dashboard-heading">
      <div>
        <div class="page-title">运行总览</div>
        <div class="page-subtitle">集中查看数据库实例运行状态与集群分布</div>
      </div>
      <div class="heading-actions">
        <span v-if="lastUpdated" class="updated-at">最近更新 {{ lastUpdated }}</span>
        <el-button :icon="Refresh" @click="loadStats">刷新数据</el-button>
      </div>
    </div>

    <el-row :gutter="16" class="metric-row">
      <el-col class="metric-col" :xs="24" :sm="12" :md="6" v-for="card in cards" :key="card.key">
        <el-card class="metric-card">
          <div class="metric-topline">
            <div class="metric-icon" :style="{ color: card.color, backgroundColor: card.softColor }">
              <component :is="card.icon" />
            </div>
            <!-- <el-tag size="small" type="info" effect="light">状态统计</el-tag> -->
          </div>
          <div class="metric-value">{{ card.value }}</div>
          <div class="metric-label">{{ card.label }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="chart-row">
      <el-col :xs="24" :sm="12">
        <el-card class="chart-card">
          <template #header>
            <div class="header-row">
              <div>
                <div class="chart-title">业务维度集群分布</div>
                <div class="chart-subtitle">按所属业务统计集群数量</div>
              </div>
              <span class="chart-unit"></span>
            </div>
          </template>
          <div ref="projectChartRef" class="chart-canvas--pie"></div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12">
        <el-card class="chart-card">
          <template #header>
            <div class="header-row">
              <div>
                <div class="chart-title">系统维度集群分布</div>
                <div class="chart-subtitle">按数据库类型统计集群数量</div>
              </div>
              <span class="chart-unit"></span>
            </div>
          </template>
          <div ref="dbTypeChartRef" class="chart-canvas--pie"></div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import * as echarts from "echarts";
import { nextTick, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { Refresh } from "@element-plus/icons-vue";

import { listInstances } from "../api/modules/instances";
import { getClusterStats } from "../api/modules/clusters";
import MysqlIcon from "../components/icons/MysqlIcon.vue";
import MongoIcon from "../components/icons/MongoIcon.vue";
import RedisIcon from "../components/icons/RedisIcon.vue";
import PostgreSQLIcon from "../components/icons/PostgreSQLIcon.vue";
import DorisIcon from "../components/icons/DorisIcon.vue";

const cards = reactive([
  { key: "mysql", label: "MySQL 实例", value: "0 / 0", icon: MysqlIcon, color: "#2563eb", softColor: "#eff6ff" },
  { key: "mongodb", label: "MongoDB 实例", value: "0 / 0", icon: MongoIcon, color: "#12b76a", softColor: "#ecfdf3" },
  { key: "redis", label: "Redis 实例", value: "0 / 0", icon: RedisIcon, color: "#f04438", softColor: "#fef3f2" },
  { key: "postgresql", label: "PostgreSQL 实例", value: "0 / 0", icon: PostgreSQLIcon, color: "#0ba5ec", softColor: "#f0f9ff" },
  { key: "doris", label: "Doris 实例", value: "0 / 0", icon: DorisIcon, color: "#7a5af8", softColor: "#f4f3ff" },
]);

const projectChartRef = ref(null);
const dbTypeChartRef = ref(null);
const loading = ref(false);
const lastUpdated = ref("");
let projectChartInstance = null;
let dbTypeChartInstance = null;

function setInstanceCard(key, instances) {
  const card = cards.find((item) => item.key === key);
  if (card) {
    const total = instances.length;
    const normal = instances.filter((inst) => inst.running_status === "running").length;
    card.value = `${normal} / ${total}`;
  }
}

function renderProjectChart(data) {
  if (!projectChartRef.value) return;
  if (!projectChartInstance) {
    projectChartInstance = echarts.init(projectChartRef.value);
  }
  projectChartInstance.setOption({
    tooltip: {
      trigger: "item",
      formatter: "{b}: {c}",
      backgroundColor: "#101828",
      borderWidth: 0,
      textStyle: { color: "#fff" },
    },
    legend: {
      orient: "vertical",
      right: 10,
      top: "center",
      textStyle: { color: "#667085", fontSize: 12 },
    },
    series: [
      {
        type: "pie",
        radius: ["40%", "70%"],
        center: ["40%", "50%"],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 6,
          borderColor: "#fff",
          borderWidth: 2,
        },
        label: {
          show: true,
          position: "outside",
          formatter: "{b}\n{c}套 ({d}%)",
          fontSize: 12,
        },
        labelLine: {
          show: true,
        },
        data: data.map((item, index) => ({
          name: item.name,
          value: item.value,
          itemStyle: {
            color: ["#2563eb", "#12b76a", "#f79009", "#7a5af8", "#0ba5ec", "#f04438", "#6172f3", "#15b79e", "#ee46bc"][index % 9],
          },
        })),
      },
    ],
  });
}

function renderDbTypeChart(data) {
  if (!dbTypeChartRef.value) return;
  if (!dbTypeChartInstance) {
    dbTypeChartInstance = echarts.init(dbTypeChartRef.value);
  }
  const dbTypeLabels = {
    mysql: "MySQL",
    mongodb: "MongoDB",
    redis: "Redis",
    postgresql: "PostgreSQL",
    doris: "Doris",
  };
  dbTypeChartInstance.setOption({
    tooltip: {
      trigger: "item",
      formatter: "{b}: {c}",
      backgroundColor: "#101828",
      borderWidth: 0,
      textStyle: { color: "#fff" },
    },
    legend: {
      orient: "vertical",
      right: 10,
      top: "center",
      textStyle: { color: "#667085", fontSize: 12 },
    },
    series: [
      {
        type: "pie",
        radius: ["40%", "70%"],
        center: ["40%", "50%"],
        avoidLabelOverlap: false,
        itemStyle: {
          borderRadius: 6,
          borderColor: "#fff",
          borderWidth: 2,
        },
        label: {
          show: true,
          position: "outside",
          formatter: "{b}\n{c}套 ({d}%)",
          fontSize: 12,
        },
        labelLine: {
          show: true,
        },
        data: data.map((item, index) => ({
          name: dbTypeLabels[item.name] || item.name,
          value: item.value,
          itemStyle: {
            color: ["#2563eb", "#12b76a", "#f04438", "#0ba5ec", "#7a5af8"][index % 5],
          },
        })),
      },
    ],
  });
}

async function loadClusterStats() {
  try {
    const { data } = await getClusterStats();
    const stats = data.data || { by_business: [], by_db_type: [] };
    await nextTick();
    renderProjectChart(stats.by_business || []);
    renderDbTypeChart(stats.by_db_type || []);
  } catch (error) {
    console.error("加载集群统计失败", error);
  }
}

async function loadStats() {
  loading.value = true;
  try {
    await loadClusterStats();

    const tasks = ["mysql", "mongodb", "redis", "postgresql", "doris"].map(async (dbType) => {
      const { data } = await listInstances(dbType);
      const instances = Array.isArray(data.data) ? data.data : [];
      setInstanceCard(dbType, instances);
    });

    await Promise.all(tasks);
    lastUpdated.value = new Intl.DateTimeFormat("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(new Date());
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载总览失败");
  } finally {
    loading.value = false;
  }
}

function handleResize() {
  projectChartInstance?.resize();
  dbTypeChartInstance?.resize();
}

onMounted(() => {
  loadStats();
  window.addEventListener("resize", handleResize);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", handleResize);
  projectChartInstance?.dispose();
  dbTypeChartInstance?.dispose();
  projectChartInstance = null;
  dbTypeChartInstance = null;
});
</script>

<style scoped>
.dashboard-page {
  min-height: 420px;
}

.dashboard-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 18px;
}

.heading-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.updated-at {
  color: var(--text-placeholder);
  font-size: 12px;
}

.metric-row {
  row-gap: 16px;
}

.metric-card {
  position: relative;
  height: 100%;
  overflow: hidden;
}

.metric-card :deep(.el-card__body) {
  position: relative;
  z-index: 1;
  padding: 18px;
}

.metric-topline {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 18px;
}

.metric-icon {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-radius: 9px;
}

.metric-icon :deep(svg) {
  width: 23px;
  height: 23px;
}

.metric-value {
  color: var(--text-primary);
  font-size: 28px;
  font-weight: 700;
  line-height: 1.2;
  letter-spacing: -0.8px;
  font-variant-numeric: tabular-nums;
}

.metric-label {
  margin-top: 7px;
  color: var(--text-regular);
  font-size: 14px;
  font-weight: 600;
}

.metric-hint {
  margin-top: 3px;
  color: var(--text-placeholder);
  font-size: 11px;
}

@media (min-width: 992px) {
  .metric-col {
    flex: 0 0 20%;
    max-width: 20%;
  }
}

.chart-card {
  height: 100%;
}

.chart-row {
  margin-top: 20px;
  row-gap: 16px;
}

.chart-row .chart-card {
  margin-top: 0;
}

.chart-canvas--pie {
  width: 100%;
  height: 340px;
  cursor: pointer;
}

.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.chart-title {
  color: var(--text-primary);
  font-size: 15px;
  font-weight: 650;
}

.chart-subtitle,
.chart-unit {
  color: var(--text-placeholder);
  font-size: 12px;
  font-weight: 400;
}

.chart-subtitle {
  margin-top: 3px;
}

@media (max-width: 700px) {
  .dashboard-heading {
    flex-direction: column;
  }

  .updated-at {
    display: none;
  }

  .chart-canvas--pie {
    height: 300px;
  }
}
</style>
