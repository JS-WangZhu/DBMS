<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>历史记录</span>
          <el-button :loading="loading" @click="loadHistory">刷新</el-button>
        </div>
      </template>
      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <el-tab-pane label="查询历史" name="query" />
        <el-tab-pane label="变更历史" name="change" />
      </el-tabs>
      <div class="filter-row">
        <el-date-picker
          v-model="dateRange"
          type="datetimerange"
          value-format="YYYY-MM-DD HH:mm:ss"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
          range-separator="至"
          style="width: 280px"
        />
        <el-input v-model="keyword" clearable placeholder="输入SQL/命令关键字" style="width: 35%" />
        <el-button type="primary" :loading="loading" @click="onSearch">查询</el-button>
        <el-button :loading="loading" @click="onReset">重置</el-button>
      </div>
      <el-table :data="rows" stripe size="small" v-loading="loading">
        <el-table-column prop="created_at_cn" label="操作时间" width="180" />
        <el-table-column prop="username" label="操作用户" width="140" />
        <el-table-column prop="db_type" label="类型" width="100" />
        <el-table-column prop="business_line" label="项目" width="120" />
        <el-table-column prop="environment" label="环境" width="100" />
        <el-table-column prop="cluster_name" label="集群" width="180" />
        <el-table-column prop="instance_name" label="实例" width="180" />
        <el-table-column prop="statement" label="SQL/命令" min-width="380" show-overflow-tooltip />
        <el-table-column label="结果" width="90">
          <template #default="{ row }">
            <el-tag :type="row.success ? 'success' : 'danger'">{{ row.success ? "成功" : "失败" }}</el-tag>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-row">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @current-change="loadHistory"
          @size-change="onPageSizeChange"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";

import { listChangeHistory, listQueryHistory } from "../api/modules/data_access";

const activeTab = ref("query");
const loading = ref(false);
const rows = ref([]);
const queryPage = ref(1);
const queryPageSize = ref(10);
const changePage = ref(1);
const changePageSize = ref(10);
const total = ref(0);
const keyword = ref("");
const dateRange = ref([]);

const page = ref(1);
const pageSize = ref(10);

function syncPagerFromTab() {
  if (activeTab.value === "change") {
    page.value = changePage.value;
    pageSize.value = changePageSize.value;
    return;
  }
  page.value = queryPage.value;
  pageSize.value = queryPageSize.value;
}

function syncTabFromPager() {
  if (activeTab.value === "change") {
    changePage.value = page.value;
    changePageSize.value = pageSize.value;
    return;
  }
  queryPage.value = page.value;
  queryPageSize.value = pageSize.value;
}

async function loadHistory() {
  loading.value = true;
  try {
    syncTabFromPager();
    const fetcher = activeTab.value === "change" ? listChangeHistory : listQueryHistory;
    const filters = {
      keyword: keyword.value.trim() || undefined,
      start_date: dateRange.value?.[0] || undefined,
      end_date: dateRange.value?.[1] || undefined,
    };
    const { data } = await fetcher(page.value, pageSize.value, filters);
    const result = data?.data || {};
    rows.value = result.items || [];
    total.value = result.total || 0;
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载历史记录失败");
  } finally {
    loading.value = false;
  }
}

async function onTabChange() {
  syncPagerFromTab();
  await loadHistory();
}

async function onPageSizeChange() {
  page.value = 1;
  syncTabFromPager();
  await loadHistory();
}

async function onSearch() {
  page.value = 1;
  syncTabFromPager();
  await loadHistory();
}

async function onReset() {
  keyword.value = "";
  dateRange.value = [];
  page.value = 1;
  syncTabFromPager();
  await loadHistory();
}

onMounted(loadHistory);
</script>

<style scoped>
.page {
  padding: 20px;
}

.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.pagination-row {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}

.filter-row {
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 10px;
}
</style>
