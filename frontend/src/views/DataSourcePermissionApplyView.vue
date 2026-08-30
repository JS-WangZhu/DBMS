<template>
  <div class="permission-apply-page">
    <el-card shadow="never">
      <template #header>
        <div class="page-header">
          <div><h2>生产数据库权限申请</h2><p>自主申请生产数据库查询、变更权限；执行权限不在此流程内。</p></div>
          <el-button :loading="loading" @click="refreshAll">刷新</el-button>
        </div>
      </template>
      <el-tabs v-model="activeTab">
        <el-tab-pane v-if="!isAdmin" label="申请权限" name="apply">
          <el-alert title="审核通过后，权限将写入用户管理的数据源权限，并参与最终有效权限计算。" type="info" :closable="false" show-icon />
          <div class="filters">
            <el-input v-model="filters.keyword" clearable placeholder="搜索数据源、项目或环境" />
            <el-select v-model="filters.project" clearable filterable placeholder="全部项目"><el-option v-for="item in projects" :key="item" :label="item" :value="item" /></el-select>
            <el-select v-model="filters.dbType" clearable filterable placeholder="全部数据库类型"><el-option v-for="item in dbTypes" :key="item" :label="item.toUpperCase()" :value="item" /></el-select>
            <el-button @click="toggleFiltered(true)">选择筛选结果</el-button>
            <el-button @click="toggleFiltered(false)">清除筛选结果</el-button>
          </div>
          <el-table :data="filteredClusters" stripe row-key="id" empty-text="未找到生产环境数据源" table-layout="fixed">
            <el-table-column label="选择" width="72" align="center"><template #default="{ row }"><el-checkbox :model-value="isSelected(row.id)" :disabled="nothingAvailable(row)" @change="toggleRow(row, $event)" /></template></el-table-column>
            <el-table-column prop="name" label="数据源" min-width="190" />
            <el-table-column prop="project" label="项目" min-width="150" />
            <el-table-column label="数据库类型" width="130"><template #default="{ row }"><el-tag effect="plain">{{ row.db_type.toUpperCase() }}</el-tag></template></el-table-column>
            <el-table-column prop="environment" label="环境" width="110" />
            <el-table-column label="申请查询" width="150" align="center" header-align="center" class-name="permission-request-column" label-class-name="permission-request-header"><template #default="{ row }"><div class="permission-switch"><el-switch :model-value="permissionSwitchValue(row.id, 'can_query')" :disabled="hasPermission(row.id, 'can_query')" @change="setPermission(row, 'can_query', $event)" /><span v-if="hasPermission(row.id, 'can_query')">已拥有</span></div></template></el-table-column>
            <el-table-column label="申请变更" width="150" align="center" header-align="center" class-name="permission-request-column" label-class-name="permission-request-header"><template #default="{ row }"><div class="permission-switch"><el-switch :model-value="permissionSwitchValue(row.id, 'can_change')" :disabled="hasPermission(row.id, 'can_change')" @change="setPermission(row, 'can_change', $event)" /><span v-if="hasPermission(row.id, 'can_change')">已拥有</span></div></template></el-table-column>
            <el-table-column label="当前有效权限" min-width="160"><template #default="{ row }"><el-tag v-if="hasPermission(row.id, 'can_query')" type="success">查询</el-tag><el-tag v-if="hasPermission(row.id, 'can_change')" type="danger">变更</el-tag><span v-if="!hasPermission(row.id, 'can_query') && !hasPermission(row.id, 'can_change')">-</span></template></el-table-column>
          </el-table>
          <div class="submit-panel">
            <div class="expiry-picker">
              <span>权限持有至</span>
              <el-button-group>
                <el-button v-for="option in expiryOptions" :key="option.label" :type="requestedExpiresAt === option.value() ? 'primary' : 'default'" @click="requestedExpiresAt = option.value()">{{ option.label }}</el-button>
              </el-button-group>
              <el-date-picker v-model="requestedExpiresAt" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" :default-time="defaultExpiryTime" :disabled-date="disablePastDate" placeholder="选择到期日期和时间" />
              <span class="expiry-hint">北京时间，到期后自动回收直接授权</span>
            </div>
            <el-input v-model="reason" type="textarea" :rows="3" maxlength="500" show-word-limit placeholder="请填写权限用途和申请原因" />
            <div class="submit-actions"><span>已选择 {{ selectedItems.length }} 个数据源</span><el-button type="primary" :loading="submitting" :disabled="!selectedItems.length" @click="submitApplication">提交申请</el-button></div>
          </div>
        </el-tab-pane>
        <el-tab-pane :label="isAdmin ? '权限审核' : '我的申请'" name="history">
          <div class="history-filters">
            <el-select v-model="historyFilters.status" clearable placeholder="全部状态" @change="loadApplications"><el-option label="待审核" value="pending" /><el-option label="已通过" value="approved" /><el-option label="已驳回" value="rejected" /></el-select>
            <el-input v-if="isAdmin" v-model="historyFilters.keyword" clearable placeholder="搜索申请人" @keyup.enter="loadApplications" />
            <el-button type="primary" plain @click="loadApplications">查询</el-button>
          </div>
          <el-table :data="applications" stripe v-loading="loading">
            <el-table-column prop="id" label="申请单" width="90" />
            <el-table-column v-if="isAdmin" label="申请人" min-width="130"><template #default="{ row }">{{ row.applicant?.display_name || row.applicant?.username || '-' }}</template></el-table-column>
            <el-table-column label="申请内容" min-width="310"><template #default="{ row }"><div v-for="item in row.items" :key="item.cluster_id" class="application-item"><span>{{ sourceLabel(item.cluster) }}</span><el-tag v-if="item.can_query" size="small" type="success">查询</el-tag><el-tag v-if="item.can_change" size="small" type="danger">变更</el-tag></div></template></el-table-column>
            <el-table-column label="持有至" width="180"><template #default="{ row }">{{ formatExpiresAt(row.requested_expires_at) }}</template></el-table-column>
            <el-table-column prop="reason" label="申请原因" min-width="180" show-overflow-tooltip />
            <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="statusType(row.status)">{{ statusText(row.status) }}</el-tag></template></el-table-column>
            <el-table-column prop="review_comment" label="审核意见" min-width="150" show-overflow-tooltip />
            <el-table-column label="申请时间" width="180"><template #default="{ row }">{{ formatBeijingDateTime(row.created_at) }}</template></el-table-column>
            <el-table-column v-if="isAdmin" label="操作" width="150" fixed="right"><template #default="{ row }"><template v-if="row.status === 'pending'"><el-button link type="success" @click="review(row, 'approved')">通过</el-button><el-button link type="danger" @click="review(row, 'rejected')">驳回</el-button></template><span v-else>-</span></template></el-table-column>
          </el-table>
          <div class="pagination"><el-pagination v-model:current-page="page" :page-size="20" :total="total" layout="total, prev, pager, next" @current-change="loadApplications" /></div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { createPermissionApplication, getPermissionApplicationSources, listPermissionApplications, reviewPermissionApplication } from "../api/modules/dataSourcePermissionApplications";

const currentUser = (() => { try { return JSON.parse(localStorage.getItem("dbms_user") || "{}"); } catch { return {}; } })();
const isAdmin = computed(() => currentUser.role === "admin");
const activeTab = ref(isAdmin.value ? "history" : "apply");
const loading = ref(false), submitting = ref(false), clusters = ref([]), applications = ref([]);
const effective = ref({}), selection = reactive({}), reason = ref(""), requestedExpiresAt = ref("");
const filters = reactive({ keyword: "", project: "", dbType: "" });
const historyFilters = reactive({ status: "", keyword: "" });
const page = ref(1), total = ref(0);
const defaultExpiryTime = new Date(2000, 0, 1, 23, 59, 59);
const formatBeijingDateTime = (value) => {
  if (!value) return "-";
  const text = String(value).replace(" ", "T");
  const date = value instanceof Date ? value : new Date(/[zZ]$|[+-]\d{2}:?\d{2}$/.test(text) ? text : `${text}Z`);
  if (Number.isNaN(date.getTime())) return "-";
  return new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" }).format(date);
};
const dateTimeText = (date) => formatBeijingDateTime(date);
const expiryOptions = [
  { label: "1天", value: () => dateTimeText(new Date(Date.now() + 24 * 60 * 60 * 1000)) },
  { label: "1周", value: () => dateTimeText(new Date(Date.now() + 7 * 24 * 60 * 60 * 1000)) },
  { label: "1月", value: () => { const date = new Date(); date.setMonth(date.getMonth() + 1); return dateTimeText(date); } },
  { label: "1年", value: () => { const date = new Date(); date.setFullYear(date.getFullYear() + 1); return dateTimeText(date); } },
];
const projects = computed(() => [...new Set(clusters.value.map((item) => item.project).filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-CN")));
const dbTypes = computed(() => [...new Set(clusters.value.map((item) => item.db_type).filter(Boolean))].sort());
const filteredClusters = computed(() => { const keyword = filters.keyword.trim().toLowerCase(); return clusters.value.filter((item) => { if (filters.project && item.project !== filters.project) return false; if (filters.dbType && item.db_type !== filters.dbType) return false; return !keyword || [item.name, item.project, item.environment, item.db_type].filter(Boolean).join(" ").toLowerCase().includes(keyword); }); });
const selectedItems = computed(() => Object.values(selection).filter((item) => item.can_query || item.can_change));
function hasPermission(id, key) { return Boolean(effective.value[id]?.[key]); }
function permissionSwitchValue(id, key) { return hasPermission(id, key) || Boolean(selection[id]?.[key]); }
function nothingAvailable(row) { return hasPermission(row.id, "can_query") && hasPermission(row.id, "can_change"); }
function isSelected(id) { return Boolean(selection[id]?.can_query || selection[id]?.can_change); }
function toggleRow(row, checked) { if (!checked) { delete selection[row.id]; return; } selection[row.id] = { cluster_id: row.id, can_query: !hasPermission(row.id, "can_query"), can_change: false }; if (!selection[row.id].can_query) selection[row.id].can_change = !hasPermission(row.id, "can_change"); }
function setPermission(row, key, value) { const item = selection[row.id] || { cluster_id: row.id, can_query: false, can_change: false }; selection[row.id] = { ...item, [key]: value }; if (!selection[row.id].can_query && !selection[row.id].can_change) delete selection[row.id]; }
function toggleFiltered(checked) { filteredClusters.value.forEach((row) => toggleRow(row, checked)); }
function sourceLabel(cluster) { return cluster ? [cluster.db_type?.toUpperCase(), cluster.project, cluster.name].filter(Boolean).join(" / ") : "数据源已删除"; }
function statusText(status) { return ({ pending: "待审核", approved: "已通过", rejected: "已驳回" })[status] || status; }
function statusType(status) { return ({ pending: "warning", approved: "success", rejected: "danger" })[status] || "info"; }
function disablePastDate(date) { const today = new Date(); today.setHours(0, 0, 0, 0); return date.getTime() < today.getTime(); }
function formatExpiresAt(value) { return formatBeijingDateTime(value); }
async function loadSources() { if (isAdmin.value) return; const { data } = await getPermissionApplicationSources(); clusters.value = data.data?.clusters || []; effective.value = Object.fromEntries((data.data?.effective_permissions || []).map((item) => [item.cluster_id, item])); }
async function loadApplications() { loading.value = true; try { const { data } = await listPermissionApplications({ page: page.value, page_size: 20, ...historyFilters }); applications.value = data.data?.items || []; total.value = data.data?.total || 0; } finally { loading.value = false; } }
async function submitApplication() { if (!requestedExpiresAt.value) return ElMessage.warning("请选择权限持有至时间"); if (!reason.value.trim()) return ElMessage.warning("请填写申请原因"); submitting.value = true; try { await createPermissionApplication({ reason: reason.value, requested_expires_at: requestedExpiresAt.value, items: selectedItems.value }); ElMessage.success("权限申请已提交"); Object.keys(selection).forEach((key) => delete selection[key]); reason.value = ""; requestedExpiresAt.value = ""; activeTab.value = "history"; await loadApplications(); } finally { submitting.value = false; } }
async function review(row, decision) { let comment = ""; if (decision === "rejected") { const result = await ElMessageBox.prompt("请填写驳回原因", "驳回权限申请", { inputType: "textarea", inputValidator: (value) => Boolean(value?.trim()) || "请填写驳回原因" }); comment = result.value; } else { await ElMessageBox.confirm("确认通过申请单 #" + row.id + "？通过后将立即授予查询/变更权限。", "审核确认", { type: "warning" }); } await reviewPermissionApplication(row.id, { decision, comment }); ElMessage.success("审核已完成"); await loadApplications(); }
async function refreshAll() { await Promise.all([loadSources(), loadApplications()]); }
onMounted(refreshAll);
</script>

<style scoped>
.permission-apply-page { min-width: 0; }
.page-header { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.page-header h2 { margin: 0 0 6px; font-size: 18px; }
.page-header p { margin: 0; color: var(--el-text-color-secondary); font-size: 13px; }
.filters, .history-filters { display: grid; grid-template-columns: minmax(240px, 1.5fr) repeat(2, minmax(170px, 1fr)) auto auto; gap: 10px; margin: 16px 0; }
.history-filters { grid-template-columns: 180px minmax(220px, 320px) auto; justify-content: start; }
.submit-panel { padding: 16px; margin-top: 16px; border: 1px solid var(--el-border-color-lighter); border-radius: 8px; background: var(--el-fill-color-light); }
.expiry-picker { display: flex; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 12px; color: var(--el-text-color-regular); }
.expiry-hint { color: var(--el-text-color-secondary); font-size: 12px; }
.submit-actions { display: flex; justify-content: space-between; align-items: center; margin-top: 12px; color: var(--el-text-color-secondary); }
.application-item { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; padding: 3px 0; }
.permission-switch { display: flex; width: 100%; min-height: 44px; flex-direction: column; align-items: center; justify-content: center; gap: 3px; }
.permission-switch span { color: var(--el-color-success); font-size: 12px; line-height: 16px; white-space: nowrap; }
:deep(td.permission-request-column .cell), :deep(th.permission-request-header .cell) { display: flex; width: 100%; justify-content: center; }
.pagination { display: flex; justify-content: flex-end; margin-top: 16px; }
@media (max-width: 1000px) { .filters { grid-template-columns: repeat(2, minmax(180px, 1fr)); } }
</style>
