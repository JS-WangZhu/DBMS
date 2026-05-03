<template>
  <div class="page">
    <el-card class="chart-card">
      <template #header>
        <div class="header-row">
          <span>最近24小时备份结果图表</span>
          <el-button link type="primary" @click="loadStats">刷新</el-button>
        </div>
      </template>

      <div ref="chartRef" class="chart-canvas" @click="loadStats"></div>
    </el-card>
  </div>
</template>

<script setup>
import * as echarts from "echarts";
import { nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import { backupOverview } from "../api/modules/backups";

const chartRef = ref(null);
let chartInstance = null;

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
    const { data } = await backupOverview(24);
    await nextTick();
    renderChart(data.data.chart || {});
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载备份统计失败");
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
.page {
  padding: 20px;
}

.chart-card {
  margin-bottom: 20px;
}

.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.chart-canvas {
  width: 100%;
  height: 500px;
  cursor: pointer;
}
</style>
