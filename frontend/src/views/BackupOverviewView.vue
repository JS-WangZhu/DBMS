<template>
  <div class="page">
    <el-row :gutter="16" class="summary-row">
      <el-col :xs="12" :sm="6">
        <el-card shadow="never" class="summary-card">
          <div class="summary-label">总集群数量</div>
          <div class="summary-value">{{ summary.total_clusters }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="never" class="summary-card normal-card">
          <div class="summary-label">备份集正常</div>
          <div class="summary-value">{{ summary.normal_backup_sets }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="never" class="summary-card abnormal-card">
          <div class="summary-label">备份集异常</div>
          <div class="summary-value">{{ summary.abnormal_backup_sets }}</div>
        </el-card>
      </el-col>
      <el-col :xs="12" :sm="6">
        <el-card shadow="never" class="summary-card">
          <div class="summary-label">总体正常比例</div>
          <div class="ratio-row">
            <div class="summary-value">{{ formatRatio(summary.normal_ratio) }}</div>
            <el-progress
              class="ratio-progress"
              :percentage="summary.normal_ratio"
              :show-text="false"
              :stroke-width="8"
              color="#67c23a"
            />
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-card shadow="never" class="detail-card">
      <template #header>
        <div class="header-row">
          <div>
            <div class="header-title">集群备份详情</div>
            <div class="header-subtitle">统计最近 48 小时；集群内任意节点存在成功备份即视为备份正常</div>
          </div>
          <el-button type="primary" :icon="Refresh" :loading="loading" @click="loadOverview">刷新</el-button>
        </div>
      </template>

      <div class="filter-row">
        <el-select v-model="businessFilter" filterable clearable placeholder="筛选业务" class="business-filter">
          <el-option
            v-for="item in businessOptions"
            :key="item"
            :label="item === '__unset__' ? '未设置' : item"
            :value="item"
          />
        </el-select>
        <el-select v-model="dbTypeFilter" clearable placeholder="筛选数据库类型" class="db-type-filter">
          <el-option v-for="item in dbTypeOptions" :key="item" :label="dbTypeLabel(item)" :value="item" />
        </el-select>
        <el-select
          v-model="clusterFilter"
          filterable
          clearable
          placeholder="筛选集群"
          class="cluster-filter"
        >
          <el-option
            v-for="item in clusterOptions"
            :key="item.cluster_id"
            :label="buildClusterLabel(item, Boolean(dbTypeFilter))"
            :value="item.cluster_id"
          />
        </el-select>
        <el-select v-model="resultFilter" clearable placeholder="筛选备份结果" class="result-filter">
          <el-option label="正常" value="normal" />
          <el-option label="异常" value="abnormal" />
        </el-select>
        <span class="filter-count">共 {{ filteredItems.length }} 个集群</span>
      </div>

      <el-table v-loading="loading" :data="paginatedItems" stripe>
        <el-table-column prop="cluster_name" label="集群名称" min-width="180">
          <template #default="{ row }">
            <div class="primary-text">{{ row.cluster_name }}</div>
            <div class="secondary-text">ID: {{ row.cluster_id }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="db_type" label="数据库类型" width="130">
          <template #default="{ row }">{{ dbTypeLabel(row.db_type) }}</template>
        </el-table-column>
        <el-table-column label="业务 / 环境" min-width="170">
          <template #default="{ row }">
            <div>{{ row.business_line || "-" }}</div>
            <div class="secondary-text">{{ row.environment || "-" }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="backup_status" label="备份结果" width="120">
          <template #default="{ row }">
            <el-tag :type="row.backup_status === 'normal' ? 'success' : 'danger'" effect="light">
              {{ row.backup_status === "normal" ? "正常" : "异常" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="48 小时内最新备份情况" min-width="310">
          <template #default="{ row }">
            <div v-if="row.latest_backup" class="latest-backup">
              <el-tag :type="latestStatusType(row.latest_backup.status)" size="small">
                {{ latestStatusLabel(row.latest_backup.status) }}
              </el-tag>
              <div>
                <div class="primary-text">
                  {{ row.latest_backup.instance_name || "-" }}
                  <span class="policy-name">· {{ row.latest_backup.policy_name || "-" }}</span>
                </div>
                <div class="secondary-text">{{ formatDateTime(row.latest_backup.started_at) }}</div>
                <el-tooltip
                  v-if="row.latest_backup.error_message"
                  :content="row.latest_backup.error_message"
                  placement="top"
                >
                  <div class="error-text">{{ row.latest_backup.error_message }}</div>
                </el-tooltip>
              </div>
            </div>
            <span v-else class="no-backup">48 小时内无备份记录</span>
          </template>
        </el-table-column>
        <el-table-column prop="successful_backup_count" label="成功次数" width="100" align="center" />
        <template #empty>
          <el-empty description="暂无符合条件的集群" :image-size="90" />
        </template>
      </el-table>
      <div class="pagination-row">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          :total="filteredItems.length"
          layout="total, sizes, prev, pager, next, jumper"
          background
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { Refresh } from "@element-plus/icons-vue";

import { backupOverview } from "../api/modules/backups";
import {
  buildClusterLabel,
  dbTypeDisplayName,
  filterClusterOptions,
} from "./backupOverviewFilters";

const loading = ref(false);
const clusterFilter = ref(null);
const businessFilter = ref("");
const dbTypeFilter = ref("");
const resultFilter = ref("");
const currentPage = ref(1);
const pageSize = ref(10);
const summary = reactive({
  total_clusters: 0,
  normal_backup_sets: 0,
  abnormal_backup_sets: 0,
  normal_ratio: 0,
  items: [],
});

const clusterOptions = computed(() =>
  filterClusterOptions(summary.items, {
    business: businessFilter.value,
    dbType: dbTypeFilter.value,
    result: resultFilter.value,
  })
);
const businessOptions = computed(() =>
  [...new Set((summary.items || []).map((item) => item.business_line || "__unset__"))].sort()
);
const dbTypeOptions = computed(() =>
  [...new Set((summary.items || []).map((item) => item.db_type).filter(Boolean))].sort()
);
const filteredItems = computed(() =>
  (summary.items || []).filter((item) => {
    const matchesCluster = !clusterFilter.value || item.cluster_id === clusterFilter.value;
    const matchesBusiness =
      !businessFilter.value ||
      (businessFilter.value === "__unset__" ? !item.business_line : item.business_line === businessFilter.value);
    const matchesDbType = !dbTypeFilter.value || item.db_type === dbTypeFilter.value;
    const matchesResult = !resultFilter.value || item.backup_status === resultFilter.value;
    return matchesCluster && matchesBusiness && matchesDbType && matchesResult;
  })
);
const paginatedItems = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return filteredItems.value.slice(start, start + pageSize.value);
});

watch([clusterFilter, businessFilter, dbTypeFilter, resultFilter, pageSize], () => {
  currentPage.value = 1;
});

watch(clusterOptions, (options) => {
  if (clusterFilter.value && !options.some((item) => item.cluster_id === clusterFilter.value)) {
    clusterFilter.value = null;
  }
});

function formatRatio(value) {
  const number = Number(value || 0);
  return (Number.isInteger(number) ? number : number.toFixed(2)) + "%";
}

function dbTypeLabel(value) {
  return dbTypeDisplayName(value);
}

function latestStatusLabel(status) {
  return {
    success: "成功",
    failed: "失败",
    running: "进行中",
  }[status] || status || "未知";
}

function latestStatusType(status) {
  return {
    success: "success",
    failed: "danger",
    running: "warning",
  }[status] || "info";
}

function formatDateTime(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
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

async function loadOverview() {
  loading.value = true;
  try {
    const { data } = await backupOverview(48);
    const result = data.data || {};
    summary.total_clusters = result.total_clusters || 0;
    summary.normal_backup_sets = result.normal_backup_sets || 0;
    summary.abnormal_backup_sets = result.abnormal_backup_sets || 0;
    summary.normal_ratio = Number(result.normal_ratio || 0);
    summary.items = result.items || [];
    currentPage.value = 1;
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载备份总览失败");
  } finally {
    loading.value = false;
  }
}

onMounted(loadOverview);
</script>

<style scoped>
.page {
  padding: 20px;
}

.summary-row {
  margin-bottom: 16px;
}

.summary-card {
  height: 126px;
  border: 1px solid #e4e7ed;
}

.summary-card :deep(.el-card__body) {
  height: 100%;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.normal-card {
  border-left: 4px solid #67c23a;
}

.abnormal-card {
  border-left: 4px solid #f56c6c;
}

.summary-label {
  color: #909399;
  font-size: 14px;
  margin-bottom: 10px;
}

.summary-value {
  color: #303133;
  font-size: 30px;
  font-weight: 600;
  line-height: 1;
}

.ratio-row {
  display: flex;
  align-items: center;
  gap: 14px;
}

.ratio-progress {
  flex: 1;
}

.detail-card {
  border: 1px solid #e4e7ed;
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.header-title {
  color: #303133;
  font-size: 16px;
  font-weight: 600;
}

.header-subtitle {
  color: #909399;
  font-size: 13px;
  margin-top: 5px;
}

.filter-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.cluster-filter {
  width: 240px;
}

.result-filter {
  width: 180px;
}

.business-filter,
.db-type-filter {
  width: 190px;
}

.filter-count {
  color: #909399;
  font-size: 13px;
}

.primary-text {
  color: #303133;
  line-height: 22px;
}

.secondary-text {
  color: #909399;
  font-size: 12px;
  line-height: 20px;
}

.latest-backup {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.policy-name {
  color: #606266;
}

.error-text {
  max-width: 360px;
  overflow: hidden;
  color: #f56c6c;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.no-backup {
  color: #a8abb2;
}

.pagination-row {
  display: flex;
  justify-content: flex-end;
  margin-top: 18px;
}

@media (max-width: 768px) {
  .page {
    padding: 12px;
  }

  .summary-row :deep(.el-col) {
    margin-bottom: 12px;
  }

  .filter-row {
    align-items: stretch;
    flex-direction: column;
  }

  .cluster-filter,
  .business-filter,
  .db-type-filter,
  .result-filter {
    width: 100%;
  }
}
</style>
