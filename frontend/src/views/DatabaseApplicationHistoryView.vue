<template>
  <div class="page resource-list-page">
    <div class="list-heading"><div><h2>申请流水</h2><p>统一查看数据库申请与回收流程的处理进度。</p></div>
      <el-input v-model="keyword" placeholder="搜索申请单号或名称" clearable class="search-input" :prefix-icon="Search" />
    </div>
    <el-card shadow="never">
      <el-table :data="[]" height="390">
        <el-table-column prop="requestNo" label="申请单号" min-width="160" /><el-table-column prop="name" label="申请名称" min-width="180" />
        <el-table-column prop="type" label="申请类型" width="110" /><el-table-column prop="database" label="数据库" width="130" />
        <el-table-column prop="status" label="状态" width="110" /><el-table-column prop="createdAt" label="申请时间" width="180" />
        <template #empty><el-empty description="暂无申请流水，流程接口将在下一阶段接入" /></template>
      </el-table>
    </el-card>
  </div>
</template>
<script setup>
import { ref } from "vue";
import { Search } from "@element-plus/icons-vue";
const keyword=ref("");
</script>
<style scoped>
.list-heading{display:flex;justify-content:space-between;align-items:center;margin:4px 2px 16px}.list-heading h2{margin:0 0 6px;font-size:24px;color:#172033}.list-heading p{margin:0;color:#7b879a;font-size:13px}.search-input{width:300px}
</style>
