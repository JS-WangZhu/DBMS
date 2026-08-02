<template>
  <div class="page">
    <el-card>
      <template #header><div class="header"><span>上线历史</span><el-button @click="loadRows">刷新</el-button></div></template>
      <el-table :data="rows" stripe v-loading="loading">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="title" label="标题" min-width="180" />
        <el-table-column label="类型" width="110"><template #default="scope">{{ dbTypeLabel(scope.row.db_type) }}</template></el-table-column>
        <el-table-column prop="applicant_name" label="申请人" width="120" />
        <el-table-column prop="cluster_name" label="数据源" min-width="150" />
        <el-table-column prop="database" label="数据库" width="140" />
        <el-table-column label="AI 初审" width="110"><template #default="scope"><el-tag :type="scope.row.ai_passed ? 'success' : 'danger'">{{ scope.row.ai_passed ? '通过' : '强制提交' }}</el-tag></template></el-table-column>
        <el-table-column label="状态" width="100"><template #default="scope"><el-tag :type="statusType(scope.row.status)">{{ statusLabel(scope.row.status) }}</el-tag></template></el-table-column>
        <el-table-column prop="created_at" label="提交时间" width="180" />
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="scope">
            <el-button link type="primary" @click="openDetail(scope.row)">详情</el-button>
            <el-button v-if="isAdmin && scope.row.status === 'pending'" link type="danger" :loading="executingId === scope.row.id" @click="execute(scope.row)">执行</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-pagination v-model:current-page="page" v-model:page-size="pageSize" layout="total, prev, pager, next" :total="total" @current-change="loadRows" />
    </el-card>
    <el-drawer v-model="drawer" title="上线详情" size="65%">
      <template v-if="current">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="标题">{{ current.title }}</el-descriptions-item><el-descriptions-item label="申请人">{{ current.applicant_name }}</el-descriptions-item>
          <el-descriptions-item label="数据源">{{ current.cluster_name }}</el-descriptions-item><el-descriptions-item label="数据库">{{ current.database }}</el-descriptions-item>
          <el-descriptions-item label="数据库类型">{{ dbTypeLabel(current.db_type) }}</el-descriptions-item>
          <el-descriptions-item v-if="isAdmin" label="回滚文件">{{ current.rollback_backup_path || '未生成（无数据变更或尚未执行）' }}</el-descriptions-item>
        </el-descriptions>
        <h4>{{ current.db_type === 'mongodb' ? 'Mongo 命令' : 'SQL' }}</h4><pre>{{ current.sql }}</pre>
        <h4>逐条 AI 初审</h4>
        <el-table :data="current.reviews" size="small"><el-table-column prop="line" label="#" width="50" /><el-table-column prop="sql" label="SQL" min-width="260" /><el-table-column label="结论" width="90"><template #default="scope"><el-tag :type="scope.row.passed ? 'success' : 'danger'">{{ scope.row.passed ? '通过' : '不通过' }}</el-tag></template></el-table-column><el-table-column prop="reason" label="原因" min-width="220" /><el-table-column prop="suggestion" label="建议" min-width="220" /></el-table>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { executeSqlRelease, listSqlReleases } from "../api/modules/sqlReleases";
const rows = ref([]), loading = ref(false), page = ref(1), pageSize = ref(10), total = ref(0), drawer = ref(false), current = ref(null), executingId = ref(null);
const isAdmin = computed(() => { try { return JSON.parse(localStorage.getItem("dbms_user") || "{}").role === "admin"; } catch { return false; } });
const statusLabel = (value) => ({ pending: "待执行", executing: "执行中", success: "成功", failed: "失败" }[value] || value);
const statusType = (value) => ({ pending: "warning", executing: "primary", success: "success", failed: "danger" }[value] || "info");
const dbTypeLabel = (value) => ({ mysql: "MySQL", mongodb: "MongoDB", postgresql: "PostgreSQL" }[value] || value || "MySQL");
async function loadRows() { loading.value = true; try { const { data } = await listSqlReleases({ page: page.value, page_size: pageSize.value }); rows.value = data.data?.items || []; total.value = data.data?.total || 0; } finally { loading.value = false; } }
function openDetail(row) { current.value = row; drawer.value = true; }
async function execute(row) { await ElMessageBox.confirm("管理员执行后会直接变更数据库；数据变更将先按影响记录生成对应数据库的回滚文件。确认执行？", "执行确认", { type: "warning" }); executingId.value = row.id; try { await executeSqlRelease(row.id); ElMessage.success("执行成功"); await loadRows(); } catch (error) { ElMessage.error(error.response?.data?.message || "执行失败"); await loadRows(); } finally { executingId.value = null; } }
onMounted(loadRows);
</script>

<style scoped>
.header { display: flex; justify-content: space-between; align-items: center; }
.el-pagination { margin-top: 16px; justify-content: flex-end; }
pre { padding: 12px; overflow: auto; background: #0f172a; color: #e2e8f0; border-radius: 6px; white-space: pre-wrap; }
</style>
