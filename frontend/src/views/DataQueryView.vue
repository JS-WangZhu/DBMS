<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>数据查询</span>
          <div class="header-actions">
            <el-button @click="reloadOptions">刷新</el-button>
          </div>
        </div>
      </template>

      <el-form :model="form" label-width="120px">
        <el-form-item label="数据库类型">
          <el-select v-model="form.db_type" style="width: 240px" @change="onDbTypeChange">
            <el-option label="MySQL" value="mysql" />
            <el-option label="MongoDB" value="mongodb" />
            <el-option label="Redis" value="redis" />
          </el-select>
        </el-form-item>
        <el-form-item label="项目">
          <el-select v-model="form.business_line" clearable style="width: 260px" @change="onBusinessLineChange">
            <el-option v-for="line in businessLines" :key="line" :label="line" :value="line" />
          </el-select>
        </el-form-item>
        <el-form-item label="环境">
          <el-select v-model="form.environment" clearable style="width: 260px" @change="onEnvironmentChange">
            <el-option v-for="env in environments" :key="env" :label="env" :value="env" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.db_type === 'mysql'" label="集群/数据库">
          <div class="inline-query-options">
            <el-select v-model="form.cluster_id" clearable style="width: 360px" @change="onClusterChange">
              <el-option v-for="cluster in filteredClusters" :key="cluster.id" :label="clusterLabel(cluster)" :value="cluster.id" />
            </el-select>
            <el-select
              v-model="form.mysql_db"
              filterable
              allow-create
              default-first-option
              clearable
              style="width: 280px"
              :loading="mysqlDatabasesLoading"
              placeholder="请选择或输入数据库"
            >
              <el-option v-for="db in mysqlDatabases" :key="db" :label="db" :value="db" />
            </el-select>
          </div>
        </el-form-item>
        <el-form-item v-else label="集群">
          <el-select v-model="form.cluster_id" clearable style="width: 360px" @change="onClusterChange">
            <el-option v-for="cluster in filteredClusters" :key="cluster.id" :label="clusterLabel(cluster)" :value="cluster.id" />
          </el-select>
        </el-form-item>

        <el-form-item v-if="form.db_type === 'mysql'" label="SQL">
          <SqlEditor v-model="form.sql" placeholder="SELECT * FROM table LIMIT 100;" :min-height="280" />
        </el-form-item>

        <template v-else-if="form.db_type === 'mongodb'">
          <el-form-item label="数据库">
            <el-select
              v-model="form.mongo_db"
              filterable
              allow-create
              default-first-option
              clearable
              style="width: 360px"
              :loading="mongoDatabasesLoading"
              placeholder="请选择或输入数据库"
            >
              <el-option v-for="db in mongoDatabases" :key="db" :label="db" :value="db" />
            </el-select>
          </el-form-item>
          <el-form-item label="Mongo命令">
            <el-input v-model="form.mongo_command" type="textarea" :rows="6" placeholder='例如：db.test_collection.find({name:"Gemini"}).limit(10)' />
            <div class="input-hint">支持 MongoDB shell 风格的只读查询语句（find/findOne/aggregate/count）</div>
          </el-form-item>
        </template>

        <template v-else-if="form.db_type === 'redis'">
          <el-form-item label="Redis命令">
            <el-input v-model="form.redis_command" type="textarea" :rows="4" placeholder='例如：GET user:1 或 HGET user:1 name' />
            <div class="input-hint">直接输入基础命令，系统会自动解析参数</div>
          </el-form-item>
        </template>

        <el-form-item v-else label="查询JSON">
          <el-input v-model="form.query_json" type="textarea" :rows="6" placeholder='{"db":"test","collection":"users","op":"find","filter":{},"limit":50}' />
        </el-form-item>
      </el-form>

      <div class="action-row">
        <el-button type="primary" :loading="running" @click="runQuery">执行查询</el-button>
        <el-button v-if="running" type="warning" plain @click="cancelRunningQuery">取消执行</el-button>
      </div>
    </el-card>

    <el-card class="result-card" v-if="resultVisible">
      <template #header>
        <div class="header-row">
          <span>查询结果</span>
          <div class="header-actions">
            <span class="result-hint">最多返回 1000 条记录</span>
            <el-button @click="clearResult">清空</el-button>
          </div>
        </div>
      </template>
      <div v-if="connectionInfo" class="connection-info">
        <span>集群：{{ connectionInfo.cluster?.name || "-" }}</span>
        <span>实例：{{ connectionInfo.instance?.name || "-" }}</span>
        <span>地址：{{ (connectionInfo.instance?.resolved_ip || connectionInfo.instance?.host_input || "-") }}:{{ connectionInfo.instance?.port || "-" }}</span>
        <span>数据库：{{ connectionInfo.database || "-" }}</span>
      </div>

      <el-table v-if="tableColumns.length" :data="pagedTableRows" stripe size="small">
        <el-table-column v-for="col in tableColumns" :key="col" :prop="col" :label="col" min-width="140" show-overflow-tooltip />
      </el-table>
      <div v-if="tableColumns.length" class="pagination-row">
        <span class="result-count">共 {{ tableRows.length }} 条</span>
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100, 200]"
          :total="tableRows.length"
          layout="total, sizes, prev, pager, next, jumper"
          background
        />
      </div>
      <el-tree
        v-else-if="isMongoResult"
        :data="mongoTreeData"
        node-key="id"
        :props="mongoTreeProps"
        default-expand-all
        class="json-tree"
      />
      <el-input v-else v-model="rawResult" type="textarea" :rows="8" readonly />
    </el-card>

  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

import SqlEditor from "../components/SqlEditor.vue";
import { listClusters } from "../api/modules/clusters";
import { cancelDataAccessExecution, listMongoDatabases, listMysqlDatabases, queryData } from "../api/modules/data_access";

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
  query_json: "",
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
  const end = start + pageSize.value;
  return tableRows.value.slice(start, end);
});

const isMongoResult = computed(() => form.db_type === "mongodb");

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
  reloadOptions();
}

function onBusinessLineChange() {
  form.environment = "";
  form.cluster_id = null;
  form.mysql_db = "";
  mysqlDatabases.value = [];
  form.mongo_db = "admin";
  mongoDatabases.value = [];
}

function onEnvironmentChange() {
  form.cluster_id = null;
  form.mysql_db = "";
  mysqlDatabases.value = [];
  form.mongo_db = "admin";
  mongoDatabases.value = [];
}

async function onClusterChange() {
  await loadMysqlDatabasesOptions();
  await loadMongoDatabasesOptions();
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
    if (list.length) {
      if (!list.includes(form.mongo_db)) {
        form.mongo_db = list[0];
      }
    } else if (!form.mongo_db) {
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

function tokenizeCommandLine(raw) {
  const source = `${raw || ""}`.trim();
  if (!source) return [];
  const parts = source.match(/"[^"\\]*(?:\\.[^"\\]*)*"|'[^'\\]*(?:\\.[^'\\]*)*'|\S+/g) || [];
  return parts.map((part) => {
    if (
      (part.startsWith('"') && part.endsWith('"')) ||
      (part.startsWith("'") && part.endsWith("'"))
    ) {
      return part.slice(1, -1).replace(/\\"/g, '"').replace(/\\'/g, "'");
    }
    return part;
  });
}

function buildRedisCommandPayload() {
  const tokens = tokenizeCommandLine(form.redis_command);
  if (!tokens.length) return null;
  return {
    command: tokens[0].toUpperCase(),
    args: tokens.slice(1),
  };
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
      children: entries.map(([childKey, childValue]) => buildJsonTreeNode(childKey, childValue, `${path}.${childKey}`)),
    };
  }
  return {
    id: path,
    label: `${key}: ${stringifyLeafValue(value)}`,
  };
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
  if (form.db_type === "mysql" && !form.sql.trim()) {
    ElMessage.warning("请填写 SQL");
    return;
  }
  if (form.db_type === "mysql" && !`${form.mysql_db || ""}`.trim()) {
    ElMessage.warning("请选择或输入 MySQL 数据库");
    return;
  }
  if (form.db_type === "mongodb" && !form.mongo_command.trim()) {
    ElMessage.warning("请填写 Mongo 命令");
    return;
  }
  if (form.db_type === "redis" && !form.redis_command.trim()) {
    ElMessage.warning("请填写 Redis 命令");
    return;
  }
  if (!["mysql", "mongodb", "redis"].includes(form.db_type) && !form.query_json.trim()) {
    ElMessage.warning("请填写查询 JSON");
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
      sql: form.db_type === "mysql" ? form.sql : undefined,
      database: form.db_type === "mysql" ? `${form.mysql_db || ""}`.trim() : undefined,
      mongo_command: form.db_type === "mongodb" ? form.mongo_command : undefined,
      mongo_database: form.db_type === "mongodb" ? `${form.mongo_db || ""}`.trim() : undefined,
      query: form.db_type === "mongodb" ? undefined : form.db_type === "redis" ? redisQuery : form.db_type === "mysql" ? undefined : form.query_json,
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
    if (result.truncated) {
      ElMessage.warning("查询结果已限制为最多 1000 条记录");
    }
    resultVisible.value = true;
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "查询失败");
  } finally {
    running.value = false;
    currentExecutionId.value = "";
  }
}

onMounted(async () => {
  await reloadOptions();
});
</script>

<style scoped>
.page {
  padding: 20px;
}

.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.action-row {
  margin-top: 10px;
}

.result-card {
  margin-top: 16px;
}

.result-hint {
  color: #64748b;
  font-size: 13px;
}

.pagination-row {
  margin-top: 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.result-count {
  color: #64748b;
  font-size: 13px;
}

.input-hint {
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.4;
}

.inline-query-options {
  display: flex;
  align-items: center;
  gap: 12px;
}

.connection-info {
  margin-bottom: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 12px 16px;
  color: #475569;
  font-size: 13px;
}

.json-tree {
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 8px 10px;
  background: #ffffff;
  max-height: 560px;
  overflow: auto;
}

.json-tree :deep(.el-tree-node__content) {
  font-family: "Consolas", "Courier New", monospace;
  font-size: 13px;
}
</style>
