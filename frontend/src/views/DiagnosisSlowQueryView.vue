<template>
  <div class="page">
    <div class="page-header">
      <div>
        <div class="page-title">慢查治理</div>
        <div class="page-subtitle">基于 ClickHouse 慢日志明细的检索、聚合分析与治理闭环</div>
      </div>
      <el-tag type="warning" effect="plain">功能预留</el-tag>
    </div>
    <el-card shadow="never" class="placeholder-card">
      <el-empty description="ClickHouse 数据接口待接入">
        <template #image><el-icon class="placeholder-icon"><TrendCharts /></el-icon></template>
        <div class="placeholder-copy">其他程序完成慢日志解析并写入 ClickHouse 后，此页面将读取真实明细；当前不会生成或展示模拟慢 SQL。</div>
      </el-empty>
      <el-row :gutter="14" class="feature-row">
        <el-col v-for="item in plannedFeatures" :key="item.title" :xs="24" :sm="12" :lg="6">
          <div class="feature-item"><el-icon><component :is="item.icon" /></el-icon><div><strong>{{ item.title }}</strong><p>{{ item.description }}</p></div></div>
        </el-col>
      </el-row>
      <el-alert type="info" :closable="false" show-icon :title="capability.message || '慢日志解析程序与 ClickHouse 查询接口尚未接入'" />
    </el-card>
  </div>
</template>

<script setup>
import { markRaw, onMounted, reactive } from "vue";
import { ElMessage } from "element-plus";
import { DataAnalysis, List, Search, TrendCharts } from "@element-plus/icons-vue";
import { getSlowQueryCapabilities } from "../api/modules/diagnosis";

const capability = reactive({ available: false, source: "ClickHouse", message: "" });
const plannedFeatures = [
  { title: "慢 SQL 检索", description: "按实例、库、耗时和时间范围筛选", icon: markRaw(Search) },
  { title: "指纹聚合", description: "SQL 归一化后聚合次数与耗时", icon: markRaw(List) },
  { title: "趋势分析", description: "展示慢查数量和延迟趋势", icon: markRaw(TrendCharts) },
  { title: "治理跟踪", description: "记录负责人、状态与优化效果", icon: markRaw(DataAnalysis) },
];
onMounted(async () => { try { const { data } = await getSlowQueryCapabilities(); Object.assign(capability, data?.data || {}); } catch (error) { ElMessage.error(error.response?.data?.message || "加载慢查治理能力状态失败"); } });
</script>

<style scoped>
.page { padding:16px 20px 24px; }.page-header { display:flex; align-items:center; justify-content:space-between; margin-bottom:14px; padding:14px 16px; background:linear-gradient(135deg,#fff7ed,#fefce8); border:1px solid #fed7aa; border-radius:8px; }.page-title { font-size:18px; font-weight:600; color:#0f172a; }.page-subtitle { margin-top:4px; font-size:12px; color:#64748b; }.placeholder-card { border:1px solid #e5e7eb; }.placeholder-icon { width:84px; height:84px; font-size:76px; color:#cbd5e1; }.placeholder-copy { max-width:620px; line-height:1.7; color:#64748b; }.feature-row { margin:12px 0 22px; }.feature-item { display:flex; gap:12px; min-height:96px; padding:16px; border:1px solid #e5e7eb; border-radius:8px; background:#f8fafc; }.feature-item > .el-icon { margin-top:2px; font-size:22px; color:#2563eb; }.feature-item strong { color:#0f172a; }.feature-item p { margin:7px 0 0; color:#64748b; font-size:12px; line-height:1.5; }
</style>
