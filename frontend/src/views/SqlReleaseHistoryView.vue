<template>
  <div class="page">
    <el-card>
      <template #header><div class="header"><span>工单历史</span><el-button @click="loadRows">刷新</el-button></div></template>
      <el-form :inline="true" class="filter-form" @submit.prevent>
        <el-form-item label="工单标题">
          <el-input v-model="filters.title_keyword" clearable placeholder="输入标题模糊搜索" style="width: 210px" @keyup.enter="searchRows" />
        </el-form-item>
        <el-form-item label="数据库类型">
          <el-select v-model="filters.db_type" clearable placeholder="全部" style="width: 140px">
            <el-option label="MySQL" value="mysql" />
            <el-option label="MongoDB" value="mongodb" />
            <el-option label="PostgreSQL" value="postgresql" />
          </el-select>
        </el-form-item>
        <el-form-item label="申请人">
          <el-input v-model="filters.applicant" clearable placeholder="姓名或账号" style="width: 150px" @keyup.enter="searchRows" />
        </el-form-item>
        <el-form-item label="执行状态">
          <el-select v-model="filters.status" clearable placeholder="全部" style="width: 150px">
            <el-option v-for="option in statusOptions" :key="option.value" :label="option.label" :value="option.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="提交时间">
          <el-date-picker
            v-model="filters.time_range"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            value-format="YYYY-MM-DD HH:mm:ss"
            style="width: 360px"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="searchRows">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>
      <el-table :data="rows" stripe v-loading="loading">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="title" label="标题" min-width="180" />
        <el-table-column label="类型" width="110"><template #default="scope">{{ dbTypeLabel(scope.row.db_type) }}</template></el-table-column>
        <el-table-column prop="applicant_name" label="申请人" width="120" />
        <el-table-column prop="cluster_name" label="数据源" min-width="150" />
        <el-table-column prop="database" label="数据库" width="140" />
        <el-table-column label="AI 初审" width="110"><template #default="scope"><el-tag :type="reviewType(scope.row)">{{ reviewLabel(scope.row) }}</el-tag></template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="scope"><el-tag :type="statusType(scope.row.status)">{{ statusLabel(scope.row.status) }}</el-tag></template></el-table-column>
        <el-table-column prop="created_at" label="提交时间" width="180" />
        <el-table-column label="操作" width="250" fixed="right">
          <template #default="scope">
            <el-button link type="primary" @click="openDetail(scope.row)">详情</el-button>
            <el-button link type="primary" @click="resubmit(scope.row)">再次提交</el-button>
            <el-button v-if="scope.row.can_execute && canExecute(scope.row)" link type="danger" :loading="executingId === scope.row.id" @click="execute(scope.row)">{{ scope.row.status === 'failed' ? '重试' : '执行' }}</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination v-model:current-page="page" v-model:page-size="pageSize" layout="total, prev, pager, next" :total="total" @current-change="loadRows" />
    </el-card>
    <el-drawer v-model="drawer" title="上线详情" size="78%" @closed="stopDetailPolling">
      <template v-if="current"><div v-loading="detailLoading">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="标题">{{ current.title }}</el-descriptions-item><el-descriptions-item label="申请人">{{ current.applicant_name }}</el-descriptions-item>
          <el-descriptions-item label="数据源">{{ current.cluster_name }}</el-descriptions-item><el-descriptions-item label="数据库">{{ current.database }}</el-descriptions-item>
          <el-descriptions-item label="数据库类型">{{ dbTypeLabel(current.db_type) }}</el-descriptions-item>
          <el-descriptions-item label="执行通道">{{ current.execution_mode === 'agent' ? `Agent：${current.execution_agent_name || '-'}` : 'DBMS Server' }}</el-descriptions-item>
          <el-descriptions-item v-if="isAdmin" label="回滚文件">{{ current.rollback_backup_path || (current.db_type === 'mongodb' ? 'MongoDB 暂不生成备份' : '未生成（无数据变更或尚未执行）') }}</el-descriptions-item>
          <el-descriptions-item v-if="current.db_type !== 'mongodb'" label="数据库备份">{{ rollbackBackupLabel(current) }}</el-descriptions-item>
        </el-descriptions>
        <el-alert v-if="current.ai_summary" :title="current.ai_summary" :type="current.ai_passed ? 'success' : 'warning'" show-icon :closable="false" class="review-summary" />
        <h4>{{ current.db_type === 'mongodb' ? 'Mongo 命令' : 'SQL' }}</h4><pre>{{ current.sql }}</pre>
        <div class="execution-header">
          <h4>逐条执行与回滚</h4>
          <div v-if="current.db_type !== 'mongodb'">
            <el-button :disabled="!selectedRollbackLines.length" :loading="rollbackLoading" @click="rollbackSelected">回滚已选</el-button>
            <el-button type="danger" :disabled="!current.can_rollback" :loading="rollbackLoading" @click="rollbackAll">一键回滚</el-button>
          </div>
        </div>
        <el-table :data="current.statement_executions || []" size="small" border @selection-change="onRollbackSelectionChange">
          <el-table-column v-if="current.db_type !== 'mongodb'" type="selection" width="46" :selectable="canSelectRollback" />
          <el-table-column prop="line" label="#" width="48" />
          <el-table-column prop="sql" label="原 SQL" min-width="240"><template #default="scope"><code class="sql-cell">{{ scope.row.sql }}</code></template></el-table-column>
          <el-table-column label="备份" width="105"><template #default="scope"><el-tag :type="backupType(scope.row)">{{ backupLabel(scope.row) }}</el-tag></template></el-table-column>
          <el-table-column label="执行状态" width="115"><template #default="scope"><el-tag :type="executionType(scope.row.status)">{{ executionLabel(scope.row.status) }}</el-tag></template></el-table-column>
          <el-table-column label="影响/备份" width="105"><template #default="scope">{{ scope.row.affected_rows ?? '-' }} / {{ scope.row.backup_rows ?? 0 }}</template></el-table-column>
          <el-table-column v-if="current.db_type !== 'mongodb'" label="回滚 SQL" min-width="300"><template #default="scope"><pre class="rollback-sql">{{ scope.row.rollback_sql || (scope.row.has_rollback ? '回滚内容仅对具备执行权限的用户可见' : '尚未生成') }}</pre><div v-if="scope.row.error || scope.row.rollback_error" class="statement-error">{{ scope.row.rollback_error || scope.row.error }}</div></template></el-table-column>
        </el-table>
        <h4>逐条 AI 初审</h4>
        <el-table :data="current.reviews" size="small"><el-table-column prop="line" label="#" width="50" /><el-table-column prop="sql" label="SQL" min-width="260" /><el-table-column label="结论" width="90"><template #default="scope"><el-tag :type="scope.row.passed ? 'success' : 'danger'">{{ scope.row.passed ? '通过' : '不通过' }}</el-tag></template></el-table-column><el-table-column prop="reason" label="原因" min-width="220" /><el-table-column prop="suggestion" label="建议" min-width="220" /></el-table>
      </div></template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { executeSqlRelease, getSqlRelease, listSqlReleases, rollbackSqlRelease } from "../api/modules/sqlReleases";
import { useTabActivationRefresh } from "../composables/useTabActivationRefresh";
const router = useRouter();
const rows = ref([]), loading = ref(false), page = ref(1), pageSize = ref(10), total = ref(0), drawer = ref(false), current = ref(null), executingId = ref(null);
const detailLoading = ref(false), rollbackLoading = ref(false), selectedRollbackLines = ref([]);
const filters = reactive({ title_keyword: "", db_type: "", applicant: "", status: "", time_range: [] });
const statusOptions = [
  { label: "初审中", value: "reviewing" },
  { label: "初审未通过", value: "review_rejected" },
  { label: "初审失败", value: "review_failed" },
  { label: "待执行", value: "pending" },
  { label: "执行中", value: "executing" },
  { label: "成功", value: "success" },
  { label: "部分失败", value: "failed" },
  { label: "回滚中", value: "rolling_back" },
  { label: "已回滚", value: "rolled_back" },
  { label: "部分回滚", value: "partial_rolled_back" },
  { label: "回滚失败", value: "rollback_failed" },
];
const isAdmin = computed(() => { try { return JSON.parse(localStorage.getItem("dbms_user") || "{}").role === "admin"; } catch { return false; } });
const statusLabel = (value) => ({ reviewing: "初审中", review_rejected: "初审未通过", review_failed: "初审失败", pending: "待执行", executing: "执行中", success: "成功", failed: "部分失败", rolling_back: "回滚中", rolled_back: "已回滚", partial_rolled_back: "部分回滚", rollback_failed: "回滚失败" }[value] || value);
const statusType = (value) => ({ reviewing: "info", review_rejected: "warning", review_failed: "danger", pending: "warning", executing: "primary", success: "success", failed: "danger", rolling_back: "primary", rolled_back: "success", partial_rolled_back: "warning", rollback_failed: "danger" }[value] || "info");
const reviewLabel = (row) => row.status === "reviewing" ? "审核中" : row.status === "review_failed" ? "失败" : row.ai_passed ? "通过" : "未通过";
const reviewType = (row) => row.status === "reviewing" ? "info" : row.status === "review_failed" ? "danger" : row.ai_passed ? "success" : "warning";
const dbTypeLabel = (value) => ({ mysql: "MySQL", mongodb: "MongoDB", postgresql: "PostgreSQL" }[value] || value || "MySQL");
const rollbackBackupLabel = (row) => { const items = row.rollback_data_backups || []; const rows = items.reduce((total, item) => total + Number(item.row_count || 0), 0); return items.length ? `${items.length} 条语句，共 ${rows} 行原始数据（加密存储）` : "尚未生成"; };
const canExecute = (row) => ["pending", "review_rejected"].includes(row.status)
  || row.can_retry_execute;
const executionLabel = (value) => ({ pending: "待执行", backing_up: "生成回滚中", backup_ready: "回滚已生成", backup_skipped: "不备份", executing: "执行中", success: "执行成功", failed: "执行失败", backup_failed: "回滚生成失败", rollback_executing: "回滚中", rolled_back: "已回滚", rollback_failed: "回滚失败" }[value] || value || "待执行");
const executionType = (value) => ({ pending: "info", backing_up: "primary", backup_ready: "warning", backup_skipped: "info", executing: "primary", success: "success", failed: "danger", backup_failed: "danger", rollback_executing: "primary", rolled_back: "success", rollback_failed: "danger" }[value] || "info");
const backupLabel = (row) => row.has_rollback ? `已备份 ${row.backup_rows || 0} 行` : row.status === "backup_skipped" ? "暂不备份" : ["backing_up"].includes(row.status) ? "生成中" : "未生成";
const backupType = (row) => row.has_rollback ? "success" : row.status === "backup_failed" ? "danger" : "info";
const canSelectRollback = (row) => row.has_rollback && ["success", "rollback_failed"].includes(row.status);
let reviewPollTimer = null, detailPollTimer = null;
function scheduleReviewPoll() { clearTimeout(reviewPollTimer); if (rows.value.some((row) => row.status === "reviewing")) reviewPollTimer = setTimeout(loadRows, 3000); }
async function loadRows() { loading.value = true; try { const params = { page: page.value, page_size: pageSize.value, title_keyword: filters.title_keyword.trim() || undefined, db_type: filters.db_type || undefined, applicant: filters.applicant.trim() || undefined, status: filters.status || undefined, start_time: filters.time_range?.[0] || undefined, end_time: filters.time_range?.[1] || undefined }; const { data } = await listSqlReleases(params); rows.value = data.data?.items || []; total.value = data.data?.total || 0; } catch (error) { ElMessage.error(error.response?.data?.message || "工单列表加载失败"); } finally { loading.value = false; scheduleReviewPoll(); } }
function searchRows() { page.value = 1; loadRows(); }
function resetFilters() { Object.assign(filters, { title_keyword: "", db_type: "", applicant: "", status: "", time_range: [] }); searchRows(); }
function stopDetailPolling(clearSelection = true) { clearTimeout(detailPollTimer); detailPollTimer = null; if (clearSelection) selectedRollbackLines.value = []; }
function scheduleDetailPolling() { stopDetailPolling(false); if (drawer.value && current.value && ["executing", "rolling_back"].includes(current.value.status)) detailPollTimer = setTimeout(() => loadDetail(current.value.id, true), 1000); }
async function loadDetail(id, silent = false) { if (!silent) detailLoading.value = true; try { const { data } = await getSqlRelease(id); current.value = data.data; } catch (error) { if (!silent) ElMessage.error(error.response?.data?.message || "工单详情加载失败"); } finally { detailLoading.value = false; scheduleDetailPolling(); } }
function openDetail(row) { current.value = row; drawer.value = true; loadDetail(row.id); }
function onRollbackSelectionChange(items) { selectedRollbackLines.value = items.filter(canSelectRollback).map((item) => item.line); }
async function rollbackLines(lines) { const partial = Array.isArray(lines); await ElMessageBox.confirm(partial ? `确认回滚选中的 ${lines.length} 条 SQL？系统将按逆序执行对应回滚语句。` : "确认一键回滚全部可回滚 SQL？系统将按逆序执行。", partial ? "部分回滚确认" : "一键回滚确认", { type: "warning", confirmButtonText: "确认回滚" }); rollbackLoading.value = true; try { const { data } = await rollbackSqlRelease(current.value.id, lines); current.value = data.data?.release || current.value; ElMessage.success(data.message || "回滚完成"); await loadRows(); } catch (error) { ElMessage.error(error.response?.data?.message || "回滚失败"); await loadDetail(current.value.id, true); } finally { rollbackLoading.value = false; } }
function rollbackSelected() { return rollbackLines([...selectedRollbackLines.value]); }
function rollbackAll() { return rollbackLines(null); }
async function resubmit(row) {
  try {
    sessionStorage.setItem("sql_release_resubmit_draft", JSON.stringify({
      source_release_id: row.id,
      title: row.title || "",
      cluster_id: row.cluster_id,
      instance_id: row.instance_id,
      db_type: row.db_type || "mysql",
      database: row.database || "",
      sql: row.sql || "",
    }));
  } catch {
    ElMessage.error("SQL 内容过大，无法暂存再次提交信息");
    return;
  }
  await router.push({ path: "/data-release/apply", query: { resubmit: String(row.id) } });
}
async function execute(row) { const rejected = row.status === "review_rejected"; const mongoNotice = row.db_type === "mongodb" ? "MongoDB 当前按语句逐条执行，但暂不生成回滚备份。" : row.execution_mode === "agent" ? "本工单将由实例绑定的 Agent 逐条提交；Agent 通道当前不生成回滚备份。" : "每条 SQL 都会先生成并保存回滚语句，再单独提交执行。"; const message = rejected ? `AI 初审未通过。确认接受审核提示的风险并继续执行？${mongoNotice}` : `执行后会直接变更数据库；${mongoNotice}确认执行？`; await ElMessageBox.confirm(message, rejected ? "风险确认" : "执行确认", { type: "warning", confirmButtonText: rejected ? "确认风险并执行" : "执行" }); executingId.value = row.id; if (current.value?.id === row.id) { current.value.status = "executing"; scheduleDetailPolling(); } try { await executeSqlRelease(row.id, { confirm_risk: rejected }); ElMessage.success("执行成功"); await loadRows(); if (current.value?.id === row.id) await loadDetail(row.id, true); } catch (error) { ElMessage.error(error.response?.data?.message || "执行失败"); await loadRows(); if (current.value?.id === row.id) await loadDetail(row.id, true); } finally { executingId.value = null; } }
onMounted(loadRows);
useTabActivationRefresh(loadRows);
onBeforeUnmount(() => { clearTimeout(reviewPollTimer); stopDetailPolling(); });
</script>

<style scoped>
.header { display: flex; justify-content: space-between; align-items: center; }
.filter-form { margin-bottom: 2px; }
.el-pagination { margin-top: 16px; justify-content: flex-end; }
pre { padding: 12px; overflow: auto; background: #0f172a; color: #e2e8f0; border-radius: 6px; white-space: pre-wrap; }
.review-summary { margin-top: 16px; }
.execution-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-top: 18px; }
.execution-header h4 { margin: 0; }
.sql-cell { white-space: pre-wrap; word-break: break-word; }
.rollback-sql { margin: 0; padding: 7px; max-height: 150px; font-size: 12px; }
.statement-error { margin-top: 5px; color: #e5484d; font-size: 12px; word-break: break-all; }
</style>
