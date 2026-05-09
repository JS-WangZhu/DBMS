<template>
  <div>
    <el-row :gutter="16">
      <el-col :xs="24" :sm="12" :md="6" v-for="card in cards" :key="card.key">
        <el-card class="metric-card">
          <div class="label">{{ card.label }}</div>
          <div class="value">{{ card.value }}</div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="chart-row">
      <el-col :xs="24" :sm="12">
        <el-card class="chart-card">
          <template #header>
            <div class="header-row">
              <span>业务维度集群分布</span>
              <el-button link type="primary" @click="loadClusterStats">刷新</el-button>
            </div>
          </template>
          <div ref="projectChartRef" class="chart-canvas--pie"></div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12">
        <el-card class="chart-card">
          <template #header>
            <div class="header-row">
              <span>系统维度集群分布</span>
              <el-button link type="primary" @click="loadClusterStats">刷新</el-button>
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

import { listInstances } from "../api/modules/instances";
import { getClusterStats } from "../api/modules/clusters";

const cards = reactive([
  { key: "mysql", label: "MySQL 实例", value: "0/0" },
  { key: "mongodb", label: "MongoDB 实例", value: "0/0" },
  { key: "redis", label: "Redis 实例", value: "0/0" },
  { key: "doris", label: "Doris 实例", value: "0/0" },
]);

const projectChartRef = ref(null);
const dbTypeChartRef = ref(null);
let projectChartInstance = null;
let dbTypeChartInstance = null;

function setInstanceCard(key, instances) {
  const card = cards.find((item) => item.key === key);
  if (card) {
    const total = instances.length;
    const normal = instances.filter((inst) => inst.running_status === "running").length;
    card.value = `${normal}/${total}`;
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
    },
    legend: {
      orient: "vertical",
      right: 10,
      top: "center",
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
            color: ["#5470c6", "#91cc75", "#fac858", "#ee6666", "#73c0de", "#3ba272", "#fc8452", "#9a60b4", "#ea7ccc"][index % 9],
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
    doris: "Doris",
  };
  dbTypeChartInstance.setOption({
    tooltip: {
      trigger: "item",
      formatter: "{b}: {c}",
    },
    legend: {
      orient: "vertical",
      right: 10,
      top: "center",
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
            color: ["#5470c6", "#91cc75", "#fac858", "#ee6666"][index % 4],
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
  try {
    await loadClusterStats();

    const tasks = ["mysql", "mongodb", "redis", "doris"].map(async (dbType) => {
      const { data } = await listInstances(dbType);
      const instances = Array.isArray(data.data) ? data.data : [];
      setInstanceCard(dbType, instances);
    });

    await Promise.all(tasks);
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载总览失败");
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
.metric-card {
  margin-bottom: 16px;
}

.label {
  color: #5c6e83;
  margin-bottom: 8px;
}

.value {
  font-size: 30px;
  font-weight: 700;
  color: #0a4f92;
}

.chart-card {
  margin-top: 16px;
}

.chart-row {
  margin-top: 8px;
}

.chart-row .chart-card {
  margin-top: 0;
}

.chart-canvas--pie {
  width: 100%;
  height: 320px;
  cursor: pointer;
}

.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
