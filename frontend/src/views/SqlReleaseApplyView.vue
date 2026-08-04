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
            <el-option v-for="item in databaseTypes" :key="item.value" :value="item.value" :label="item.label" />
          </el-select>
        </el-form-item>
        <el-form-item label="环境">
          <el-select v-model="form.environment" :disabled="!form.db_type" filterable placeholder="选择环境" style="width: 100%" @change="onEnvironmentChange">
            <el-option v-for="item in environments" :key="item" :value="item" :label="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="集群">
          <el-select v-model="form.cluster_id" :disabled="!form.environment" filterable placeholder="选择具备变更权限的集群" style="width: 100%" @change="loadDatabases">
            <el-option v-for="item in filteredClusters" :key="item.id" :value="item.id" :label="clusterLabel(item)" />
          </el-select>
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

  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import { Connection, Document, Folder, Grid, Key, Search, View } from "@element-plus/icons-vue";
import { listClusters } from "../api/modules/clusters";
import {
  listSqlReleaseDatabases,
  listSqlReleaseObjects,
  listSqlReleaseTableColumns,
  submitSqlRelease,
} from "../api/modules/sqlReleases";
import SqlEditor from "../components/SqlEditor.vue";
import { extractReleaseObjectNames } from "../utils/sqlRelease";

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
const tableObjects = ref({ tables: [], collections: [], views: [], procedures: [], functions: [], triggers: [], events: [] });
const databaseTypes = [
  { label: "MySQL", value: "mysql" },
  { label: "MongoDB", value: "mongodb" },
  { label: "PostgreSQL", value: "postgresql" },
];
const form = reactive({ title: "", project: "", db_type: "", environment: "", cluster_id: null, database: "", sql: "" });
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

async function submit() {
  if (!form.project || !form.db_type || !form.environment || !form.cluster_id || !form.database || !form.sql.trim()) return ElMessage.warning("请按项目、数据库、环境、集群顺序选择数据源，并填写目标库和变更语句");
  submitting.value = true;
  try {
    await submitSqlRelease({ ...form });
    ElMessage.success("工单已提交，AI 初审正在后台进行");
    form.title = ""; form.sql = "";
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "提交失败");
  } finally { submitting.value = false; }
}

onMounted(async () => {
  const responses = await Promise.all(databaseTypes.map((item) => listClusters(item.value, { action: "change" })));
  clusters.value = responses.flatMap(({ data }) => data.data || []);
});

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
</style>
