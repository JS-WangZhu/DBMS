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
          <el-option label="PostgreSQL" value="postgresql" />
          <el-option label="Doris" value="doris" />
          <el-option label="Agent" value="agent" />
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
        <el-table-column label="类型" width="100">
          <template #default="{ row }">{{ row.db_type === "agent" ? "Agent" : row.db_type }}</template>
        </el-table-column>
        <el-table-column label="业务/环境" min-width="180">
          <template #default="{ row }">
            {{ row.business_line || "-" }}/{{ row.environment || "-" }}
          </template>
        </el-table-column>
        <el-table-column prop="cluster_name" label="集群/地址" min-width="180" show-overflow-tooltip />
        <el-table-column prop="instance_name" label="实例/Agent" min-width="200" show-overflow-tooltip />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.inspection_status === 'abnormal' ? 'danger' : 'success'">
              {{ row.inspection_status === "abnormal" ? "异常" : "正常" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="异常子项" min-width="460">
          <template #default="{ row }">
            <span v-if="!row.issues?.length">-</span>
            <div v-else class="issue-list">
              <div v-for="item in row.issues" :key="item.id || item.issue_key" class="issue-item">
                <el-tag :type="item.severity === 'critical' ? 'danger' : 'warning'" size="small">
                  {{ item.issue_name }}
                </el-tag>
                <span class="issue-message" :title="item.message">{{ item.message || "-" }}</span>
                <el-tag v-if="isIssueMuted(item)" type="info" size="small">
                  已屏蔽至 {{ formatDateTime(item.muted_until) }}
                </el-tag>
                <el-button
                  v-if="item.id"
                  link
                  :type="isIssueMuted(item) ? 'success' : 'primary'"
                  :loading="mutingAlertId === item.id"
                  @click.stop="toggleIssueMute(item)"
                >
                  {{ isIssueMuted(item) ? "解除屏蔽" : "屏蔽" }}
                </el-button>
              </div>
            </div>
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

    <el-dialog
      v-model="muteDialog.visible"
      :title="`屏蔽：${muteDialog.issue?.issue_name || ''}`"
      width="480px"
      append-to-body
      :close-on-click-modal="!muteDialog.submitting"
    >
      <p class="mute-dialog-help">请选择屏蔽时长。屏蔽期间异常仍会记录，但不会发送告警。</p>
      <div class="mute-duration-row">
        <el-input-number
          v-model="muteDialog.amount"
          :min="1"
          :max="muteUnitOptions.find((item) => item.value === muteDialog.unit)?.max || 1"
          :precision="0"
          controls-position="right"
        />
        <el-select v-model="muteDialog.unit" class="mute-unit-select">
          <el-option v-for="option in muteUnitOptions" :key="option.value" :label="option.label" :value="option.value" />
        </el-select>
      </div>
      <template #footer>
        <el-button :disabled="muteDialog.submitting" @click="muteDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="muteDialog.submitting" @click="confirmIssueMute">确认屏蔽</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { getInspectionOverview, muteInspectionAlert, runInspectionNow } from "../api/modules/inspection";

const loading = ref(false);
const running = ref(false);
const mutingAlertId = ref(null);
const rows = ref([]);
const summary = ref({});
const muteDialog = reactive({
  visible: false,
  issue: null,
  amount: 1,
  unit: "hour",
  submitting: false,
});
const muteUnitOptions = [
  { label: "小时", value: "hour", minutes: 60, max: 8760 },
  { label: "天", value: "day", minutes: 1440, max: 365 },
  { label: "周", value: "week", minutes: 10080, max: 52 },
  { label: "月（30天）", value: "month", minutes: 43200, max: 12 },
];
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

function isIssueMuted(issue) {
  if (!issue?.muted_until) return false;
  const until = new Date(issue.muted_until).getTime();
  return Number.isFinite(until) && until > Date.now();
}

async function toggleIssueMute(issue) {
  if (!issue?.id) return;
  if (!isIssueMuted(issue)) {
    muteDialog.issue = issue;
    muteDialog.amount = 1;
    muteDialog.unit = "hour";
    muteDialog.visible = true;
    return;
  }

  mutingAlertId.value = issue.id;
  try {
    await ElMessageBox.confirm(`确认解除“${issue.issue_name}”的告警屏蔽吗？`, "解除屏蔽", {
      type: "warning",
    });
    await muteInspectionAlert(issue.id, 0);
    ElMessage.success("已解除屏蔽");
    await loadData();
  } catch (error) {
    if (error === "cancel" || error === "close") return;
    ElMessage.error(error.response?.data?.message || "设置屏蔽失败");
  } finally {
    mutingAlertId.value = null;
  }
}

async function confirmIssueMute() {
  const issue = muteDialog.issue;
  const amount = Number(muteDialog.amount);
  const unit = muteUnitOptions.find((item) => item.value === muteDialog.unit);
  if (!issue?.id || !Number.isInteger(amount) || amount <= 0 || !unit) {
    ElMessage.warning("请输入大于0的整数时长");
    return;
  }

  muteDialog.submitting = true;
  mutingAlertId.value = issue.id;
  try {
    await muteInspectionAlert(issue.id, amount * unit.minutes);
    ElMessage.success("屏蔽设置成功");
    muteDialog.visible = false;
    await loadData();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "设置屏蔽失败");
  } finally {
    muteDialog.submitting = false;
    mutingAlertId.value = null;
  }
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
.issue-list { display: flex; flex-direction: column; gap: 6px; }
.issue-item { display: flex; align-items: center; gap: 8px; min-width: 0; }
.issue-message { flex: 1; min-width: 80px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mute-dialog-help { margin: 0 0 16px; color: #606266; line-height: 1.6; }
.mute-duration-row { display: flex; gap: 12px; }
.mute-duration-row :deep(.el-input-number) { flex: 1; width: auto; }
.mute-unit-select { width: 140px; }
</style>
