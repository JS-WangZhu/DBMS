<template>
  <div class="webql-page">
    <!-- 顶部：数据源选择栏 -->
    <div class="topbar">
      <div class="topbar-left">
        <el-select v-model="form.db_type" size="default" placeholder="选择数据库类型" style="width: 160px" @change="onDbTypeChange">
          <el-option label="MySQL" value="mysql" />
          <el-option label="MongoDB" value="mongodb" />
          <el-option label="Redis" value="redis" />
        </el-select>
        <el-select
          v-model="form.business_line"
          clearable
          placeholder="选择项目"
          size="default"
          style="width: 180px"
          @change="onBusinessLineChange"
        >
          <el-option v-for="line in businessLines" :key="line" :label="line" :value="line" />
        </el-select>
        <el-select
          v-model="form.environment"
          clearable
          placeholder="选择环境"
          size="default"
          style="width: 160px"
          @change="onEnvironmentChange"
        >
          <el-option v-for="env in environments" :key="env" :label="env" :value="env" />
        </el-select>
        <el-select
          v-model="form.cluster_id"
          clearable
          placeholder="选择集群"
          size="default"
          style="width: 260px"
          @change="onClusterChange"
        >
          <el-option
            v-for="cluster in filteredClusters"
            :key="cluster.id"
            :label="clusterLabel(cluster)"
            :value="cluster.id"
          />
        </el-select>
      </div>
      <div class="topbar-right">
        <el-button size="default" @click="reloadOptions">
          <el-icon><Refresh /></el-icon>
          <span>刷新</span>
        </el-button>
      </div>
    </div>

    <!-- 主体：左右分栏 -->
    <div class="webql-body">
      <!-- 左侧 schema 浏览器 -->
      <aside class="schema-panel">
        <div class="schema-header">
          <el-select
            v-if="form.db_type === 'mysql'"
            v-model="form.mysql_db"
            filterable
            allow-create
            default-first-option
            clearable
            size="default"
            class="db-select"
            :loading="mysqlDatabasesLoading"
            placeholder="选择数据库"
            @change="onMysqlDatabaseChange"
          >
            <template #prefix>
              <el-icon><Coin /></el-icon>
            </template>
            <el-option v-for="db in mysqlDatabases" :key="db" :label="db" :value="db" />
          </el-select>
          <el-select
            v-else-if="form.db_type === 'mongodb'"
            v-model="form.mongo_db"
            filterable
            allow-create
            default-first-option
            clearable
            size="default"
            class="db-select"
            :loading="mongoDatabasesLoading"
            placeholder="选择数据库"
            @change="onMongoDatabaseChange"
          >
            <template #prefix>
              <el-icon><Coin /></el-icon>
            </template>
            <el-option v-for="db in mongoDatabases" :key="db" :label="db" :value="db" />
          </el-select>
          <span v-else class="schema-placeholder">Redis 无库浏览</span>
        </div>

        <template v-if="form.db_type === 'mysql' || form.db_type === 'mongodb'">
          <div class="schema-search">
            <el-input v-model="schemaKeyword" size="small" placeholder="搜索对象" clearable>
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
          </div>
          <div class="schema-tree">
            <el-tree
              v-if="schemaTreeData.length"
              ref="schemaTreeRef"
              :data="schemaTreeData"
              :props="schemaTreeProps"
              :filter-node-method="filterSchemaNode"
              node-key="key"
              lazy
              :load="loadSchemaNode"
              highlight-current
              @node-click="onSchemaNodeClick"
            >
              <template #default="{ data }">
                <span class="tree-node">
                  <el-icon v-if="data.kind === 'group'" class="tree-icon">
                    <Folder />
                  </el-icon>
                  <el-icon v-else-if="data.kind === 'table' || data.kind === 'collection'" class="tree-icon tree-icon-table">
                    <Grid />
                  </el-icon>
                  <el-icon v-else-if="data.kind === 'view' || data.kind === 'mongo-view'" class="tree-icon tree-icon-view">
                    <View />
                  </el-icon>
                  <el-icon v-else-if="data.kind === 'column'" class="tree-icon tree-icon-column">
                    <Key v-if="data.raw?.column_key === 'PRI'" />
                    <Connection v-else />
                  </el-icon>
                  <el-icon v-else-if="data.kind === 'field'" class="tree-icon tree-icon-column">
                    <Connection />
                  </el-icon>
                  <el-icon v-else-if="data.kind === 'index'" class="tree-icon">
                    <Key />
                  </el-icon>
                  <el-icon v-else class="tree-icon">
                    <Document />
                  </el-icon>
                  <span class="tree-label" :title="data.tooltip || data.label">{{ data.label }}</span>
                  <span v-if="data.suffix" class="tree-suffix">{{ data.suffix }}</span>
                </span>
              </template>
            </el-tree>
            <el-empty v-else description="请选择数据库" :image-size="80" />
          </div>
        </template>
        <template v-else>
          <div class="schema-tip">当前数据库类型无需对象浏览。</div>
        </template>
      </aside>

      <!-- 右侧编辑区 -->
      <main class="editor-panel">
        <!-- 工具条 -->
        <div class="editor-toolbar">
          <div class="toolbar-left">
            <template v-if="form.db_type === 'mysql'">
              <span class="current-db" :title="form.mysql_db || ''">
                <el-icon><Coin /></el-icon>
                <span>{{ form.mysql_db || "未选择数据库" }}</span>
              </span>
            </template>
            <template v-else-if="form.db_type === 'mongodb'">
              <span class="current-db" :title="form.mongo_db || ''">
                <el-icon><Coin /></el-icon>
                <span>{{ form.mongo_db || "未选择数据库" }}</span>
              </span>
            </template>
            <template v-else>
              <span class="current-db">
                <el-icon><Coin /></el-icon>
                <span>Redis</span>
              </span>
            </template>
          </div>
          <div class="toolbar-right">
            <el-button type="primary" :loading="running" @click="runQuery">
              <el-icon><VideoPlay /></el-icon>
              <span>执行</span>
              <span class="shortcut-hint">Ctrl+Enter</span>
            </el-button>
            <el-button
              v-if="form.db_type !== 'redis'"
              class="ai-analyze-btn"
              :loading="aiAnalyzing"
              @click="openAIAnalysis"
            >
              <el-icon><MagicStick /></el-icon>
              <span>AI 分析</span>
            </el-button>
            <el-button v-if="running" type="warning" plain @click="cancelRunningQuery">
              <el-icon><CircleClose /></el-icon>
              <span>取消</span>
            </el-button>
          </div>
        </div>

        <!-- AI 智能分析弹窗 -->
        <el-dialog
          v-model="aiDialogVisible"
          :fullscreen="aiFullscreen"
          :width="aiFullscreen ? '100%' : '1080px'"
          :close-on-click-modal="false"
          :show-close="false"
          append-to-body
          destroy-on-close
          class="ai-analyze-dialog"
          @close="onAIDialogClose"
        >
          <template #header>
            <div class="ai-dialog-header">
              <div class="ai-dialog-title">
                <span class="ai-title-icon"><el-icon><MagicStick /></el-icon></span>
                <span>AI 智能分析</span>
                <el-tag v-if="aiAnalyzing" size="small" effect="light" class="ai-running-tag">思考中...</el-tag>
              </div>
              <div class="ai-dialog-actions">
                <el-button size="small" plain @click="aiFullscreen = !aiFullscreen">
                  <el-icon><FullScreen /></el-icon>
                  <span>{{ aiFullscreen ? "退出全屏" : "全屏" }}</span>
                </el-button>
                <el-button size="small" text @click="aiDialogVisible = false">
                  <el-icon><Close /></el-icon>
                </el-button>
              </div>
            </div>
          </template>

          <div class="ai-dialog-body">
            <div class="ai-pane ai-pane-source">
              <div class="ai-pane-header">
                <span>源{{ form.db_type === 'mongodb' ? '命令' : 'SQL' }}</span>
                <el-button size="small" link @click="copyAISource">复制</el-button>
              </div>
              <pre class="ai-source-pre"><code>{{ aiSourceText || "(空)" }}</code></pre>
            </div>
            <div class="ai-pane ai-pane-result">
              <div class="ai-pane-header">
                <span>智能生成结果</span>
                <el-button
                  v-if="aiResultText && !aiAnalyzing"
                  size="small"
                  link
                  @click="copyAIResult"
                >复制</el-button>
              </div>
              <div class="ai-result-box" ref="aiResultBoxRef">
                <div v-if="aiAnalyzing && !aiResultText" class="ai-loading">
                  <span class="ai-loading-dot"></span>
                  <span>AI 正在深度思考，请稍候...</span>
                </div>
                <div v-else-if="!aiResultText" class="ai-empty">点击 AI 分析按钮开始</div>
                <div v-else class="markdown-content" v-html="renderMarkdown(aiResultText)"></div>
              </div>
            </div>
          </div>

          <template #footer>
            <div class="ai-dialog-footer">
              <el-button v-if="aiAnalyzing" type="warning" plain @click="stopAIAnalysis">停止</el-button>
              <el-button v-else type="primary" @click="restartAIAnalysis" :disabled="!aiSourceText">重新分析</el-button>
              <el-button @click="aiDialogVisible = false">关 闭</el-button>
            </div>
          </template>
        </el-dialog>

        <!-- 编辑区 -->
        <div class="editor-area">
          <SqlEditor
            v-if="form.db_type === 'mysql'"
            ref="sqlEditorRef"
            v-model="form.sql"
            mode="sql"
            placeholder="SELECT * FROM table LIMIT 100;"
            :min-height="260"
            :schema="sqlSchema"
            @run="runQuery"
          />
          <SqlEditor
            v-else-if="form.db_type === 'mongodb'"
            ref="mongoEditorRef"
            v-model="form.mongo_command"
            mode="mongodb"
            placeholder='例如：db.test_collection.find({name:"Gemini"}).limit(10)'
            :min-height="260"
            :schema="mongoSchema"
            @run="runQuery"
          />
          <SqlEditor
            v-else
            ref="redisEditorRef"
            v-model="form.redis_command"
            mode="redis"
            placeholder="例如：GET user:1 或 HGET user:1 name"
            :min-height="220"
            @run="runQuery"
          />
          <div v-if="form.db_type === 'mongodb'" class="editor-hint">
            支持 MongoDB shell 风格的只读查询语句（find/findOne/aggregate/count）
          </div>
          <div v-else-if="form.db_type === 'redis'" class="editor-hint">
            直接输入基础命令，系统会自动解析参数
          </div>
        </div>

        <!-- 结果区 -->
        <div class="result-area">
          <div class="result-tabs">
            <div class="result-tab" :class="{ active: activeResultTab === 'result' }" @click="activeResultTab = 'result'">
              结果集
            </div>
            <div class="result-tab" :class="{ active: activeResultTab === 'info' }" @click="activeResultTab = 'info'">
              执行信息
            </div>
            <div class="result-spacer" />
            <span v-if="resultVisible && tableRows.length" class="result-count">共 {{ tableRows.length }} 条</span>
            <el-button v-if="resultVisible" size="small" text @click="clearResult">清空</el-button>
          </div>

          <div class="result-body">
            <template v-if="activeResultTab === 'result'">
              <el-empty v-if="!resultVisible" description="点击执行按钮查看结果" :image-size="70" />
              <template v-else>
                <el-table v-if="tableColumns.length" :data="pagedTableRows" stripe size="small" border>
                  <el-table-column
                    v-for="col in tableColumns"
                    :key="col"
                    :prop="col"
                    :label="col"
                    min-width="140"
                    show-overflow-tooltip
                  />
                </el-table>
                <el-tree
                  v-else-if="isMongoResult"
                  :data="mongoTreeData"
                  node-key="id"
                  :props="mongoTreeProps"
                  default-expand-all
                  class="json-tree"
                />
                <el-input v-else v-model="rawResult" type="textarea" :rows="10" readonly />
                <div v-if="tableColumns.length" class="pagination-row">
                  <el-pagination
                    v-model:current-page="currentPage"
                    v-model:page-size="pageSize"
                    :page-sizes="[20, 50, 100, 200]"
                    :total="tableRows.length"
                    layout="total, sizes, prev, pager, next, jumper"
                    background
                    small
                  />
                </div>
              </template>
            </template>

            <template v-else>
              <div class="info-panel">
                <div v-if="!connectionInfo" class="info-placeholder">暂无执行记录</div>
                <template v-else>
                  <div class="info-row"><span class="info-label">集群：</span>{{ connectionInfo.cluster?.name || "-" }}</div>
                  <div class="info-row"><span class="info-label">实例：</span>{{ connectionInfo.instance?.name || "-" }}</div>
                  <div class="info-row">
                    <span class="info-label">地址：</span>
                    {{ (connectionInfo.instance?.resolved_ip || connectionInfo.instance?.host_input || "-") }}:{{
                      connectionInfo.instance?.port || "-"
                    }}
                  </div>
                  <div class="info-row"><span class="info-label">数据库：</span>{{ connectionInfo.database || "-" }}</div>
                  <div class="info-row">
                    <span class="info-label">耗时：</span>{{ lastElapsedMs >= 0 ? `${lastElapsedMs} ms` : "-" }}
                  </div>
                </template>
              </div>
            </template>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import {
  CircleClose,
  Close,
  Coin,
  Connection,
  Document,
  Folder,
  FullScreen,
  Grid,
  Key,
  MagicStick,
  Refresh,
  Search,
  VideoPlay,
  View,
} from "@element-plus/icons-vue";

import SqlEditor from "../components/SqlEditor.vue";
import { listClusters } from "../api/modules/clusters";
import {
  cancelDataAccessExecution,
  describeMongoCollection,
  listMongoCollections,
  listMongoDatabases,
  listMysqlDatabases,
  listMysqlObjects,
  listMysqlTableColumns,
  queryData,
} from "../api/modules/data_access";

const form = reactive({
  db_type: "mysql",
  business_line: "",
  environment: "",
  cluster_id: null,
  sql: "",
  mysql_db: "",
  mongo_db: "admin",
  mongo_command: "",
  redis_command: "",
});

const clusters = ref([]);
const running = ref(false);
const resultVisible = ref(false);
const tableColumns = ref([]);
const tableRows = ref([]);
const rawResult = ref("");
const currentPage = ref(1);
const pageSize = ref(50);
const mongoDatabases = ref([]);
const mongoDatabasesLoading = ref(false);
const mysqlDatabases = ref([]);
const mysqlDatabasesLoading = ref(false);
const mongoTreeData = ref([]);
const connectionInfo = ref(null);
const currentExecutionId = ref("");
const activeResultTab = ref("result");
const lastElapsedMs = ref(-1);
const schemaKeyword = ref("");
const schemaTreeRef = ref(null);
const sqlEditorRef = ref(null);
const mongoEditorRef = ref(null);
const redisEditorRef = ref(null);

/** 左侧树数据（由数据库切换驱动） */
const schemaTreeData = ref([]);
const schemaObjects = ref({ tables: [], views: [], procedures: [], functions: [], triggers: [], events: [] });
const mongoSchemaObjects = ref({ collections: [], views: [] });
/** table -> columns 缓存 */
const tableColumnsCache = reactive({});
/** mongo collection -> {sample_fields, indexes, doc_count, size_bytes} 缓存 */
const mongoCollectionInfoCache = reactive({});

const schemaTreeProps = {
  children: "children",
  label: "label",
  isLeaf: "leaf",
};

const mongoTreeProps = {
  children: "children",
  label: "label",
};

const businessLines = computed(() => {
  const set = new Set(clusters.value.map((c) => c.business_line || c.namespace).filter(Boolean));
  return Array.from(set).sort();
});

const environments = computed(() => {
  const source = form.business_line
    ? clusters.value.filter((c) => (c.business_line || c.namespace) === form.business_line)
    : clusters.value;
  const set = new Set(source.map((c) => c.environment).filter(Boolean));
  return Array.from(set).sort();
});

const filteredClusters = computed(() => {
  let list = clusters.value;
  if (form.business_line) {
    list = list.filter((c) => (c.business_line || c.namespace) === form.business_line);
  }
  if (form.environment) {
    list = list.filter((c) => c.environment === form.environment);
  }
  return list;
});

const pagedTableRows = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value;
  return tableRows.value.slice(start, start + pageSize.value);
});

const isMongoResult = computed(() => form.db_type === "mongodb");

/** 供 SqlEditor 补全使用 */
const sqlSchema = computed(() => {
  const tables = (schemaObjects.value.tables || []).map((t) => ({
    name: t.name,
    row_count: t.row_count,
    columns: tableColumnsCache[t.name] || [],
  }));
  const views = (schemaObjects.value.views || []).map((v) => ({ name: v.name }));
  return { tables, views };
});

/** 供 MongoDB SqlEditor 补全使用 */
const mongoSchema = computed(() => {
  const collections = (mongoSchemaObjects.value.collections || []).map((c) => ({
    name: c.name,
    fields: (mongoCollectionInfoCache[c.name]?.sample_fields) || [],
  }));
  const views = (mongoSchemaObjects.value.views || []).map((v) => ({ name: v.name }));
  return { collections, views };
});

function clusterLabel(cluster) {
  return cluster.name || `集群-${cluster.id}`;
}

async function loadClusters() {
  const { data } = await listClusters(form.db_type, { action: "query" });
  clusters.value = data.data || [];
}

async function reloadOptions() {
  await loadClusters();
  await loadMysqlDatabasesOptions(true);
  await loadMongoDatabasesOptions(true);
}

function onDbTypeChange() {
  form.business_line = "";
  form.environment = "";
  form.cluster_id = null;
  form.mysql_db = "";
  form.mongo_db = "admin";
  form.mongo_command = "";
  form.redis_command = "";
  mysqlDatabases.value = [];
  mongoDatabases.value = [];
  resetSchema();
  reloadOptions();
}

function onBusinessLineChange() {
  form.environment = "";
  form.cluster_id = null;
  form.mysql_db = "";
  form.mongo_db = "admin";
  mysqlDatabases.value = [];
  mongoDatabases.value = [];
  resetSchema();
}

function onEnvironmentChange() {
  form.cluster_id = null;
  form.mysql_db = "";
  form.mongo_db = "admin";
  mysqlDatabases.value = [];
  mongoDatabases.value = [];
  resetSchema();
}

async function onClusterChange() {
  resetSchema();
  await loadMysqlDatabasesOptions();
  await loadMongoDatabasesOptions();
  if (form.db_type === "mysql" && form.mysql_db) {
    await loadMysqlSchema();
  } else if (form.db_type === "mongodb" && form.mongo_db) {
    await loadMongoSchema();
  }
}

async function onMysqlDatabaseChange() {
  await loadMysqlSchema();
}

async function onMongoDatabaseChange() {
  await loadMongoSchema();
}

function resetSchema() {
  schemaTreeData.value = [];
  schemaObjects.value = { tables: [], views: [], procedures: [], functions: [], triggers: [], events: [] };
  mongoSchemaObjects.value = { collections: [], views: [] };
  for (const key of Object.keys(tableColumnsCache)) delete tableColumnsCache[key];
  for (const key of Object.keys(mongoCollectionInfoCache)) delete mongoCollectionInfoCache[key];
}

async function loadMysqlDatabasesOptions(silent = false) {
  if (form.db_type !== "mysql" || !form.cluster_id) {
    mysqlDatabases.value = [];
    form.mysql_db = "";
    return;
  }
  mysqlDatabasesLoading.value = true;
  try {
    const { data } = await listMysqlDatabases(form.cluster_id);
    const list = data?.data?.databases || [];
    mysqlDatabases.value = list;
    if (list.length && !list.includes(form.mysql_db)) {
      form.mysql_db = list[0];
    }
  } catch (error) {
    if (!silent) {
      ElMessage.warning(error.response?.data?.message || "加载 MySQL 数据库列表失败");
    }
  } finally {
    mysqlDatabasesLoading.value = false;
  }
}

async function loadMongoDatabasesOptions(silent = false) {
  if (form.db_type !== "mongodb" || !form.cluster_id) {
    mongoDatabases.value = [];
    form.mongo_db = "admin";
    return;
  }
  mongoDatabasesLoading.value = true;
  try {
    const { data } = await listMongoDatabases(form.cluster_id);
    const list = data?.data?.databases || [];
    mongoDatabases.value = list;
    if (list.length && !list.includes(form.mongo_db)) {
      form.mongo_db = list[0];
    } else if (!list.length && !form.mongo_db) {
      form.mongo_db = "admin";
    }
  } catch (error) {
    if (!silent) {
      ElMessage.warning(error.response?.data?.message || "加载 MongoDB 数据库列表失败");
    }
  } finally {
    mongoDatabasesLoading.value = false;
  }
}

async function loadMysqlSchema() {
  if (!form.cluster_id || !form.mysql_db) {
    schemaTreeData.value = [];
    return;
  }
  try {
    const { data } = await listMysqlObjects(form.cluster_id, form.mysql_db);
    const payload = data?.data || {};
    schemaObjects.value = {
      tables: payload.tables || [],
      views: payload.views || [],
      procedures: payload.procedures || [],
      functions: payload.functions || [],
      triggers: payload.triggers || [],
      events: payload.events || [],
    };
    schemaTreeData.value = buildSchemaTree(schemaObjects.value);
  } catch (error) {
    ElMessage.warning(error.response?.data?.message || "加载数据库对象失败");
    schemaTreeData.value = [];
  }
}

async function loadMongoSchema() {
  if (!form.cluster_id || !form.mongo_db) {
    schemaTreeData.value = [];
    mongoSchemaObjects.value = { collections: [], views: [] };
    return;
  }
  try {
    const { data } = await listMongoCollections(form.cluster_id, form.mongo_db);
    const payload = data?.data || {};
    const collections = payload.collections || [];
    const views = payload.views || [];
    mongoSchemaObjects.value = { collections, views };
    schemaTreeData.value = buildMongoSchemaTree(collections, views);
  } catch (error) {
    ElMessage.warning(error.response?.data?.message || "加载集合列表失败");
    schemaTreeData.value = [];
    mongoSchemaObjects.value = { collections: [], views: [] };
  }
}

function buildSchemaTree(objects) {
  const mkGroup = (label, kind, items, toChild) => {
    const children = (items || []).map(toChild);
    return {
      key: `group:${kind}`,
      label: `${label} (${items?.length || 0})`,
      kind: "group",
      leaf: children.length === 0,
      _children: children,
    };
  };
  const tablesGroup = mkGroup("Tables", "tables", objects.tables, (t) => ({
    key: `table:${t.name}`,
    label: t.name,
    kind: "table",
    raw: t,
    suffix: formatSize(t.size_bytes),
    tooltip: `${t.name}${t.size_bytes ? ` · ${formatSize(t.size_bytes)}` : ""}`,
    leaf: false,
  }));
  const viewsGroup = mkGroup("Views", "views", objects.views, (v) => ({
    key: `view:${v.name}`,
    label: v.name,
    kind: "view",
    raw: v,
    leaf: true,
  }));
  const procGroup = mkGroup("Procedures", "procedures", objects.procedures, (p) => ({
    key: `procedure:${p.name}`,
    label: p.name,
    kind: "procedure",
    raw: p,
    leaf: true,
  }));
  const funcGroup = mkGroup("Functions", "functions", objects.functions, (f) => ({
    key: `function:${f.name}`,
    label: f.name,
    kind: "function",
    raw: f,
    leaf: true,
  }));
  const trigGroup = mkGroup("Triggers", "triggers", objects.triggers, (t) => ({
    key: `trigger:${t.name}`,
    label: t.name,
    kind: "trigger",
    raw: t,
    leaf: true,
  }));
  const evtGroup = mkGroup("Events", "events", objects.events, (e) => ({
    key: `event:${e.name}`,
    label: e.name,
    kind: "event",
    raw: e,
    leaf: true,
  }));
  return [tablesGroup, viewsGroup, procGroup, funcGroup, trigGroup, evtGroup];
}

function buildMongoSchemaTree(collections, views) {
  const mkGroup = (label, kind, items, toChild) => {
    const children = (items || []).map(toChild);
    return {
      key: `group:${kind}`,
      label: `${label} (${items?.length || 0})`,
      kind: "group",
      leaf: children.length === 0,
      _children: children,
    };
  };
  const collGroup = mkGroup("Collections", "collections", collections, (c) => ({
    key: `collection:${c.name}`,
    label: c.name,
    kind: "collection",
    raw: c,
    tooltip: c.name,
    leaf: false,
  }));
  const viewGroup = mkGroup("Views", "mongo-views", views, (v) => ({
    key: `mongo-view:${v.name}`,
    label: v.name,
    kind: "mongo-view",
    raw: v,
    leaf: true,
  }));
  return [collGroup, viewGroup];
}

function formatSize(bytes) {
  const n = Number(bytes || 0);
  if (!n) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

function filterSchemaNode(keyword, data) {
  if (!keyword) return true;
  if (data.kind === "group") return true;
  return `${data.label || ""}`.toLowerCase().includes(keyword.toLowerCase());
}

async function loadSchemaNode(node, resolve) {
  const data = node.data;
  if (!data) return resolve([]);
  if (data.kind === "group") {
    return resolve(data._children || []);
  }
  if (data.kind === "table") {
    const cached = tableColumnsCache[data.label];
    if (cached) {
      return resolve(cached.map((c) => columnToTreeNode(data.label, c)));
    }
    try {
      const res = await listMysqlTableColumns(form.cluster_id, form.mysql_db, data.label);
      const cols = res.data?.data?.columns || [];
      tableColumnsCache[data.label] = cols;
      resolve(cols.map((c) => columnToTreeNode(data.label, c)));
    } catch (error) {
      ElMessage.warning(error.response?.data?.message || "加载列信息失败");
      resolve([]);
    }
    return;
  }
  if (data.kind === "collection") {
    const cached = mongoCollectionInfoCache[data.label];
    if (cached) {
      return resolve(buildMongoCollectionChildren(data.label, cached));
    }
    try {
      const res = await describeMongoCollection(form.cluster_id, form.mongo_db, data.label);
      const info = res.data?.data || {};
      mongoCollectionInfoCache[data.label] = info;
      resolve(buildMongoCollectionChildren(data.label, info));
    } catch (error) {
      ElMessage.warning(error.response?.data?.message || "加载集合信息失败");
      resolve([]);
    }
    return;
  }
  return resolve([]);
}

function buildMongoCollectionChildren(collectionName, info) {
  const nodes = [];
  const fields = Array.isArray(info.sample_fields) ? info.sample_fields : [];
  const indexes = Array.isArray(info.indexes) ? info.indexes : [];
  if (fields.length) {
    nodes.push({
      key: `mongo-fields:${collectionName}`,
      label: `Fields (${fields.length})`,
      kind: "group",
      leaf: false,
      _children: fields.map((f) => ({
        key: `field:${collectionName}.${f.name}`,
        label: f.name,
        kind: "field",
        raw: f,
        suffix: f.type || "",
        tooltip: `${f.name} : ${f.type || ""}`,
        leaf: true,
      })),
    });
  }
  if (indexes.length) {
    nodes.push({
      key: `mongo-indexes:${collectionName}`,
      label: `Indexes (${indexes.length})`,
      kind: "group",
      leaf: false,
      _children: indexes.map((idx) => ({
        key: `index:${collectionName}.${idx.name}`,
        label: idx.name,
        kind: "index",
        raw: idx,
        suffix: idx.unique ? "unique" : "",
        tooltip: (idx.key || []).map((it) => `${it[0]}:${it[1]}`).join(", "),
        leaf: true,
      })),
    });
  }
  if (typeof info.doc_count === "number" || typeof info.size_bytes === "number") {
    const stat = [];
    if (typeof info.doc_count === "number") stat.push(`文档 ${info.doc_count}`);
    if (typeof info.size_bytes === "number") stat.push(formatSize(info.size_bytes));
    nodes.push({
      key: `mongo-stat:${collectionName}`,
      label: stat.join(" · ") || "统计",
      kind: "info",
      leaf: true,
    });
  }
  if (!nodes.length) {
    nodes.push({
      key: `mongo-empty:${collectionName}`,
      label: "暂无字段样本",
      kind: "info",
      leaf: true,
    });
  }
  return nodes;
}

function columnToTreeNode(tableName, col) {
  const typeHint = col.column_type || col.data_type || "";
  return {
    key: `column:${tableName}.${col.name}`,
    label: col.name,
    kind: "column",
    raw: col,
    suffix: typeHint,
    tooltip: `${col.name} ${typeHint}${col.comment ? ` · ${col.comment}` : ""}`,
    leaf: true,
  };
}

function onSchemaNodeClick(data) {
  if (!data) return;
  if (data.kind === "table" || data.kind === "view") {
    sqlEditorRef.value?.insertText(`\`${data.label}\``);
  } else if (data.kind === "column") {
    sqlEditorRef.value?.insertText(`\`${data.label}\``);
  } else if (data.kind === "collection" || data.kind === "mongo-view") {
    const snippet = `db.${data.label}.find({}).limit(10)`;
    if (mongoEditorRef.value?.insertText) {
      mongoEditorRef.value.insertText(snippet);
    } else {
      form.mongo_command = snippet;
    }
  } else if (data.kind === "field") {
    if (form.db_type === "mongodb") {
      const snippet = `"${data.label}": `;
      if (mongoEditorRef.value?.insertText) {
        mongoEditorRef.value.insertText(snippet);
      } else {
        form.mongo_command = form.mongo_command
          ? `${form.mongo_command}${form.mongo_command.endsWith(" ") ? "" : " "}${snippet}`
          : snippet;
      }
    }
  }
}

/** 过滤关键字变化时触发树过滤 */
function applySchemaFilter() {
  nextTick(() => schemaTreeRef.value?.filter(schemaKeyword.value || ""));
}

watch(schemaKeyword, () => applySchemaFilter());

function tokenizeCommandLine(raw) {
  const source = `${raw || ""}`.trim();
  if (!source) return [];
  const parts = source.match(/"[^"\\]*(?:\\.[^"\\]*)*"|'[^'\\]*(?:\\.[^'\\]*)*'|\S+/g) || [];
  return parts.map((part) => {
    if ((part.startsWith('"') && part.endsWith('"')) || (part.startsWith("'") && part.endsWith("'"))) {
      return part.slice(1, -1).replace(/\\"/g, '"').replace(/\\'/g, "'");
    }
    return part;
  });
}

function buildRedisCommandPayload() {
  const tokens = tokenizeCommandLine(form.redis_command);
  if (!tokens.length) return null;
  return { command: tokens[0].toUpperCase(), args: tokens.slice(1) };
}

function stringifyLeafValue(value) {
  if (typeof value === "string") return `"${value}"`;
  return String(value);
}

function buildJsonTreeNode(key, value, path) {
  if (Array.isArray(value)) {
    return {
      id: path,
      label: `${key}: [${value.length}]`,
      children: value.map((item, index) => buildJsonTreeNode(`[${index}]`, item, `${path}.${index}`)),
    };
  }
  if (value && typeof value === "object") {
    const entries = Object.entries(value);
    return {
      id: path,
      label: `${key}: {${entries.length}}`,
      children: entries.map(([ck, cv]) => buildJsonTreeNode(ck, cv, `${path}.${ck}`)),
    };
  }
  return { id: path, label: `${key}: ${stringifyLeafValue(value)}` };
}

function buildMongoTree(value) {
  return [buildJsonTreeNode("result", value, "root")];
}

function clearResult() {
  tableColumns.value = [];
  tableRows.value = [];
  mongoTreeData.value = [];
  connectionInfo.value = null;
  rawResult.value = "";
  currentPage.value = 1;
  resultVisible.value = false;
  lastElapsedMs.value = -1;
}

function buildExecutionId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return window.crypto.randomUUID().replace(/-/g, "");
  }
  return `${Date.now()}${Math.random().toString(16).slice(2)}`;
}

async function cancelRunningQuery() {
  if (!currentExecutionId.value) {
    ElMessage.warning("当前无可取消任务");
    return;
  }
  try {
    await cancelDataAccessExecution(currentExecutionId.value);
    ElMessage.success("已发送取消请求");
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "取消失败");
  }
}

async function runQuery() {
  if (!form.cluster_id) {
    ElMessage.warning("请选择项目、环境和集群");
    return;
  }
  if (form.db_type === "mysql") {
    if (!form.sql.trim()) {
      ElMessage.warning("请填写 SQL");
      return;
    }
    if (!`${form.mysql_db || ""}`.trim()) {
      ElMessage.warning("请选择或输入 MySQL 数据库");
      return;
    }
  }
  if (form.db_type === "mongodb" && !form.mongo_command.trim()) {
    ElMessage.warning("请填写 Mongo 命令");
    return;
  }
  if (form.db_type === "redis" && !form.redis_command.trim()) {
    ElMessage.warning("请填写 Redis 命令");
    return;
  }

  running.value = true;
  currentExecutionId.value = buildExecutionId();
  const startedAt = Date.now();
  try {
    const redisQuery = form.db_type === "redis" ? buildRedisCommandPayload() : undefined;
    if (form.db_type === "redis" && !redisQuery) {
      ElMessage.warning("Redis 命令格式无效");
      return;
    }
    const payload = {
      db_type: form.db_type,
      business_line: form.business_line || undefined,
      environment: form.environment || undefined,
      cluster_id: form.cluster_id,
      sql: form.db_type === "mysql" ? form.sql : undefined,
      database: form.db_type === "mysql" ? `${form.mysql_db || ""}`.trim() : undefined,
      mongo_command: form.db_type === "mongodb" ? form.mongo_command : undefined,
      mongo_database: form.db_type === "mongodb" ? `${form.mongo_db || ""}`.trim() : undefined,
      query: form.db_type === "redis" ? redisQuery : undefined,
      execution_id: currentExecutionId.value,
    };
    const { data } = await queryData(payload);
    const result = data?.data?.result || {};
    tableColumns.value = result.columns || [];
    tableRows.value = result.rows || [];
    mongoTreeData.value = form.db_type === "mongodb" ? buildMongoTree(result.rows || result) : [];
    connectionInfo.value = data?.data?.connection_info || null;
    currentPage.value = 1;
    rawResult.value = JSON.stringify(result.rows || result, null, 2);
    lastElapsedMs.value = Date.now() - startedAt;
    if (result.truncated) {
      ElMessage.warning("查询结果已限制为最多 1000 条记录");
    }
    resultVisible.value = true;
    activeResultTab.value = "result";
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "查询失败");
  } finally {
    running.value = false;
    currentExecutionId.value = "";
  }
}

// ================ AI 智能分析 ================
const aiDialogVisible = ref(false);
const aiFullscreen = ref(false);
const aiAnalyzing = ref(false);
const aiSourceText = ref("");
const aiResultText = ref("");
const aiResultBoxRef = ref(null);
let aiAbortController = null;

function getCurrentStatement() {
  if (form.db_type === "mysql") return (form.sql || "").trim();
  if (form.db_type === "mongodb") return (form.mongo_command || "").trim();
  return "";
}

function getCurrentDatabase() {
  if (form.db_type === "mysql") return `${form.mysql_db || ""}`.trim();
  if (form.db_type === "mongodb") return `${form.mongo_db || ""}`.trim();
  return "";
}

function openAIAnalysis() {
  if (form.db_type === "redis") {
    ElMessage.warning("Redis 暂不支持 AI 分析");
    return;
  }
  if (!form.cluster_id) {
    ElMessage.warning("请先选择集群");
    return;
  }
  const stmt = getCurrentStatement();
  if (!stmt) {
    ElMessage.warning("请先在编辑器中录入待分析的语句");
    return;
  }
  const dbName = getCurrentDatabase();
  if (!dbName) {
    ElMessage.warning(`请先选择 ${form.db_type === "mysql" ? "MySQL" : "MongoDB"} 数据库`);
    return;
  }
  aiSourceText.value = stmt;
  aiResultText.value = "";
  aiDialogVisible.value = true;
  nextTick(() => startAIAnalysisStream());
}

function restartAIAnalysis() {
  aiResultText.value = "";
  startAIAnalysisStream();
}

function stopAIAnalysis() {
  if (aiAbortController) {
    try { aiAbortController.abort(); } catch {}
    aiAbortController = null;
  }
  aiAnalyzing.value = false;
}

function onAIDialogClose() {
  stopAIAnalysis();
  aiFullscreen.value = false;
}

async function startAIAnalysisStream() {
  const payload = {
    db_type: form.db_type,
    business_line: form.business_line || undefined,
    environment: form.environment || undefined,
    cluster_id: form.cluster_id,
    database: getCurrentDatabase(),
    statement: aiSourceText.value,
  };
  aiAnalyzing.value = true;
  aiResultText.value = "";
  aiAbortController = new AbortController();
  let acc = "";
  try {
    const token = localStorage.getItem("dbms_token");
    const response = await fetch("/api/v1/ai/analyze/stream", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
      signal: aiAbortController.signal,
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.message || "请求失败");
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data: ")) continue;
        try {
          const data = JSON.parse(trimmed.slice(6));
          if (data.error) {
            ElMessage.error(data.error);
            continue;
          }
          if (data.content) acc += data.content;
          aiResultText.value = acc;
          nextTick(() => {
            const el = aiResultBoxRef.value;
            if (el) el.scrollTop = el.scrollHeight;
          });
        } catch {}
      }
    }
  } catch (error) {
    if (error.name !== "AbortError") {
      ElMessage.error(error.message || "AI 分析失败");
    }
  } finally {
    aiAnalyzing.value = false;
    aiAbortController = null;
  }
}

function copyAISource() {
  copyToClipboard(aiSourceText.value, "源语句已复制");
}
function copyAIResult() {
  copyToClipboard(aiResultText.value, "分析结果已复制");
}
function copyToClipboard(text, msg) {
  if (!text) return;
  if (navigator.clipboard && window.isSecureContext) {
    navigator.clipboard.writeText(text).then(() => ElMessage.success(msg)).catch(() => fallbackCopy(text, msg));
  } else {
    fallbackCopy(text, msg);
  }
}
function fallbackCopy(text, msg) {
  const ta = document.createElement("textarea");
  ta.value = text;
  ta.style.position = "fixed";
  ta.style.left = "-9999px";
  document.body.appendChild(ta);
  ta.select();
  try { document.execCommand("copy"); ElMessage.success(msg); } catch { ElMessage.error("复制失败"); }
  document.body.removeChild(ta);
}

// 简易 Markdown 渲染（与 AIAnalysisView 完全一致，支持标题/代码块/表格/加粗/无序与有序列表/think 折叠/状态标签）
function renderMarkdown(text) {
  if (!text) return "";
  let html = text;

  // 1. 处理 <think> 标签
  if (html.includes("<think>")) {
    if (html.includes("</think>")) {
      html = html.replace(/<think>([\s\S]*?)<\/think>/g, (_m, content) => {
        return `<details class="think-details"><summary>AI 思考过程 (已完成)</summary><div class="think-content">${content}</div></details>`;
      });
    } else {
      const parts = html.split("<think>");
      const beforeThink = parts[0];
      const thinking = parts[1] || "";
      html = `${beforeThink}<details open class="think-details thinking"><summary>AI 正在思考...</summary><div class="think-content">${thinking}</div></details>`;
    }
  }

  // 2. 基础转义（保护已生成的 HTML 标签）
  html = html
    .replace(/&/g, "&amp;")
    .replace(/</g, (match, offset) => {
      const sub = html.substring(offset);
      if (
        sub.startsWith("</details>") ||
        sub.startsWith("<details") ||
        sub.startsWith("<summary") ||
        sub.startsWith("</summary") ||
        sub.startsWith('<div class="think-content"') ||
        sub.startsWith("</div>")
      ) {
        return match;
      }
      return "&lt;";
    })
    .replace(/>/g, (match, offset) => {
      const prev = html.substring(0, offset + 1);
      if (
        prev.endsWith("</details>") ||
        prev.endsWith(">") ||
        prev.endsWith("</summary>") ||
        prev.endsWith("</div>")
      ) {
        return match;
      }
      return "&gt;";
    });

  // 3. 代码块
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre class="code-block"><code>$2</code></pre>');

  // 4. 行内代码
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

  // 5. 标题
  html = html.replace(/^### (.*$)/gm, "<h4>$1</h4>");
  html = html.replace(/^## (.*$)/gm, "<h3>$1</h3>");
  html = html.replace(/^# (.*$)/gm, "<h2>$1</h2>");

  // 6. 加粗
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

  // 7. 列表
  html = html.replace(/^\s*[-*+]\s+(.*)$/gm, "<li>$1</li>");
  html = html.replace(/(<li>.*<\/li>)/gs, (match) => {
    if (match.includes("<ul>")) return match;
    return `<ul>${match}</ul>`;
  });
  html = html.replace(/^\s*(\d+)\.\s+(.*)$/gm, '<li data-index="$1">$2</li>');
  html = html.replace(/(<li data-index=.*<\/li>)/gs, (match) => {
    if (match.includes("<ol>")) return match;
    return `<ol>${match}</ol>`;
  });

  // 8. 状态标签
  html = html.replace(/\[可执行\]/g, '<span class="status-tag status-success">[可执行]</span>');
  html = html.replace(/\[建议放行\]/g, '<span class="status-tag status-success">[建议放行]</span>');
  html = html.replace(/\[有风险\]/g, '<span class="status-tag status-warning">[有风险]</span>');
  html = html.replace(/\[语法错误\]/g, '<span class="status-tag status-danger">[语法错误]</span>');
  html = html.replace(/\[禁止执行\]/g, '<span class="status-tag status-danger">[禁止执行]</span>');
  html = html.replace(/\[不建议放行\]/g, '<span class="status-tag status-danger">[不建议放行]</span>');

  // 9. 换行
  html = html.replace(/\n/g, "<br>");

  // 10. 简单表格处理
  const lines = html.split("<br>");
  let inTable = false;
  let tableHtml = "";
  const newLines = [];
  for (let line of lines) {
    if (line.trim().startsWith("|") && line.includes("|")) {
      if (!inTable) {
        inTable = true;
        tableHtml = '<table class="md-table">';
      }
      if (line.includes("---")) continue;
      const cells = line.split("|").filter((c) => c.trim() !== "");
      tableHtml += "<tr>" + cells.map((c) => `<td>${c.trim()}</td>`).join("") + "</tr>";
    } else {
      if (inTable) {
        inTable = false;
        tableHtml += "</table>";
        newLines.push(tableHtml);
      }
      newLines.push(line);
    }
  }
  if (inTable) newLines.push(tableHtml + "</table>");

  return newLines.join("");
}

onMounted(async () => {
  await reloadOptions();
  if (form.db_type === "mysql" && form.cluster_id && form.mysql_db) {
    await loadMysqlSchema();
  } else if (form.db_type === "mongodb" && form.cluster_id && form.mongo_db) {
    await loadMongoSchema();
  }
});
</script>

<style scoped>
.webql-page {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 76px);
  padding: 12px;
  gap: 10px;
  background: #f5f7fb;
}

.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 14px;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.topbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.webql-body {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 10px;
}

.schema-panel {
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}

.schema-header {
  padding: 10px 10px 8px;
  border-bottom: 1px solid #eef2f7;
}

.db-select {
  width: 100%;
}

.schema-placeholder {
  color: #94a3b8;
  font-size: 13px;
}

.schema-search {
  padding: 8px 10px;
  border-bottom: 1px solid #eef2f7;
}

.schema-tree {
  flex: 1;
  overflow: auto;
  padding: 6px 4px;
}

.schema-tip {
  padding: 20px 12px;
  color: #94a3b8;
  font-size: 13px;
  text-align: center;
}

.tree-node {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  width: 100%;
}

.tree-icon {
  font-size: 14px;
  color: #64748b;
}

.tree-icon-table {
  color: #2563eb;
}

.tree-icon-view {
  color: #9333ea;
}

.tree-icon-column {
  color: #0ea5e9;
}

.tree-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tree-suffix {
  color: #94a3b8;
  font-size: 12px;
  margin-left: 6px;
}

.editor-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  overflow: hidden;
}

.editor-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 14px;
  border-bottom: 1px solid #eef2f7;
  background: #fafbff;
}

.current-db {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: #334155;
  font-size: 13px;
  font-weight: 500;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.shortcut-hint {
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.22);
  font-size: 11px;
  font-weight: 400;
}

/* ============ AI 分析按钮 ============ */
.ai-analyze-btn {
  background: linear-gradient(135deg, #a855f7 0%, #6366f1 100%);
  border: none;
  color: #ffffff;
  font-weight: 500;
  box-shadow: 0 1px 3px rgba(99, 102, 241, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.18);
  transition: all 0.2s ease;
}
.ai-analyze-btn:hover,
.ai-analyze-btn:focus {
  background: linear-gradient(135deg, #9333ea 0%, #4f46e5 100%);
  color: #ffffff;
  box-shadow: 0 3px 10px rgba(99, 102, 241, 0.5), inset 0 1px 0 rgba(255, 255, 255, 0.2);
  transform: translateY(-1px);
}
.ai-analyze-btn:active {
  transform: translateY(0);
  box-shadow: 0 1px 2px rgba(99, 102, 241, 0.5);
}
.ai-analyze-btn.is-loading {
  opacity: 0.85;
}
.ai-analyze-btn :deep(.el-icon) {
  color: #ffffff;
}

/* ============ AI 分析弹窗 ============ */
.ai-analyze-dialog :deep(.el-dialog) {
  border-radius: 12px;
  overflow: hidden;
}
.ai-analyze-dialog :deep(.el-dialog__header) {
  padding: 0;
  margin: 0;
  border-bottom: 1px solid #eef2f7;
}
.ai-analyze-dialog :deep(.el-dialog__body) {
  padding: 0;
  background: #fafbff;
}
.ai-analyze-dialog :deep(.el-dialog__footer) {
  padding: 12px 20px;
  border-top: 1px solid #eef2f7;
  background: #ffffff;
}
.ai-dialog-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  background: linear-gradient(90deg, #f5f3ff 0%, #eef2ff 100%);
}
.ai-dialog-title {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-size: 16px;
  font-weight: 600;
  color: #1e293b;
}
.ai-title-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: linear-gradient(135deg, #a855f7 0%, #6366f1 100%);
  color: #ffffff;
  font-size: 16px;
}
.ai-running-tag {
  background: #ede9fe !important;
  color: #6d28d9 !important;
  border-color: #ddd6fe !important;
}
.ai-dialog-actions { display: inline-flex; align-items: center; gap: 8px; }

.ai-dialog-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
  gap: 0;
  height: 560px;
}
.ai-pane {
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: #ffffff;
}
.ai-pane-source { border-right: 1px solid #eef2f7; background: #f8fafc; }
.ai-pane-result { background: linear-gradient(180deg, #fffbeb 0%, #ffffff 40%); }
.ai-pane-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  font-size: 13px;
  color: #475569;
  border-bottom: 1px solid #eef2f7;
  background: rgba(255, 255, 255, 0.65);
}
.ai-source-pre {
  flex: 1;
  min-height: 0;
  overflow: auto;
  margin: 0;
  padding: 14px 16px;
  font-family: Consolas, "Courier New", monospace;
  font-size: 13px;
  line-height: 1.6;
  color: #0f172a;
  background: transparent;
  white-space: pre-wrap;
  word-break: break-word;
}
.ai-result-box {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 14px 18px;
  font-size: 13px;
  line-height: 1.6;
}
.ai-empty { color: #94a3b8; text-align: center; padding: 40px 0; }
.ai-loading {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: #6d28d9;
  font-size: 13px;
  padding: 6px 10px;
  background: #f5f3ff;
  border-radius: 20px;
}
.ai-loading-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #8b5cf6;
  animation: aiPulse 1.2s ease-in-out infinite;
}
@keyframes aiPulse {
  0%, 100% { opacity: 0.3; transform: scale(0.85); }
  50% { opacity: 1; transform: scale(1); }
}
.ai-dialog-footer { display: flex; justify-content: flex-end; gap: 8px; }

/* ============ Markdown 样式 ============ */
.ai-result-box .markdown-content { color: #1f2328; }
.ai-result-box h2 { font-size: 1.3em; margin: 18px 0 10px; padding-bottom: 4px; border-bottom: 1px solid #e2e8f0; font-weight: 600; }
.ai-result-box h3 { font-size: 1.1em; margin: 14px 0 8px; font-weight: 600; }
.ai-result-box h4 { font-size: 1em; margin: 12px 0 6px; font-weight: 600; }
.ai-result-box .code-block {
  padding: 12px 14px; background: #0f172a; color: #e2e8f0;
  border-radius: 6px; margin: 10px 0; font-size: 12.5px; overflow: auto;
}
.ai-result-box .code-block code { background: transparent; color: inherit; padding: 0; }
.ai-result-box code { padding: 2px 5px; background: rgba(139, 92, 246, 0.12); color: #6d28d9; border-radius: 4px; font-size: 85%; }
.ai-result-box ul { padding-left: 20px; margin: 8px 0; }
.ai-result-box li { margin-bottom: 3px; }
.ai-result-box ol { padding-left: 22px; margin: 8px 0; }
.ai-result-box ol li { margin-bottom: 3px; }
.ai-result-box .md-table {
  border-collapse: collapse;
  margin: 10px 0;
  width: max-content;
  max-width: 100%;
  overflow: auto;
  font-size: 12.5px;
}
.ai-result-box .md-table td {
  padding: 6px 10px;
  border: 1px solid #d0d7de;
}
.ai-result-box .md-table tr { background: #ffffff; }
.ai-result-box .md-table tr:nth-child(even) { background: #f6f8fa; }
.ai-result-box .md-table tr:hover { background: #eef2ff; }
.ai-result-box p { margin: 6px 0; }
.ai-result-box strong { color: #0f172a; }
.ai-result-box .think-details {
  margin: 8px 0; border: 1px solid #e4e7ed; border-radius: 6px; background: #fdfdfd;
}
.ai-result-box .think-details summary {
  padding: 6px 10px; cursor: pointer; color: #64748b; font-size: 12px; background: #f5f7fa; border-radius: 6px;
}
.ai-result-box .think-details.thinking summary { color: #6d28d9; }
.ai-result-box .think-content { padding: 10px; font-size: 12px; color: #64748b; font-style: italic; white-space: pre-wrap; }
.ai-result-box .status-tag {
  display: inline-block; padding: 0 8px; height: 22px; line-height: 20px; font-size: 12px;
  border-radius: 4px; border: 1px solid; margin: 0 4px; font-weight: 600;
}
.ai-result-box .status-success { background: #f0fdf4; border-color: #bbf7d0; color: #16a34a; }
.ai-result-box .status-warning { background: #fffbeb; border-color: #fde68a; color: #d97706; }
.ai-result-box .status-danger { background: #fef2f2; border-color: #fecaca; color: #dc2626; }


.editor-area {
  padding: 10px 14px 6px;
}

.plain-editor :deep(.el-textarea__inner) {
  font-family: Consolas, "Courier New", monospace;
  font-size: 13px;
}

.editor-hint {
  margin-top: 6px;
  color: #94a3b8;
  font-size: 12px;
}

.result-area {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  border-top: 1px solid #eef2f7;
}

.result-tabs {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 14px;
  border-bottom: 1px solid #eef2f7;
  background: #fafbff;
}

.result-tab {
  padding: 4px 12px;
  font-size: 13px;
  color: #64748b;
  cursor: pointer;
  border-radius: 6px;
}

.result-tab:hover {
  color: #2563eb;
}

.result-tab.active {
  color: #1d4ed8;
  background: #dbeafe;
  font-weight: 500;
}

.result-spacer {
  flex: 1;
}

.result-count {
  color: #64748b;
  font-size: 12px;
  margin-right: 8px;
}

.result-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 10px 14px;
}

.pagination-row {
  margin-top: 10px;
  display: flex;
  justify-content: flex-end;
}

.info-panel {
  display: flex;
  flex-direction: column;
  gap: 6px;
  color: #475569;
  font-size: 13px;
}

.info-row {
  display: flex;
  gap: 6px;
}

.info-label {
  color: #94a3b8;
  min-width: 64px;
}

.info-placeholder {
  color: #94a3b8;
  font-size: 13px;
}

.json-tree {
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 8px 10px;
  background: #ffffff;
}

.json-tree :deep(.el-tree-node__content) {
  font-family: Consolas, "Courier New", monospace;
  font-size: 13px;
}
</style>
