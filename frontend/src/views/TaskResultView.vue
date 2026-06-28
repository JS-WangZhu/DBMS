<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>结果查询</span>
          <el-button :loading="loading" @click="loadData">刷新</el-button>
        </div>
      </template>

      <div class="toolbar">
        <el-input
          v-model="filters.task_name"
          clearable
          placeholder="任务名称"
          style="width: 220px"
          @clear="onFilterChange"
          @change="onFilterChange"
        />
        <el-button type="primary" @click="onFilterChange">搜索</el-button>
        <el-select v-model="filters.task_type" clearable placeholder="任务类型" style="width: 160px" @change="onFilterChange">
          <el-option label="Shell脚本" value="shell" />
          <el-option label="Python脚本" value="python" />
          <el-option label="HTTP请求" value="http" />
          <el-option label="SQL请求" value="sql" />
        </el-select>
        <el-select v-model="filters.status" clearable placeholder="状态" style="width: 140px" @change="onFilterChange">
          <el-option label="运行中" value="running" />
          <el-option label="成功" value="success" />
          <el-option label="失败" value="failed" />
        </el-select>
        <el-button type="danger" plain :disabled="!selectedRows.length" @click="deleteSelected">
          删除所选
        </el-button>
      </div>

      <el-table :data="rows" stripe v-loading="loading" @selection-change="onSelectionChange">
        <el-table-column type="selection" width="48" />
        <el-table-column prop="task_name" label="任务名称" min-width="180" show-overflow-tooltip />
        <el-table-column label="类型" width="110">
          <template #default="{ row }">{{ taskTypeText(row.task_type) }}</template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="statusType(row.status)">{{ statusText(row.status) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="trigger_type" label="触发" width="90" />
        <el-table-column prop="attempt" label="次数" width="70" />
        <el-table-column label="开始时间" min-width="170">
          <template #default="{ row }">{{ formatDateTime(row.started_at) }}</template>
        </el-table-column>
        <el-table-column label="耗时" width="100">
          <template #default="{ row }">{{ row.duration_ms == null ? "-" : `${row.duration_ms} ms` }}</template>
        </el-table-column>
        <el-table-column prop="error_message" label="错误" min-width="220" show-overflow-tooltip />
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
            <el-button v-if="row.status === 'failed'" link type="warning" @click="retry(row)">重试</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          background
          layout="total, prev, pager, next"
          :total="pager.total"
          :current-page="pager.page"
          :page-size="pager.page_size"
          @current-change="onPageChange"
        />
      </div>
    </el-card>

    <el-drawer v-model="detailVisible" title="执行详情" size="56%">
      <template v-if="detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="任务">{{ detail.task_name }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ statusText(detail.status) }}</el-descriptions-item>
          <el-descriptions-item label="开始">{{ formatDateTime(detail.started_at) }}</el-descriptions-item>
          <el-descriptions-item label="结束">{{ formatDateTime(detail.finished_at) }}</el-descriptions-item>
        </el-descriptions>
        <h4>标准输出</h4>
        <pre>{{ detail.stdout || "-" }}</pre>
        <h4>错误输出</h4>
        <pre>{{ detail.stderr || detail.error_message || "-" }}</pre>
        <h4>结构化结果</h4>
        <pre>{{ JSON.stringify(detail.result_json || {}, null, 2) }}</pre>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { deleteTaskResults, getTaskResult, listTaskResults, retryTaskResult } from "../api/modules/tasks";

const loading = ref(false);
const rows = ref([]);
const selectedRows = ref([]);
const detail = ref(null);
const detailVisible = ref(false);
const filters = reactive({ task_name: "", task_type: "", status: "" });
const pager = reactive({ page: 1, page_size: 10, total: 0 });

function taskTypeText(type) {
  return { shell: "Shell脚本", python: "Python脚本", http: "HTTP请求", sql: "SQL请求" }[type] || type;
}
function statusText(status) {
  return { running: "运行中", success: "成功", failed: "失败" }[status] || status;
}
function statusType(status) {
  return { running: "info", success: "success", failed: "danger" }[status] || "info";
}
function formatDateTime(value) {
  if (!value) return "-";
  const source = String(value);
  const normalized = /[zZ]|[+-]\d{2}:\d{2}$/.test(source) ? source : `${source}Z`;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}

async function loadData() {
  loading.value = true;
  try {
    const params = { page: pager.page, page_size: pager.page_size };
    if (filters.task_name) params.task_name = filters.task_name;
    if (filters.task_type) params.task_type = filters.task_type;
    if (filters.status) params.status = filters.status;
    const { data } = await listTaskResults(params);
    rows.value = data?.data?.items || [];
    pager.total = Number(data?.data?.total || 0);
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载结果失败");
  } finally {
    loading.value = false;
  }
}

async function openDetail(row) {
  const { data } = await getTaskResult(row.id);
  detail.value = data?.data || row;
  detailVisible.value = true;
}

async function retry(row) {
  await retryTaskResult(row.id);
  ElMessage.success("已发起重试");
  await loadData();
}

function onSelectionChange(selection) {
  selectedRows.value = selection || [];
}

async function deleteSelected() {
  const ids = selectedRows.value.map((item) => item.id);
  if (!ids.length) return;
  await ElMessageBox.confirm(`确认删除选中的 ${ids.length} 条调度结果？`, "删除确认", { type: "warning" });
  await deleteTaskResults(ids);
  ElMessage.success("已删除");
  selectedRows.value = [];
  if (rows.value.length === ids.length && pager.page > 1) {
    pager.page -= 1;
  }
  await loadData();
}

async function onFilterChange() {
  pager.page = 1;
  await loadData();
}
async function onPageChange(page) {
  pager.page = Number(page) || 1;
  await loadData();
}

onMounted(loadData);
</script>

<style scoped>
.page { padding: 20px; }
.header-row { display: flex; justify-content: space-between; align-items: center; }
.toolbar { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 12px; }
.pagination-wrap { margin-top: 12px; display: flex; justify-content: flex-end; }
pre { white-space: pre-wrap; word-break: break-word; background: #f6f8fa; padding: 12px; border-radius: 6px; }
</style>
