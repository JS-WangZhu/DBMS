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
          style="width: 350px"
        />
        <el-input v-model="keyword" clearable placeholder="输入SQL/命令关键字" style="width: 260px" />
        <template v-if="activeTab === 'query'">
          <el-select v-model="queryFilters.db_type" clearable placeholder="数据库类型" style="width: 140px">
            <el-option label="MySQL" value="mysql" />
            <el-option label="PostgreSQL" value="postgresql" />
            <el-option label="MongoDB" value="mongodb" />
            <el-option label="Redis" value="redis" />
          </el-select>
          <el-select v-model="queryFilters.success" clearable placeholder="执行状态" style="width: 120px">
            <el-option label="成功" value="true" />
            <el-option label="失败" value="false" />
          </el-select>
          <el-input v-model="queryFilters.username" clearable placeholder="操作用户" style="width: 140px" />
        </template>
        <el-button type="primary" :loading="loading" @click="onSearch">查询</el-button>
        <el-button :loading="loading" @click="onReset">重置</el-button>
      </div>
      <el-alert
        v-if="historyError"
        class="history-alert"
        type="error"
        :closable="false"
        show-icon
        :title="historyError"
      />
      <el-table :data="rows" stripe size="small" v-loading="loading" @row-dblclick="openDetail">
        <el-table-column prop="created_at_cn" label="操作时间" width="180" />
        <el-table-column prop="username" label="操作用户" width="140" />
        <el-table-column prop="db_type" label="类型" width="110" />
        <el-table-column prop="business_line" label="项目" width="120" />
        <el-table-column prop="environment" label="环境" width="100" />
        <el-table-column prop="cluster_name" label="集群" min-width="150" />
        <el-table-column prop="instance_name" label="实例" min-width="150" />
        <el-table-column v-if="activeTab === 'query'" prop="database_name" label="数据库" min-width="130" />
        <el-table-column prop="statement" label="SQL/命令" min-width="320" show-overflow-tooltip />
        <el-table-column v-if="activeTab === 'query'" prop="duration_ms" label="耗时" width="100">
          <template #default="{ row }">{{ row.duration_ms }} ms</template>
        </el-table-column>
        <el-table-column v-if="activeTab === 'query'" prop="result_row_count" label="结果行数" width="100" />
        <el-table-column label="结果" width="90">
          <template #default="{ row }">
            <el-tag :type="row.success ? 'success' : 'danger'">{{ row.success ? "成功" : "失败" }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="activeTab === 'query'" label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click.stop="openDetail(row)">详情</el-button>
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

    <el-drawer v-model="detailVisible" title="查询审计详情" size="82%" destroy-on-close>
      <div v-loading="detailLoading" class="detail-body">
        <template v-if="detail">
          <el-descriptions :column="3" border size="small">
            <el-descriptions-item label="操作时间">{{ detail.created_at_cn || "-" }}</el-descriptions-item>
            <el-descriptions-item label="操作用户">{{ detail.username || "-" }}</el-descriptions-item>
            <el-descriptions-item label="执行状态">
              <el-tag :type="detail.success ? 'success' : 'danger'">{{ detail.success ? "成功" : "失败" }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="数据库类型">{{ detail.db_type || "-" }}</el-descriptions-item>
            <el-descriptions-item label="项目/环境">{{ detail.business_line || "-" }} / {{ detail.environment || "-" }}</el-descriptions-item>
            <el-descriptions-item label="集群/实例">{{ detail.cluster_name || "-" }} / {{ detail.instance_name || "-" }}</el-descriptions-item>
            <el-descriptions-item label="数据库">{{ detail.database_name || "-" }}</el-descriptions-item>
            <el-descriptions-item label="耗时">{{ detail.duration_ms }} ms</el-descriptions-item>
            <el-descriptions-item label="结果行数">
              {{ detail.result_row_count }}
              <el-tag v-if="detail.result_truncated" type="warning" size="small">最多保留1000条</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="客户端IP">{{ detail.client_ip || "-" }}</el-descriptions-item>
            <el-descriptions-item label="执行ID" :span="2">{{ detail.execution_id || "-" }}</el-descriptions-item>
            <el-descriptions-item v-if="detail.error" label="失败信息" :span="3">
              <span class="error-text">{{ detail.error }}</span>
            </el-descriptions-item>
          </el-descriptions>

          <div class="section-title">
            <span>查询内容</span>
            <el-button size="small" @click="copyText(detail.statement, '查询内容')">复制</el-button>
          </div>
          <pre class="code-block">{{ detail.statement || "-" }}</pre>

          <el-tabs v-model="detailTab">
            <el-tab-pane label="查询结果" name="result">
              <el-empty v-if="!detail.result || !resultRows.length" description="该请求没有查询结果或结果为空" />
              <template v-else-if="isRelationalResult">
                <el-table :data="pagedResultRows" border stripe size="small" max-height="520">
                  <el-table-column
                    v-for="column in resultColumns"
                    :key="column"
                    :prop="column"
                    :label="column"
                    min-width="150"
                    show-overflow-tooltip
                  >
                    <template #default="{ row }">{{ formatCell(row[column]) }}</template>
                  </el-table-column>
                </el-table>
                <div class="result-pagination">
                  <el-pagination
                    v-model:current-page="resultPage"
                    v-model:page-size="resultPageSize"
                    :page-sizes="[20, 50, 100]"
                    :total="resultRows.length"
                    layout="total, sizes, prev, pager, next"
                    background
                  />
                </div>
              </template>
              <pre v-else class="json-block">{{ formattedResult }}</pre>
            </el-tab-pane>
            <el-tab-pane label="原始JSON" name="json">
              <div class="copy-row">
                <el-button size="small" @click="copyText(formattedResult, '查询结果')">复制结果</el-button>
              </div>
              <pre class="json-block">{{ formattedResult }}</pre>
            </el-tab-pane>
            <el-tab-pane label="请求上下文" name="request">
              <pre class="json-block">{{ formattedRequest }}</pre>
            </el-tab-pane>
          </el-tabs>
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

import { getQueryHistoryDetail, listChangeHistory, listQueryHistory } from "../api/modules/data_access";
import { useTabActivationRefresh } from "../composables/useTabActivationRefresh";

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
const historyError = ref("");
const queryFilters = reactive({ db_type: "", success: "", username: "" });

const page = ref(1);
const pageSize = ref(10);
const detailVisible = ref(false);
const detailLoading = ref(false);
const detail = ref(null);
const detailTab = ref("result");
const resultPage = ref(1);
const resultPageSize = ref(20);

const resultRows = computed(() => Array.isArray(detail.value?.result?.rows) ? detail.value.result.rows : []);
const resultColumns = computed(() => {
  const configured = detail.value?.result?.columns;
  if (Array.isArray(configured) && configured.length) return configured;
  const names = new Set();
  resultRows.value.forEach((row) => {
    if (row && typeof row === "object" && !Array.isArray(row)) Object.keys(row).forEach((key) => names.add(key));
  });
  return [...names];
});
const isRelationalResult = computed(() =>
  ["mysql", "postgresql"].includes(detail.value?.db_type)
  && resultRows.value.every((row) => row && typeof row === "object" && !Array.isArray(row)),
);
const pagedResultRows = computed(() => {
  const start = (resultPage.value - 1) * resultPageSize.value;
  return resultRows.value.slice(start, start + resultPageSize.value);
});
const formattedResult = computed(() => JSON.stringify(detail.value?.result ?? null, null, 2));
const formattedRequest = computed(() => JSON.stringify(detail.value?.request ?? {}, null, 2));

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
  historyError.value = "";
  try {
    syncTabFromPager();
    const fetcher = activeTab.value === "change" ? listChangeHistory : listQueryHistory;
    const filters = {
      keyword: keyword.value.trim() || undefined,
      start_date: dateRange.value?.[0] || undefined,
      end_date: dateRange.value?.[1] || undefined,
    };
    if (activeTab.value === "query") {
      filters.db_type = queryFilters.db_type || undefined;
      filters.success = queryFilters.success || undefined;
      filters.username = queryFilters.username.trim() || undefined;
    }
    const { data } = await fetcher(page.value, pageSize.value, filters);
    const result = data?.data || {};
    rows.value = result.items || [];
    total.value = result.total || 0;
  } catch (error) {
    const message = error.response?.data?.message || "加载历史记录失败";
    historyError.value = message;
    rows.value = [];
    total.value = 0;
    ElMessage.error(message);
  } finally {
    loading.value = false;
  }
}

async function openDetail(row) {
  if (activeTab.value !== "query" || !row?.event_id) return;
  detailVisible.value = true;
  detailLoading.value = true;
  detail.value = null;
  detailTab.value = "result";
  resultPage.value = 1;
  try {
    const { data } = await getQueryHistoryDetail(row.event_id);
    detail.value = data?.data || null;
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载查询审计详情失败");
    detailVisible.value = false;
  } finally {
    detailLoading.value = false;
  }
}

async function copyText(value, label) {
  try {
    await navigator.clipboard.writeText(String(value ?? ""));
    ElMessage.success(`${label}已复制`);
  } catch (_error) {
    ElMessage.error("复制失败，请手动复制");
  }
}

function formatCell(value) {
  if (value === null || value === undefined) return "NULL";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
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
  queryFilters.db_type = "";
  queryFilters.success = "";
  queryFilters.username = "";
  page.value = 1;
  syncTabFromPager();
  await loadHistory();
}

onMounted(loadHistory);
useTabActivationRefresh(loadHistory);
</script>

<style scoped>
.page { padding: 20px; }
.header-row { display: flex; justify-content: space-between; align-items: center; }
.pagination-row, .result-pagination { margin-top: 12px; display: flex; justify-content: flex-end; }
.filter-row { margin-bottom: 12px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.history-alert { margin-bottom: 12px; }
.detail-body { min-height: 240px; }
.section-title { margin: 20px 0 8px; display: flex; justify-content: space-between; align-items: center; font-weight: 600; }
.code-block, .json-block { margin: 0; padding: 14px; border-radius: 6px; background: #f6f8fa; border: 1px solid #e4e7ed; white-space: pre-wrap; word-break: break-word; max-height: 520px; overflow: auto; font-family: Consolas, Monaco, monospace; font-size: 13px; line-height: 1.6; }
.copy-row { margin-bottom: 8px; display: flex; justify-content: flex-end; }
.error-text { color: #f56c6c; white-space: pre-wrap; }
</style>
