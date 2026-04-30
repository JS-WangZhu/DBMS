<template>
  <el-row :gutter="16">
    <el-col :xs="24" :sm="12" :md="4" v-for="card in cards" :key="card.key">
      <el-card class="metric-card">
        <div class="label">{{ card.label }}</div>
        <div class="value">{{ card.value }}</div>
      </el-card>
    </el-col>
  </el-row>

  <el-card class="chart-card">
    <template #header>
      <div class="header-row">
        <span>最近24小时备份结果图表</span>
        <el-button link type="primary" @click="loadStats">刷新</el-button>
      </div>
    </template>

    <div ref="chartRef" class="chart-canvas" @click="loadStats"></div>
  </el-card>
</template>

<script setup>
import * as echarts from "echarts";
import { nextTick, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

import { backupOverview } from "../api/modules/backups";
import { listInstances } from "../api/modules/instances";
import { formatBeijingTime } from "../utils/time";

const cards = reactive([
  { key: "mysql", label: "MySQL 实例", value: "0/0" },
  { key: "mongodb", label: "MongoDB 实例", value: "0/0" },
  { key: "redis", label: "Redis 实例", value: "0/0" },
  { key: "doris", label: "Doris 实例", value: "0/0" },
  { key: "backup_success", label: "备份成功(24h)", value: 0 },
  { key: "backup_failed", label: "备份失败(24h)", value: 0 },
]);

const chartRef = ref(null);
let chartInstance = null;

function setCardValue(key, value) {
  const card = cards.find((item) => item.key === key);
  if (card) {
    card.value = value;
  }
}

function setInstanceCard(key, instances) {
  const card = cards.find((item) => item.key === key);
  if (card) {
    const total = instances.length;
    const normal = instances.filter((inst) => inst.running_status === "running").length;
    card.value = `${normal}/${total}`;
  }
}

function convertToBeijingTime(utcLabel) {
  if (!utcLabel) {
    return utcLabel;
  }
  const dateStr = utcLabel.replace(" ", "T") + ":00Z";
  const date = new Date(dateStr);
  if (Number.isNaN(date.getTime())) {
    return utcLabel;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    hour12: false,
  }).format(date);
}

function renderChart(chart) {
  if (!chartRef.value) {
    return;
  }
  if (!chartInstance) {
    chartInstance = echarts.init(chartRef.value);
  }

  const beijingLabels = (chart.labels || []).map(convertToBeijingTime);

  chartInstance.setOption({
    tooltip: {
      trigger: "axis",
    },
    legend: {
      data: ["成功", "失败"],
      top: 0,
    },
    grid: {
      left: 42,
      right: 20,
      top: 48,
      bottom: 42,
    },
    xAxis: {
      type: "category",
      data: beijingLabels,
      axisLabel: {
        rotate: 35,
      },
    },
    yAxis: {
      type: "value",
      minInterval: 1,
    },
    series: [
      {
        name: "成功",
        type: "line",
        smooth: true,
        data: chart.success || [],
        itemStyle: { color: "#2f9e44" },
        areaStyle: { color: "rgba(47, 158, 68, 0.15)" },
      },
      {
        name: "失败",
        type: "line",
        smooth: true,
        data: chart.failed || [],
        itemStyle: { color: "#d9480f" },
        areaStyle: { color: "rgba(217, 72, 15, 0.12)" },
      },
    ],
  });
}

async function loadStats() {
  try {
    const tasks = ["mysql", "mongodb", "redis", "doris"].map(async (dbType) => {
      const { data } = await listInstances(dbType);
      const instances = Array.isArray(data.data) ? data.data : [];
      setInstanceCard(dbType, instances);
    });

    const backupTask = backupOverview(24).then(async ({ data }) => {
      setCardValue("backup_success", data.data.success || 0);
      setCardValue("backup_failed", data.data.failed || 0);
      await nextTick();
      renderChart(data.data.chart || {});
    });

    await Promise.all([...tasks, backupTask]);
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载总览失败");
  }
}

function handleResize() {
  chartInstance?.resize();
}

onMounted(() => {
  loadStats();
  window.addEventListener("resize", handleResize);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", handleResize);
  chartInstance?.dispose();
  chartInstance = null;
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
  margin-top: 8px;
}

.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.chart-canvas {
  width: 100%;
  height: 380px;
  cursor: pointer;
}
</style>
