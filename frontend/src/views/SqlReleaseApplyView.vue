<template>
  <div class="page">
    <div class="release-workspace">
    <el-card class="release-card">
      <template #header><span>SQL 上线申请</span></template>
      <el-alert title="提交时必须经过 AI 逐条初审；未通过的语句请按建议修改，也可确认风险后强制提交。" type="info" show-icon :closable="false" />
      <el-form :model="form" label-width="100px" class="release-form">
        <el-form-item label="申请标题"><el-input v-model="form.title" maxlength="255" /></el-form-item>
        <el-form-item label="项目">
          <el-select v-model="form.project" filterable placeholder="先选择项目" style="width: 100%" @change="onProjectChange">
            <el-option v-for="item in projects" :key="item" :value="item" :label="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="数据库">
          <el-select v-model="form.db_type" :disabled="!form.project" placeholder="再选择数据库" style="width: 100%" @change="onDbTypeChange">
            <template #prefix><component :is="databaseTypeIcons[form.db_type]" v-if="form.db_type" class="database-type-selected-icon" /></template>
            <el-option v-for="item in databaseTypes" :key="item.value" :value="item.value" :label="item.label">
              <span class="database-type-option"><component :is="item.icon" />{{ item.label }}</span>
            </el-option>
          </el-select>
        </el-form-item>
        <el-form-item label="环境">
          <el-select v-model="form.environment" :disabled="!form.db_type" filterable placeholder="选择环境" style="width: 100%" @change="onEnvironmentChange">
            <el-option v-for="item in environments" :key="item" :value="item" :label="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="集群">
          <el-select v-model="form.cluster_id" :disabled="!form.environment" filterable placeholder="选择具备变更权限的集群" style="width: 100%" @change="loadDatabases">
            <el-option v-for="item in filteredClusters" :key="item.id" :value="item.id" :label="clusterLabel(item)">
              <div class="cluster-option"><span>{{ clusterLabel(item) }}</span><small>{{ item.description || "暂无描述" }}</small></div>
            </el-option>
          </el-select>
          <div v-if="selectedCluster" class="cluster-description">集群描述：{{ selectedCluster.description || "暂无描述" }}</div>
        </el-form-item>
        <el-form-item label="目标库">
          <el-select v-model="form.database" :disabled="!form.cluster_id" filterable allow-create default-first-option placeholder="选择或输入目标库" style="width: 100%" :loading="databaseLoading" @change="loadTableOverview">
            <el-option v-for="item in databases" :key="item" :value="item" :label="item" />
          </el-select>
        </el-form-item>
        <el-form-item :label="form.db_type === 'mongodb' ? 'Mongo命令' : 'SQL'">
          <SqlEditor
            :key="editorMode"
            ref="sqlEditorRef"
            v-model="form.sql"
            :mode="editorMode"
            :placeholder="editorPlaceholder"
            :min-height="300"
            :schema="editorSchema"
            @run="submit"
          />
          <div class="editor-hint">支持语法高亮与智能补全，多个变更以分号结束；提交工单后系统将异步进行 AI 初审</div>
        </el-form-item>
      </el-form>
      <div class="actions"><el-button type="primary" :loading="submitting" @click="submit">提交工单</el-button></div>
    </el-card>

    <el-card class="overview-card">
      <template #header>
        <div class="overview-header">
          <div>
            <div class="overview-title">对象概览</div>
            <div class="overview-subtitle">{{ form.database ? `${form.database} · ${objectRows.length} 个${form.db_type === 'mongodb' ? '集合' : '表'}` : '选择目标库后显示' }}</div>
          </div>
          <el-button :disabled="!form.database" :loading="overviewLoading" @click="loadTableOverview">刷新</el-button>
        </div>
      </template>
      <el-input v-model="tableKeyword" clearable placeholder="搜索对象" :disabled="!form.database" class="overview-search">
        <template #prefix><el-icon><Search /></el-icon></template>
      </el-input>
      <div class="overview-body" v-loading="overviewLoading">
        <el-tree
          v-if="form.database && hasFilteredObjects"
          :data="schemaTreeData"
          :props="{ label: 'label', children: 'children', isLeaf: 'leaf' }"
          node-key="key"
          :key="`${form.db_type}:${schemaGeneration}`"
          lazy
          :load="loadSchemaNode"
          :default-expanded-keys="[form.db_type === 'mongodb' ? 'group:collections' : 'group:tables']"
          :expand-on-click-node="false"
          class="object-tree"
          @node-click="onSchemaNodeClick"
        >
          <template #default="{ data }">
            <span :class="['tree-node', { 'is-sql-used': data.isUsed }]">
              <el-icon v-if="data.kind === 'group'" class="tree-icon"><Folder /></el-icon>
              <el-icon v-else-if="data.kind === 'table' || data.kind === 'collection'" class="tree-icon tree-icon-table"><Grid /></el-icon>
              <el-icon v-else-if="data.kind === 'view'" class="tree-icon tree-icon-view"><View /></el-icon>
              <el-icon v-else-if="data.kind === 'column' || data.kind === 'field'" class="tree-icon tree-icon-column">
                <Key v-if="data.raw?.column_key === 'PRI'" /><Connection v-else />
              </el-icon>
              <el-icon v-else class="tree-icon"><Document /></el-icon>
              <span class="tree-label" :title="data.tooltip || data.label">{{ data.label }}</span>
              <el-tag v-if="data.isUsed" size="small" type="warning" effect="dark">SQL涉及</el-tag>
              <span v-if="data.loading" class="tree-suffix">加载中...</span>
              <span v-else-if="data.suffix" class="tree-suffix">{{ data.suffix }}</span>
            </span>
          </template>
        </el-tree>
        <el-empty v-else :description="form.database ? '暂无匹配对象' : '请先选择目标库'" :image-size="72" />
      </div>
    </el-card>
    </div>

    <el-dialog
      v-model="reviewDialogVisible"
      width="760px"
      top="4vh"
      class="review-progress-dialog"
      :close-on-click-modal="false"
      @closed="onReviewDialogClosed"
    >
      <template #header>
        <div class="review-dialog-header">
          <div class="review-orbit" :class="{ done: reviewFinished }"><span></span><i></i></div>
          <div>
            <h3>{{ reviewDialogTitle }}</h3>
            <p>工单 #{{ reviewRelease?.id }} · {{ reviewRelease?.title }}</p>
          </div>
        </div>
      </template>
      <div v-if="reviewRelease" class="review-progress-body">
        <SqlReleaseShareCard :release="reviewRelease" class="review-share-card" />
        <div class="review-progress-overview">
          <div><strong>{{ reviewCompleted }}</strong><span>/ {{ reviewTotal }} 条已审核</span></div>
          <span>{{ reviewRelease.ai_summary }}</span>
        </div>
        <el-progress :percentage="reviewPercent" :status="reviewProgressStatus" :stroke-width="10" />
        <transition-group name="review-item" tag="div" class="review-statement-list">
          <div v-for="item in reviewRelease.reviews" :key="item.line" class="review-statement" :class="[`is-${item.status}`, { 'is-passed': item.status === 'completed' && item.passed, 'is-rejected': item.status === 'completed' && !item.passed }]">
            <div class="review-state-mark">
              <el-icon v-if="item.status === 'completed' && item.passed"><CircleCheck /></el-icon>
              <el-icon v-else-if="item.status === 'completed' || item.status === 'failed'"><CircleClose /></el-icon>
              <el-icon v-else-if="item.status === 'reviewing'" class="is-loading"><Loading /></el-icon>
              <span v-else>{{ item.line }}</span>
            </div>
            <div class="review-statement-main">
              <div><strong>第 {{ item.line }} 条</strong><el-tag size="small" :type="reviewItemType(item)">{{ reviewItemLabel(item) }}</el-tag></div>
              <code>{{ item.sql }}</code>
              <div v-if="item.status === 'reviewing' && (item.thinking_content || item.stream_content)" class="review-live-output">
                <details v-if="item.thinking_content" open><summary>Thinking</summary><pre>{{ item.thinking_content }}</pre></details>
                <pre v-if="item.stream_content">{{ item.stream_content }}</pre>
              </div>
              <p>{{ item.reason }}</p>
              <p v-if="item.suggestion" class="review-suggestion">建议：{{ item.suggestion }}</p>
            </div>
          </div>
        </transition-group>
      </div>
      <template #footer>
        <span class="review-background-tip">{{ reviewFinished ? "审核结果已保存至工单" : "关闭后审核仍会在后台继续" }}</span>
        <template v-if="reviewRelease?.status === 'review_rejected'">
          <el-button @click="returnRejectedToEdit">返回重新修改</el-button>
          <el-button type="danger" :loading="forceSubmitting" @click="forceSubmitRejected">已知影响，强制提交</el-button>
        </template>
        <template v-else-if="reviewRelease?.status === 'review_failed'">
          <el-button @click="returnRejectedToEdit">返回修改</el-button>
          <el-button type="warning" :loading="skipReviewSubmitting" @click="skipFailedReview">跳过审核</el-button>
        </template>
        <el-button v-else type="primary" @click="reviewDialogVisible = false">{{ reviewFinished ? "完成" : "转至后台运行" }}</el-button>
      </template>

    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";
import { CircleCheck, CircleClose, Connection, Document, Folder, Grid, Key, Loading, Search, View } from "@element-plus/icons-vue";
import { listClusters } from "../api/modules/clusters";
import {
  getSqlReleaseReviewProgress,
  forceSubmitSqlRelease,
  listSqlReleaseDatabases,
  listSqlReleaseObjects,
  listSqlReleaseTableColumns,
  skipSqlReleaseReview,
  submitSqlRelease,
} from "../api/modules/sqlReleases";
import SqlEditor from "../components/SqlEditor.vue";
import SqlReleaseShareCard from "../components/SqlReleaseShareCard.vue";
import MysqlIcon from "../components/icons/MysqlIcon.vue";
import MongoIcon from "../components/icons/MongoIcon.vue";
import PostgreSQLIcon from "../components/icons/PostgreSQLIcon.vue";
import { extractReleaseObjectNames } from "../utils/sqlRelease";
import { useTabActivationRefresh } from "../composables/useTabActivationRefresh";

const route = useRoute();
const router = useRouter();
const clusters = ref([]);
const databases = ref([]);
const databaseLoading = ref(false);
const submitting = ref(false);
const overviewLoading = ref(false);
const tableKeyword = ref("");
const sqlEditorRef = ref(null);
const tableColumnsCache = reactive({});
const loadingColumns = reactive(new Set());
const schemaGeneration = ref(0);
const reviewDialogVisible = ref(false);
const reviewRelease = ref(null);
const submittedDraft = ref(null);
const forceSubmitting = ref(false);
const skipReviewSubmitting = ref(false);
let reviewPollTimer = null;
let reviewDialogMovedToBackground = false;

const tableObjects = ref({ tables: [], collections: [], views: [], procedures: [], functions: [], triggers: [], events: [] });
const databaseTypes = [
  { label: "MySQL", value: "mysql", icon: MysqlIcon },
  { label: "MongoDB", value: "mongodb", icon: MongoIcon },
  { label: "PostgreSQL", value: "postgresql", icon: PostgreSQLIcon },
];
const databaseTypeIcons = Object.fromEntries(databaseTypes.map((item) => [item.value, item.icon]));
const form = reactive({ title: "", project: "", db_type: "", environment: "", cluster_id: null, instance_id: null, database: "", sql: "" });
const reviewFinished = computed(() => reviewRelease.value && reviewRelease.value.status !== "reviewing");
const reviewCompleted = computed(() => reviewRelease.value?.review_progress?.completed || 0);
const reviewTotal = computed(() => reviewRelease.value?.review_progress?.total || reviewRelease.value?.reviews?.length || 0);
const reviewPercent = computed(() => reviewRelease.value?.review_progress?.percent || 0);
const reviewDialogTitle = computed(() => reviewRelease.value?.review_skipped ? "AI 预审已跳过" : reviewRelease.value?.status === "pending" ? "AI 初审已通过" : reviewRelease.value?.status === "review_rejected" ? "AI 初审发现风险" : reviewRelease.value?.status === "review_failed" ? "AI 初审异常" : "AI 正在逐条审核");
const reviewProgressStatus = computed(() => reviewRelease.value?.status === "pending" ? "success" : ["review_rejected", "review_failed"].includes(reviewRelease.value?.status) ? "exception" : undefined);

const REVIEW_POLL_INTERVAL = 1200;
const projects = computed(() => Array.from(new Set(clusters.value.map((item) => item.business_line || item.namespace).filter(Boolean))).sort());
const environments = computed(() => Array.from(new Set(clusters.value
  .filter((item) => (item.business_line || item.namespace) === form.project && item.db_type === form.db_type)
  .map((item) => item.environment)
  .filter(Boolean))).sort());
const filteredClusters = computed(() => clusters.value.filter((item) =>
  (item.business_line || item.namespace) === form.project
  && item.db_type === form.db_type
  && item.environment === form.environment
));
const selectedCluster = computed(() => clusters.value.find((item) => Number(item.id) === Number(form.cluster_id)) || null);
const usedTableNames = computed(() => extractReleaseObjectNames(form.sql, form.db_type));
const objectRows = computed(() => form.db_type === "mongodb" ? (tableObjects.value.collections || []) : (tableObjects.value.tables || []));
const filteredTables = computed(() => {
  const keyword = tableKeyword.value.trim().toLowerCase();
  return objectRows.value
    .filter((item) => !keyword || String(item.name || "").toLowerCase().includes(keyword))
    .slice()
    .sort((left, right) => {
      const leftUsed = isUsedTable(left.name);
      const rightUsed = isUsedTable(right.name);
      if (leftUsed !== rightUsed) return leftUsed ? -1 : 1;
      return String(left.name || "").localeCompare(String(right.name || ""));
    });
});
const sqlSchema = computed(() => ({
  tables: (tableObjects.value.tables || []).map((item) => ({
    ...item,
    columns: tableColumnsCache[item.name] || [],
  })),
  views: tableObjects.value.views || [],
}));
const mongoSchema = computed(() => ({
  collections: (tableObjects.value.collections || []).map((item) => ({
    ...item,
    fields: tableColumnsCache[item.name] || [],
  })),
  views: tableObjects.value.views || [],
}));
const editorSchema = computed(() => form.db_type === "mongodb" ? mongoSchema.value : sqlSchema.value);
const editorMode = computed(() => form.db_type === "mongodb" ? "mongodb" : (form.db_type === "postgresql" ? "postgresql" : "sql"));
const editorPlaceholder = computed(() => form.db_type === "mongodb"
  ? '例如：db.orders.updateMany({status: "new"}, {$set: {status: "paid"}});'
  : "每条语句以分号结束；输入关键字、表名或 表名.字段 可自动补全");
const hasFilteredObjects = computed(() => !tableKeyword.value.trim() || schemaTreeData.value.some((group) => group.children.length));
const schemaTreeData = computed(() => {
  const keyword = tableKeyword.value.trim().toLowerCase();
  const matches = (items) => (items || []).filter((item) => !keyword || String(item.name || "").toLowerCase().includes(keyword));
  const group = (label, kind, items, mapItem, count = items.length) => ({
    key: `group:${kind}`,
    label: `${label} (${count})`,
    kind: "group",
    leaf: items.length === 0,
    children: items.map(mapItem),
  });
  return [
    group(form.db_type === "mongodb" ? "Collections" : "Tables", form.db_type === "mongodb" ? "collections" : "tables", filteredTables.value, (item) => ({
      key: `${form.db_type === "mongodb" ? "collection" : "table"}:${item.name}`, label: item.name,
      kind: form.db_type === "mongodb" ? "collection" : "table", raw: item, leaf: false,
      suffix: formatSize(item.size_bytes), isUsed: isUsedTable(item.name), loading: isLoadingColumns(item.name),
      tooltip: `${item.name}${item.row_count != null ? ` · ${formatCount(item.row_count)} 行` : ""}${item.size_bytes ? ` · ${formatSize(item.size_bytes)}` : ""}`,
    })),
    group("Views", "views", matches(tableObjects.value.views), (item) => objectTreeItem(form.db_type === "mongodb" ? "mongo-view" : "view", item)),
    group("Procedures", "procedures", matches(tableObjects.value.procedures), (item) => objectTreeItem("procedure", item)),
    group("Functions", "functions", matches(tableObjects.value.functions), (item) => objectTreeItem("function", item)),
    group("Triggers", "triggers", matches(tableObjects.value.triggers), (item) => objectTreeItem("trigger", item)),
    group("Events", "events", matches(tableObjects.value.events), (item) => objectTreeItem("event", item)),
  ];
});

function clusterLabel(item) { return item.name || `集群-${item.id}`; }

function isUsedTable(name) {
  const normalized = String(name || "").toLowerCase();
  return usedTableNames.value.has(normalized) || usedTableNames.value.has(normalized.split(".").pop());
}

function objectTreeItem(kind, item) {
  return { key: `${kind}:${item.name}`, label: item.name, kind, raw: item, leaf: true };
}

function columnTreeItem(table, column) {
  const type = column.column_type || column.data_type || column.type || "";
  return {
    key: `column:${table}.${column.name}`, label: column.name, kind: form.db_type === "mongodb" ? "field" : "column", raw: column,
    suffix: type, tooltip: `${column.name} ${type}${column.comment ? ` · ${column.comment}` : ""}`, leaf: true,
  };
}

async function ensureTableColumns(table, silent = false) {
  const generation = schemaGeneration.value;
  const loadingKey = `${generation}:${table}`;
  if (!form.cluster_id || !form.database || !table || tableColumnsCache[table] || loadingColumns.has(loadingKey)) {
    return tableColumnsCache[table] || [];
  }
  const clusterId = form.cluster_id;
  const database = form.database;
  loadingColumns.add(loadingKey);
  try {
    const { data } = await listSqlReleaseTableColumns(clusterId, database, table, form.db_type);
    const columns = data.data?.columns || [];
    if (schemaGeneration.value === generation) {
      tableColumnsCache[table] = columns;
      return columns;
    }
    return [];
  } catch (error) {
    if (!silent && schemaGeneration.value === generation) {
      ElMessage.warning(error.response?.data?.message || `表 ${table} 字段加载失败`);
    }
    return [];
  } finally {
    loadingColumns.delete(loadingKey);
  }
}

function isLoadingColumns(table) {
  return loadingColumns.has(`${schemaGeneration.value}:${table}`);
}

async function loadSchemaNode(node, resolve) {
  const data = node.data;
  if (!data) return resolve([]);
  if (data.kind === "group") return resolve(data.children || []);
  if (data.kind === "table" || data.kind === "collection") {
    const columns = await ensureTableColumns(data.label);
    return resolve(columns.map((item) => columnTreeItem(data.label, item)));
  }
  return resolve([]);
}

function onSchemaNodeClick(data) {
  if (!data) return;
  if (data.kind === "collection" || data.kind === "mongo-view") {
    sqlEditorRef.value?.insertText(`db.${data.label}.`);
  } else if (data.kind === "field") {
    sqlEditorRef.value?.insertText(`"${data.label}": `);
  } else if (["table", "view", "column"].includes(data.kind)) {
    const quoted = form.db_type === "postgresql"
      ? data.label.split(".").map((item) => `"${item.replaceAll('"', '""')}"`).join(".")
      : `\`${data.label}\``;
    sqlEditorRef.value?.insertText(quoted);
  }
}

function resetClusterSelection() {
  form.cluster_id = null;
  form.instance_id = null;
  form.database = "";
  databases.value = [];
  clearTableOverview();
}

function clearTableOverview() {
  schemaGeneration.value += 1;
  tableKeyword.value = "";
  tableObjects.value = { tables: [], collections: [], views: [], procedures: [], functions: [], triggers: [], events: [] };
  for (const key of Object.keys(tableColumnsCache)) delete tableColumnsCache[key];
  loadingColumns.clear();
}

function onProjectChange() {
  form.db_type = "";
  form.environment = "";
  resetClusterSelection();
}

function onDbTypeChange() {
  form.environment = "";
  resetClusterSelection();
}

function onEnvironmentChange() {
  resetClusterSelection();
}

async function loadDatabases() {
  form.database = "";
  databases.value = [];
  clearTableOverview();
  if (!form.cluster_id) return;
  databaseLoading.value = true;
  try {
    const { data } = await listSqlReleaseDatabases(form.cluster_id, form.db_type);
    databases.value = data.data?.databases || [];
    form.instance_id = data.data?.instance_id || null;
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "数据库列表加载失败");
  } finally { databaseLoading.value = false; }
}

async function loadTableOverview() {
  clearTableOverview();
  if (!form.cluster_id || !form.database) return;
  overviewLoading.value = true;
  try {
    const { data } = await listSqlReleaseObjects(form.cluster_id, form.database, form.db_type);
    const payload = data.data || {};
    tableObjects.value = {
      tables: payload.tables || [], collections: payload.collections || [], views: payload.views || [], procedures: payload.procedures || [],
      functions: payload.functions || [], triggers: payload.triggers || [], events: payload.events || [],
    };
    preloadUsedTableColumns();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "表概览加载失败");
  } finally { overviewLoading.value = false; }
}

function formatCount(value) {
  const count = Number(value || 0);
  return count.toLocaleString("zh-CN");
}

function formatSize(value) {
  const bytes = Number(value || 0);
  if (!bytes) return "-";
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function preloadUsedTableColumns() {
  const actualNames = new Map(objectRows.value.flatMap((item) => {
    const full = String(item.name).toLowerCase();
    return [[full, item.name], [full.split(".").pop(), item.name]];
  }));
  for (const name of usedTableNames.value) {
    const actualName = actualNames.get(name);
    if (actualName) ensureTableColumns(actualName, true);
  }
}


function reviewItemLabel(item) {
  if (item.status === "reviewing") return "审核中";
  if (item.status === "pending") return "等待";
  if (item.status === "failed") return "失败";
  if (item.status === "skipped") return "已跳过";
  return item.passed ? "通过" : "不通过";
}

function reviewItemType(item) {
  if (item.status === "reviewing" || item.status === "pending") return "info";
  if (item.status === "completed" && item.passed) return "success";
  if (item.status === "skipped") return "warning";
  return "danger";
}

function stopReviewPolling() {
  clearTimeout(reviewPollTimer);
  reviewPollTimer = null;
}

function scheduleReviewPoll() {
  stopReviewPolling();
  if (reviewDialogVisible.value && reviewRelease.value?.status === "reviewing") {
    reviewPollTimer = setTimeout(loadReviewProgress, REVIEW_POLL_INTERVAL);
  }
}

async function loadReviewProgress() {
  if (!reviewDialogVisible.value || !reviewRelease.value?.id) return;
  try {
    const { data } = await getSqlReleaseReviewProgress(reviewRelease.value.id);
    reviewRelease.value = data.data;
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "审核进度获取失败，任务仍在后台运行");
    reviewDialogVisible.value = false;
    return;
  }
  scheduleReviewPoll();
}

function openReviewProgress(release) {
  stopReviewPolling();
  reviewRelease.value = release;
  reviewDialogMovedToBackground = false;
  reviewDialogVisible.value = true;
  scheduleReviewPoll();
}

function onReviewDialogClosed() {
  stopReviewPolling();
  if (!reviewFinished.value && !reviewDialogMovedToBackground) {
    reviewDialogMovedToBackground = true;
    ElMessage.info("审核已转至后台，可稍后在工单历史查看结果");
  }
}

async function submit() {
  if (!form.project || !form.db_type || !form.environment || !form.cluster_id || !form.database || !form.sql.trim()) return ElMessage.warning("请按项目、数据库、环境、集群顺序选择数据源，并填写目标库和变更语句");
  const statementCount = Math.max(1, form.sql.split(";").filter((item) => item.trim()).length);
  try {
    await ElMessageBox.confirm(
      `即将向 ${form.project}/${form.environment}/${form.database} 提交 ${statementCount} 条${form.db_type === "mongodb" ? "命令" : " SQL"}，提交后将进入 AI 初审。请确认目标数据源和变更内容无误。`,
      "提交工单二次确认",
      { type: "warning", confirmButtonText: "确认提交", cancelButtonText: "返回检查" },
    );
  } catch {
    return;
  }
  submittedDraft.value = { ...form };
  submitting.value = true;
  try {
    const { data } = await submitSqlRelease({ ...form });
    openReviewProgress(data.data);
    ElMessage.success(data.message || "工单已提交");
    form.title = ""; form.sql = "";
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "提交失败");
  } finally { submitting.value = false; }
}

function returnRejectedToEdit() {
  const draft = submittedDraft.value;
  if (draft) {
    Object.assign(form, draft);
  } else if (reviewRelease.value) {
    form.title = reviewRelease.value.title || "";
    form.sql = reviewRelease.value.sql || "";
  }
  reviewDialogVisible.value = false;
  ElMessage.info(reviewRelease.value?.status === "review_failed" ? "已恢复本次工单内容" : "已恢复本次工单内容，请按初审建议修改后重新提交");
}

async function skipFailedReview() {
  if (!reviewRelease.value?.id || reviewRelease.value.status !== "review_failed") return;
  try {
    await ElMessageBox.confirm(
      "AI 模型预审出现异常。跳过后工单将直接进入待执行，且不会产生 AI 风险结论。确认跳过本次审核？",
      "跳过 AI 预审确认",
      { type: "warning", confirmButtonText: "确认跳过" },
    );
  } catch {
    return;
  }
  skipReviewSubmitting.value = true;
  try {
    const { data } = await skipSqlReleaseReview(reviewRelease.value.id);
    reviewRelease.value = data.data;
    submittedDraft.value = null;
    ElMessage.success(data.message || "已跳过 AI 预审");
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "跳过审核失败");
  } finally {
    skipReviewSubmitting.value = false;
  }
}

async function forceSubmitRejected() {
  if (!reviewRelease.value?.id || reviewRelease.value.status !== "review_rejected") return;
  try {
    await ElMessageBox.confirm(
      "AI 初审未通过。强制提交表示你已阅读全部风险与影响，工单将进入待执行状态，后续仍需具备执行权限的 DBMS 用户执行。",
      "强制提交确认",
      { type: "error", confirmButtonText: "已知影响，确认提交", cancelButtonText: "返回修改" },
    );
  } catch {
    return;
  }
  forceSubmitting.value = true;
  try {
    const { data } = await forceSubmitSqlRelease(reviewRelease.value.id);
    reviewRelease.value = data.data;
    submittedDraft.value = null;
    ElMessage.success(data.message || "工单已强制提交，等待执行");
    reviewDialogVisible.value = false;
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "强制提交失败");
  } finally {
    forceSubmitting.value = false;
  }
}

async function restoreResubmitDraft() {
  const requestedReleaseId = String(route.query.resubmit || "");
  if (!requestedReleaseId) return;
  let draft = null;
  try {
    draft = JSON.parse(sessionStorage.getItem("sql_release_resubmit_draft") || "null");
  } catch {
    draft = null;
  }
  sessionStorage.removeItem("sql_release_resubmit_draft");
  await router.replace({ path: route.path });
  if (!draft || String(draft.source_release_id || "") !== requestedReleaseId) {
    ElMessage.warning("再次提交信息已失效，请返回工单历史重新操作");
    return;
  }

  form.title = String(draft.title || "");
  form.sql = String(draft.sql || "");
  const cluster = clusters.value.find((item) => (
    Number(item.id) === Number(draft.cluster_id)
    && item.db_type === draft.db_type
  ));
  if (!cluster) {
    ElMessage.warning("原工单的数据源当前不可选，已保留标题和 SQL，请重新选择目标数据源");
    return;
  }

  form.project = cluster.business_line || cluster.namespace || "";
  form.db_type = cluster.db_type || draft.db_type || "";
  form.environment = cluster.environment || "";
  form.cluster_id = cluster.id;
  await loadDatabases();
  form.instance_id = draft.instance_id || form.instance_id;
  form.database = String(draft.database || "");
  await loadTableOverview();
  ElMessage.success(`已载入工单 #${requestedReleaseId}，修改后可重新提交`);
}

async function loadAllowedClusters() {
  const responses = await Promise.all(databaseTypes.map((item) => listClusters(item.value, { action: "change" })));
  clusters.value = responses.flatMap(({ data }) => data.data || []);
}

onMounted(async () => {
  await loadAllowedClusters();
  await restoreResubmitDraft();
});
useTabActivationRefresh(async () => {
  await loadAllowedClusters();
  await restoreResubmitDraft();
});

onBeforeUnmount(stopReviewPolling);
watch(
  () => Array.from(usedTableNames.value).sort().join("|"),
  preloadUsedTableColumns
);
</script>

<style scoped>
.page { display: grid; gap: 16px; }
.release-workspace { display: grid; grid-template-columns: minmax(0, 1fr) 420px; gap: 16px; align-items: start; }
.release-card, .overview-card { min-width: 0; }
.release-form { margin-top: 20px; }
.database-type-option { display: inline-flex; align-items: center; gap: 8px; }
.database-type-option :deep(svg) { width: 16px; height: 16px; }
.cluster-option { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.cluster-option small { max-width: 260px; overflow: hidden; color: #94a3b8; text-overflow: ellipsis; white-space: nowrap; }
.cluster-description { width: 100%; margin-top: 6px; padding: 7px 10px; border-radius: 6px; background: #f8fafc; color: #64748b; font-size: 12px; line-height: 1.5; }
.database-type-selected-icon { width: 16px; height: 16px; }
.actions { display: flex; justify-content: flex-end; margin-top: 16px; }
.overview-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.overview-title { font-weight: 600; }
.overview-subtitle { margin-top: 4px; font-size: 12px; color: #94a3b8; }
.overview-search { margin-bottom: 12px; }
.overview-body { min-height: 420px; max-height: calc(100vh - 250px); overflow: auto; }
.editor-hint { margin-top: 7px; color: #94a3b8; font-size: 12px; }
.object-tree { --el-tree-node-hover-bg-color: #f8fafc; }
.tree-node { display: inline-flex; align-items: center; gap: 6px; width: calc(100% - 8px); min-width: 0; padding: 3px 6px; border-radius: 5px; transition: background-color .15s, box-shadow .15s; }
.tree-node.is-sql-used { background: #fff3d6; box-shadow: inset 3px 0 0 #f59e0b; color: #92400e; font-weight: 600; }
.tree-node.is-sql-used:hover { background: #ffe8b0; }
.tree-icon { flex: 0 0 auto; color: #64748b; }
.tree-icon-table { color: #2563eb; }
.tree-icon-view { color: #9333ea; }
.tree-icon-column { color: #0ea5e9; }
.tree-label { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tree-suffix { flex: 0 0 auto; margin-left: 6px; color: #94a3b8; font-size: 12px; font-weight: 400; }
:deep(.object-tree .el-tree-node__content) { min-height: 34px; height: auto; padding-right: 4px; }
@media (max-width: 1180px) { .release-workspace { grid-template-columns: 1fr; } .overview-body { max-height: 520px; } }
.review-dialog-header { display: flex; align-items: center; gap: 14px; }
.review-dialog-header h3 { margin: 0 0 5px; color: #172033; font-size: 19px; }
.review-dialog-header p { margin: 0; color: #8491a5; font-size: 12px; }
.review-orbit { position: relative; width: 42px; height: 42px; border: 2px solid #d9e9ff; border-radius: 50%; }
.review-orbit::before { content: ""; position: absolute; inset: 5px; border: 2px solid #1677ff; border-right-color: transparent; border-radius: 50%; animation: review-spin 1s linear infinite; }
.review-orbit span { position: absolute; top: 16px; left: 16px; width: 6px; height: 6px; border-radius: 50%; background: #1677ff; }
.review-orbit.done::before { border-color: #20a162; animation: none; }
.review-orbit.done span { background: #20a162; }
.review-progress-overview { display: flex; align-items: baseline; justify-content: space-between; gap: 18px; margin-bottom: 10px; color: #7b879a; font-size: 12px; }
.review-share-card { margin-bottom: 18px; }
.review-progress-overview strong { margin-right: 3px; color: #172033; font-size: 28px; }
.review-statement-list { display: grid; gap: 10px; max-height: min(300px, 32vh); margin-top: 18px; overflow: auto; padding-right: 4px; }
.review-statement { display: grid; grid-template-columns: 34px minmax(0,1fr); gap: 11px; padding: 13px; border: 1px solid #e5eaf2; border-radius: 8px; background: #fff; transition: .25s ease; }
.review-statement.is-reviewing { border-color: #8fc1ff; background: #f6faff; box-shadow: 0 5px 18px rgba(22,119,255,.09); transform: translateX(3px); }
.review-state-mark { display: grid; place-items: center; width: 30px; height: 30px; border-radius: 50%; color: #738197; background: #eef2f7; }
.is-passed .review-state-mark { color: #fff; background: #20a162; }
.is-rejected .review-state-mark,.is-failed .review-state-mark { color: #fff; background: #e5484d; }
.is-reviewing .review-state-mark { color: #1677ff; background: #e7f2ff; }
.review-statement-main>div { display: flex; align-items: center; gap: 8px; }
.review-statement-main code { display: block; margin: 7px 0; color: #27364b; white-space: pre-wrap; word-break: break-all; }
.review-live-output { margin: 8px 0; border-left: 3px solid #8fc1ff; background: #f8fbff; color: #3b4b61; }
.review-live-output details { padding: 7px 9px 0; }
.review-live-output summary { cursor: pointer; color: #6d28d9; font-size: 12px; }
.review-live-output pre { max-height: 150px; margin: 0; padding: 7px 9px; overflow: auto; white-space: pre-wrap; word-break: break-word; font: 12px/1.55 ui-monospace, SFMono-Regular, Menlo, monospace; }
.review-statement-main p { margin: 0; color: #7b879a; font-size: 12px; }
.review-suggestion { margin-top: 5px!important; color: #b56a00!important; }
.review-background-tip { float: left; line-height: 32px; color: #8a95a7; font-size: 12px; }
.review-item-enter-active,.review-item-leave-active { transition: all .25s ease; }
.review-item-enter-from,.review-item-leave-to { opacity: 0; transform: translateY(8px); }
@keyframes review-spin { to { transform: rotate(360deg); } }
</style>
