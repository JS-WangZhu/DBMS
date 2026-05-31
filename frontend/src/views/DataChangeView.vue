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
        <el-segmented
          v-if="form.db_type === 'mysql'"
          v-model="form.route_mode"
          :options="routeModeOptions"
          size="default"
          @change="onRouteModeChange"
        />
        <el-select
          v-if="form.db_type === 'mysql' && form.route_mode === 'manual'"
          v-model="form.instance_id"
          clearable
          filterable
          placeholder="指定变更实例"
          size="default"
          style="width: 260px"
          @change="onRouteInstanceChange"
        >
          <el-option
            v-for="instance in filteredInstances"
            :key="instance.id"
            :label="instanceLabel(instance)"
            :value="instance.id"
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
              :key="schemaTreeKey"
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
            <el-tag type="danger" size="small" effect="light" round class="change-tag">变更</el-tag>
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
            <el-button type="danger" :loading="running" @click="runChange">
              <el-icon><VideoPlay /></el-icon>
              <span>执行变更</span>
              <span class="shortcut-hint">Ctrl+Enter</span>
            </el-button>
            <el-button v-if="running" type="warning" plain @click="cancelRunningChange">
              <el-icon><CircleClose /></el-icon>
              <span>取消</span>
            </el-button>
          </div>
        </div>

        <!-- 编辑区 -->
        <div class="editor-area">
          <SqlEditor
            v-if="form.db_type === 'mysql'"
            ref="sqlEditorRef"
            v-model="form.sql"
            mode="sql"
            placeholder="例如：INSERT INTO users(name) VALUES('Tom');"
            :min-height="260"
            :schema="sqlSchema"
            @run="runChange"
          />
          <SqlEditor
            v-else-if="form.db_type === 'mongodb'"
            ref="mongoEditorRef"
            v-model="form.mongo_command"
            mode="mongodb"
            placeholder='例如：db.users.updateOne({name:"Gemini"}, {$set:{name:"new"}})'
            :min-height="260"
            :schema="mongoSchema"
            @run="runChange"
          />
          <SqlEditor
            v-else
            ref="redisEditorRef"
            v-model="form.redis_command"
            mode="redis"
            placeholder='例如：SET user:1 "Tom" EX 60 或 DEL user:1'
            :min-height="220"
            @run="runChange"
          />
          <div v-if="form.db_type === 'mongodb'" class="editor-hint">
            支持 MongoDB shell 风格变更语句（insertOne/updateOne/deleteOne/replaceOne）
          </div>
          <div v-else-if="form.db_type === 'redis'" class="editor-hint">
            支持原生命令，按空格分隔参数；带空格的参数请用引号包裹
          </div>
          <div v-else class="editor-hint danger-hint">
            ⚠ 变更操作不可逆，请确认语句安全后再执行
          </div>
        </div>

        <!-- 结果区 -->
        <div class="result-area">
          <div class="result-tabs">
            <div class="result-tab active">变更结果</div>
            <div class="result-spacer" />
            <el-button v-if="resultVisible" size="small" text @click="clearResult">清空</el-button>
          </div>
          <div class="result-body">
            <el-empty v-if="!resultVisible" description="点击执行变更按钮查看结果" :image-size="70" />
            <el-input v-else v-model="rawResult" type="textarea" :rows="12" readonly class="result-textarea" />
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  CircleClose,
  Coin,
  Connection,
  Document,
  Folder,
  Grid,
  Key,
  Refresh,
  Search,
  VideoPlay,
  View,
} from "@element-plus/icons-vue";

import SqlEditor from "../components/SqlEditor.vue";
import { listClusters } from "../api/modules/clusters";
import { listInstances } from "../api/modules/instances";
import {
  cancelDataAccessExecution,
  changeData,
  describeMongoCollection,
  listMongoCollections,
  listMongoDatabases,
  listMysqlDatabases,
  listMysqlObjects,
  listMysqlTableColumns,
} from "../api/modules/data_access";

const form = reactive({
  db_type: "mysql",
  business_line: "",
  environment: "",
  cluster_id: null,
  route_mode: "auto",
  instance_id: null,
  sql: "",
  mysql_db: "",
  mongo_db: "admin",
  mongo_command: "",
  redis_command: "",
});

const clusters = ref([]);
const instances = ref([]);
const running = ref(false);
const resultVisible = ref(false);
const rawResult = ref("");
const mongoDatabases = ref([]);
const mongoDatabasesLoading = ref(false);
const mysqlDatabases = ref([]);
const mysqlDatabasesLoading = ref(false);
const currentExecutionId = ref("");
const schemaKeyword = ref("");
const schemaTreeRef = ref(null);
const schemaTreeVersion = ref(0);
const sqlEditorRef = ref(null);
const mongoEditorRef = ref(null);
const redisEditorRef = ref(null);
const routeModeOptions = [
  { label: "自动", value: "auto" },
  { label: "手动", value: "manual" },
];

const schemaTreeData = ref([]);
const schemaObjects = ref({ tables: [], views: [], procedures: [], functions: [], triggers: [], events: [] });
const mongoSchemaObjects = ref({ collections: [], views: [] });
const tableColumnsCache = reactive({});
const mongoCollectionInfoCache = reactive({});

const schemaTreeProps = {
  children: "children",
  label: "label",
  isLeaf: "leaf",
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

const filteredInstances = computed(() => {
  if (!form.cluster_id) return [];
  return instances.value.filter((item) => Number(item.cluster_id) === Number(form.cluster_id));
});

const sqlSchema = computed(() => {
  const tables = (schemaObjects.value.tables || []).map((t) => ({
    name: t.name,
    row_count: t.row_count,
    columns: tableColumnsCache[t.name] || [],
  }));
  const views = (schemaObjects.value.views || []).map((v) => ({ name: v.name }));
  return { tables, views };
});

const mongoSchema = computed(() => {
  const collections = (mongoSchemaObjects.value.collections || []).map((c) => ({
    name: c.name,
    fields: (mongoCollectionInfoCache[c.name]?.sample_fields) || [],
  }));
  const views = (mongoSchemaObjects.value.views || []).map((v) => ({ name: v.name }));
  return { collections, views };
});
const schemaTreeKey = computed(() => [
  form.db_type,
  form.cluster_id || "",
  form.route_mode || "auto",
  form.instance_id || "",
  form.mysql_db || "",
  form.mongo_db || "",
  schemaTreeVersion.value,
].join(":"));

function clusterLabel(cluster) {
  return cluster.name || `集群-${cluster.id}`;
}

async function loadClusters() {
  const { data } = await listClusters(form.db_type, { action: "change" });
  clusters.value = data.data || [];
}

function instanceLabel(instance) {
  const address = `${instance.resolved_ip || instance.host_input || "-"}:${instance.port || "-"}`;
  return `${instance.name || `实例-${instance.id}`} (${address})`;
}

function currentRoutePayload() {
  if (form.db_type !== "mysql") return {};
  if (form.route_mode === "manual" && form.instance_id) {
    return { route_mode: "manual", instance_id: form.instance_id };
  }
  return { route_mode: "auto" };
}

async function loadInstances() {
  if (form.db_type !== "mysql") {
    instances.value = [];
    return;
  }
  const { data } = await listInstances(form.db_type);
  instances.value = data.data || [];
}

async function reloadOptions() {
  await loadClusters();
  await loadInstances();
  await loadMysqlDatabasesOptions(true);
  await loadMongoDatabasesOptions(true);
}

function onDbTypeChange() {
  form.business_line = "";
  form.environment = "";
  form.cluster_id = null;
  form.route_mode = "auto";
  form.instance_id = null;
  form.mysql_db = "";
  form.mongo_db = "";
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
  form.route_mode = "auto";
  form.instance_id = null;
  form.mysql_db = "";
  form.mongo_db = "";
  mysqlDatabases.value = [];
  mongoDatabases.value = [];
  resetSchema();
}

function onEnvironmentChange() {
  form.cluster_id = null;
  form.route_mode = "auto";
  form.instance_id = null;
  form.mysql_db = "";
  form.mongo_db = "";
  mysqlDatabases.value = [];
  mongoDatabases.value = [];
  resetSchema();
}

async function onClusterChange() {
  form.route_mode = "auto";
  form.instance_id = null;
  form.mysql_db = "";
  form.mongo_db = "";
  resetSchema();
  await loadMysqlDatabasesOptions();
  await loadMongoDatabasesOptions();
  if (form.db_type === "mysql" && form.mysql_db) {
    await loadMysqlSchema();
  } else if (form.db_type === "mongodb" && form.mongo_db) {
    await loadMongoSchema();
  }
}

async function onRouteModeChange() {
  if (form.route_mode !== "manual") {
    form.instance_id = null;
  } else if (!form.instance_id) {
    form.mysql_db = "";
    mysqlDatabases.value = [];
    resetSchema();
    return;
  }
  resetSchema();
  await loadMysqlDatabasesOptions();
  if (form.db_type === "mysql" && form.mysql_db) {
    await loadMysqlSchema();
  }
}

async function onRouteInstanceChange() {
  resetSchema();
  await loadMysqlDatabasesOptions();
  if (form.db_type === "mysql" && form.mysql_db) {
    await loadMysqlSchema();
  }
}

async function onMysqlDatabaseChange() {
  await loadMysqlSchema();
}

async function onMongoDatabaseChange() {
  await loadMongoSchema();
}

function resetSchema() {
  schemaTreeVersion.value += 1;
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
    const { data } = await listMysqlDatabases(form.cluster_id, currentRoutePayload());
    const list = data?.data?.databases || [];
    mysqlDatabases.value = list;
    if (form.mysql_db && !list.includes(form.mysql_db)) {
      form.mysql_db = "";
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
    form.mongo_db = "";
    return;
  }
  mongoDatabasesLoading.value = true;
  try {
    const { data } = await listMongoDatabases(form.cluster_id);
    const list = data?.data?.databases || [];
    mongoDatabases.value = list;
    if (form.mongo_db && !list.includes(form.mongo_db)) {
      form.mongo_db = "";
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
    const { data } = await listMysqlObjects(form.cluster_id, form.mysql_db, currentRoutePayload());
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
    key: `view:${v.name}`, label: v.name, kind: "view", raw: v, leaf: true,
  }));
  const procGroup = mkGroup("Procedures", "procedures", objects.procedures, (p) => ({
    key: `procedure:${p.name}`, label: p.name, kind: "procedure", raw: p, leaf: true,
  }));
  const funcGroup = mkGroup("Functions", "functions", objects.functions, (f) => ({
    key: `function:${f.name}`, label: f.name, kind: "function", raw: f, leaf: true,
  }));
  const trigGroup = mkGroup("Triggers", "triggers", objects.triggers, (t) => ({
    key: `trigger:${t.name}`, label: t.name, kind: "trigger", raw: t, leaf: true,
  }));
  const evtGroup = mkGroup("Events", "events", objects.events, (e) => ({
    key: `event:${e.name}`, label: e.name, kind: "event", raw: e, leaf: true,
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
    key: `collection:${c.name}`, label: c.name, kind: "collection", raw: c, tooltip: c.name, leaf: false,
  }));
  const viewGroup = mkGroup("Views", "mongo-views", views, (v) => ({
    key: `mongo-view:${v.name}`, label: v.name, kind: "mongo-view", raw: v, leaf: true,
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
      const res = await listMysqlTableColumns(form.cluster_id, form.mysql_db, data.label, currentRoutePayload());
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
        label: f.name, kind: "field", raw: f,
        suffix: f.type || "", tooltip: `${f.name} : ${f.type || ""}`, leaf: true,
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
        label: idx.name, kind: "index", raw: idx,
        suffix: idx.unique ? "unique" : "",
        tooltip: (idx.key || []).map((it) => `${it[0]}:${it[1]}`).join(", "),
        leaf: true,
      })),
    });
  }
  if (!nodes.length) {
    nodes.push({ key: `mongo-empty:${collectionName}`, label: "暂无字段样本", kind: "info", leaf: true });
  }
  return nodes;
}

function columnToTreeNode(tableName, col) {
  const typeHint = col.column_type || col.data_type || "";
  return {
    key: `column:${tableName}.${col.name}`,
    label: col.name, kind: "column", raw: col,
    suffix: typeHint,
    tooltip: `${col.name} ${typeHint}${col.comment ? ` · ${col.comment}` : ""}`,
    leaf: true,
  };
}

function onSchemaNodeClick(data) {
  if (!data) return;
  if (data.kind === "table" || data.kind === "view" || data.kind === "column") {
    sqlEditorRef.value?.insertText(`\`${data.label}\``);
  } else if (data.kind === "collection" || data.kind === "mongo-view") {
    const snippet = `db.${data.label}.updateOne({}, {$set: {}})`;
    if (mongoEditorRef.value?.insertText) {
      mongoEditorRef.value.insertText(snippet);
    } else {
      form.mongo_command = snippet;
    }
  } else if (data.kind === "field" && form.db_type === "mongodb") {
    const snippet = `"${data.label}": `;
    mongoEditorRef.value?.insertText?.(snippet);
  }
}

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

function clearResult() {
  rawResult.value = "";
  resultVisible.value = false;
}

function buildExecutionId() {
  if (window.crypto && typeof window.crypto.randomUUID === "function") {
    return window.crypto.randomUUID().replace(/-/g, "");
  }
  return `${Date.now()}${Math.random().toString(16).slice(2)}`;
}

async function cancelRunningChange() {
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

async function runChange() {
  if (!form.cluster_id) {
    ElMessage.warning("请选择项目、环境和集群");
    return;
  }
  if (form.db_type === "mysql") {
    if (form.route_mode === "manual" && !form.instance_id) {
      ElMessage.warning("请选择变更实例");
      return;
    }
    if (!form.sql.trim()) { ElMessage.warning("请填写 SQL"); return; }
    if (!`${form.mysql_db || ""}`.trim()) { ElMessage.warning("请选择或输入 MySQL 数据库"); return; }
  }
  if (form.db_type === "mongodb" && !form.mongo_command.trim()) {
    ElMessage.warning("请填写 Mongo 命令");
    return;
  }
  if (form.db_type === "redis" && !form.redis_command.trim()) {
    ElMessage.warning("请填写 Redis 命令");
    return;
  }

  try {
    await ElMessageBox.confirm("确认要执行变更吗？请确认语句安全。", "高风险操作", {
      type: "warning",
      confirmButtonText: "确认执行",
      cancelButtonText: "取消",
    });
  } catch {
    return;
  }

  running.value = true;
  currentExecutionId.value = buildExecutionId();
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
      route_mode: form.db_type === "mysql" ? form.route_mode : undefined,
      instance_id: form.db_type === "mysql" && form.route_mode === "manual" ? form.instance_id : undefined,
      sql: form.db_type === "mysql" ? form.sql : undefined,
      database: form.db_type === "mysql" ? `${form.mysql_db || ""}`.trim() : undefined,
      mongo_command: form.db_type === "mongodb" ? form.mongo_command : undefined,
      mongo_database: form.db_type === "mongodb" ? `${form.mongo_db || ""}`.trim() : undefined,
      query: form.db_type === "redis" ? redisQuery : undefined,
      execution_id: currentExecutionId.value,
    };
    const { data } = await changeData(payload);
    rawResult.value = JSON.stringify(data?.data?.result || {}, null, 2);
    resultVisible.value = true;
    ElMessage.success("执行成功");
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "执行失败");
  } finally {
    running.value = false;
    currentExecutionId.value = "";
  }
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

.topbar-left { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.topbar-right { display: flex; align-items: center; gap: 8px; }

.webql-body { flex: 1; min-height: 0; display: flex; gap: 10px; }

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

.schema-header { padding: 10px 10px 8px; border-bottom: 1px solid #eef2f7; }
.db-select { width: 100%; }
.schema-placeholder { color: #94a3b8; font-size: 13px; }
.schema-search { padding: 8px 10px; border-bottom: 1px solid #eef2f7; }
.schema-tree { flex: 1; overflow: auto; padding: 6px 4px; }
.schema-tip { padding: 20px 12px; color: #94a3b8; font-size: 13px; text-align: center; }

.tree-node { display: inline-flex; align-items: center; gap: 4px; width: 100%; }
.tree-icon { font-size: 14px; color: #64748b; }
.tree-icon-table { color: #dc2626; }
.tree-icon-view { color: #9333ea; }
.tree-icon-column { color: #0ea5e9; }
.tree-label { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tree-suffix { color: #94a3b8; font-size: 12px; margin-left: 6px; }

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
  background: #fef2f2;
}

.toolbar-left { display: flex; align-items: center; gap: 10px; }
.change-tag { font-weight: 600; }
.current-db { display: inline-flex; align-items: center; gap: 6px; color: #334155; font-size: 13px; font-weight: 500; }
.toolbar-right { display: flex; align-items: center; gap: 8px; }
.shortcut-hint {
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.22);
  font-size: 11px;
  font-weight: 400;
}

.editor-area { padding: 10px 14px 6px; }
.editor-hint { margin-top: 6px; color: #94a3b8; font-size: 12px; }
.editor-hint.danger-hint { color: #dc2626; }

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
  border-radius: 6px;
}
.result-tab.active { color: #b91c1c; background: #fee2e2; font-weight: 500; }
.result-spacer { flex: 1; }

.result-body { flex: 1; min-height: 0; overflow: auto; padding: 10px 14px; }
.result-textarea :deep(.el-textarea__inner) {
  font-family: Consolas, "Courier New", monospace;
  font-size: 13px;
  background: #f8fafc;
}
</style>
