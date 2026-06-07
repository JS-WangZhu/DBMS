<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>巡检管理</span>
          <div class="header-actions">
            <el-button type="primary" :loading="running" @click="runNow">立即巡检</el-button>
            <el-button :loading="loading" @click="loadData">刷新</el-button>
          </div>
        </div>
      </template>

      <div class="toolbar">
        <el-select v-model="filters.db_type" clearable placeholder="数据库类型" style="width: 160px" @change="onFilterChange">
          <el-option label="MySQL" value="mysql" />
          <el-option label="MongoDB" value="mongodb" />
          <el-option label="Redis" value="redis" />
          <el-option label="Doris" value="doris" />
        </el-select>
        <el-select v-model="filters.status" clearable placeholder="巡检状态" style="width: 160px" @change="onFilterChange">
          <el-option label="异常" value="abnormal" />
          <el-option label="正常" value="normal" />
        </el-select>
      </div>

      <div class="summary">
        <el-tag type="info">总数 {{ summary.total || 0 }}</el-tag>
        <el-tag type="danger">异常 {{ summary.abnormal || 0 }}</el-tag>
        <el-tag type="success">正常 {{ summary.normal || 0 }}</el-tag>
      </div>

      <el-table :data="rows" stripe v-loading="loading">
        <el-table-column prop="db_type" label="类型" width="100" />
        <el-table-column label="业务/环境" min-width="180">
          <template #default="{ row }">
            {{ row.business_line || "-" }}/{{ row.environment || "-" }}
          </template>
        </el-table-column>
        <el-table-column prop="cluster_name" label="集群" min-width="180" show-overflow-tooltip />
        <el-table-column prop="instance_name" label="实例" min-width="200" show-overflow-tooltip />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.inspection_status === 'abnormal' ? 'danger' : 'success'">
              {{ row.inspection_status === "abnormal" ? "异常" : "正常" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="异常项" min-width="300" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="!row.issues?.length">-</span>
            <span v-else>{{ row.issues.map((item) => item.issue_name).join("、") }}</span>
          </template>
        </el-table-column>
        <el-table-column label="采集时间" min-width="180">
          <template #default="{ row }">{{ formatDateTime(row.collected_at) }}</template>
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
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { getInspectionOverview, runInspectionNow } from "../api/modules/inspection";

const loading = ref(false);
const running = ref(false);
const rows = ref([]);
const summary = ref({});
const filters = reactive({
  db_type: "",
  status: "",
});
const pager = reactive({
  page: 1,
  page_size: 10,
  total: 0,
});

function formatDateTime(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

async function loadData() {
  loading.value = true;
  try {
    const params = {};
    if (filters.db_type) {
      params.db_type = filters.db_type;
    }
    if (filters.status) {
      params.status = filters.status;
    }
    params.page = pager.page;
    params.page_size = pager.page_size;
    const { data } = await getInspectionOverview(params);
    rows.value = data?.data?.items || [];
    summary.value = data?.data?.summary || {};
    pager.total = Number(data?.data?.total || 0);
    pager.page = Number(data?.data?.page || pager.page);
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载巡检数据失败");
  } finally {
    loading.value = false;
  }
}

async function runNow() {
  running.value = true;
  try {
    const { data } = await runInspectionNow();
    if (data?.data?.already_running) {
      ElMessage.warning(data.message || "巡检正在执行中，请稍后查看结果");
    } else {
      ElMessage.success("巡检任务已执行");
    }
    pager.page = 1;
    await loadData();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "执行巡检失败");
  } finally {
    running.value = false;
  }
}

async function onPageChange(page) {
  pager.page = Number(page) || 1;
  await loadData();
}

async function onFilterChange() {
  pager.page = 1;
  await loadData();
}

onMounted(loadData);
</script>

<style scoped>
.page { padding: 20px; }
.header-row { display: flex; justify-content: space-between; align-items: center; }
.header-actions { display: flex; gap: 10px; }
.toolbar { display: flex; gap: 10px; margin-bottom: 12px; }
.summary { display: flex; gap: 8px; margin-bottom: 12px; }
.pagination-wrap { margin-top: 12px; display: flex; justify-content: flex-end; }
</style>
