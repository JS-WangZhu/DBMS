<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>数据变更</span>
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
          <SqlEditor v-model="form.sql" placeholder="INSERT/UPDATE/DELETE/REPLACE" :min-height="280" />
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
            <el-input v-model="form.mongo_command" type="textarea" :rows="6" placeholder='例如：db.test_collection.updateOne({name:"Gemini"}, {$set: {name:"new"}})' />
            <div class="input-hint">支持 MongoDB shell 风格的变更语句</div>
          </el-form-item>
        </template>

        <el-form-item v-else-if="form.db_type === 'redis'" label="Redis命令">
          <el-input v-model="form.redis_command" type="textarea" :rows="4" placeholder='例如：SET user:1 "Tom" EX 60 或 DEL user:1' />
          <div class="input-hint">支持原生命令，按空格分隔参数，带空格参数可用引号包裹</div>
        </el-form-item>

        <el-form-item v-else label="变更JSON">
          <el-input v-model="form.query_json" type="textarea" :rows="6" placeholder='{"db":"test","collection":"users","op":"update_one","filter":{},"update":{}}' />
        </el-form-item>
      </el-form>

      <div class="action-row">
        <el-button type="danger" :loading="running" @click="runChange">执行变更</el-button>
        <el-button v-if="running" type="warning" plain @click="cancelRunningChange">取消执行</el-button>
      </div>
    </el-card>

    <el-card class="result-card" v-if="resultVisible">
      <template #header>
        <div class="header-row">
          <span>变更结果</span>
          <div class="header-actions">
            <el-button @click="clearResult">清空</el-button>
          </div>
        </div>
      </template>

      <el-input v-model="rawResult" type="textarea" :rows="8" readonly />
    </el-card>

  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import SqlEditor from "../components/SqlEditor.vue";
import { listClusters } from "../api/modules/clusters";
import { cancelDataAccessExecution, changeData, listMongoDatabases, listMysqlDatabases } from "../api/modules/data_access";

const form = reactive({
  db_type: "mysql",
  business_line: "",
  environment: "",
  cluster_id: null,
  mysql_db: "",
  mongo_db: "admin",
  mongo_command: "",
  redis_command: "",
  sql: "",
  query_json: "",
});

const clusters = ref([]);
const mysqlDatabases = ref([]);
const mysqlDatabasesLoading = ref(false);
const mongoDatabases = ref([]);
const mongoDatabasesLoading = ref(false);
const running = ref(false);
const resultVisible = ref(false);
const rawResult = ref("");
const currentExecutionId = ref("");

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

function clusterLabel(cluster) {
  return cluster.name || `集群-${cluster.id}`;
}

async function loadClusters() {
  const { data } = await listClusters(form.db_type, { action: "change" });
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
  form.mongo_db = "admin";
  mysqlDatabases.value = [];
  mongoDatabases.value = [];
}

function onEnvironmentChange() {
  form.cluster_id = null;
  form.mysql_db = "";
  form.mongo_db = "admin";
  mysqlDatabases.value = [];
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
    if (list.length && !list.includes(form.mongo_db)) {
      form.mongo_db = list[0];
    }
  } catch (error) {
    if (!silent) {
      ElMessage.warning(error.response?.data?.message || "加载 MongoDB 数据库列表失败");
    }
  } finally {
    mongoDatabasesLoading.value = false;
  }
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
    ElMessage.warning("请填写变更 JSON");
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
      sql: form.db_type === "mysql" ? form.sql : undefined,
      database: form.db_type === "mysql" ? `${form.mysql_db || ""}`.trim() : undefined,
      mongo_command: form.db_type === "mongodb" ? form.mongo_command : undefined,
      mongo_database: form.db_type === "mongodb" ? `${form.mongo_db || ""}`.trim() : undefined,
      query: form.db_type === "mongodb" ? undefined : form.db_type === "redis" ? redisQuery : form.db_type === "mysql" ? undefined : form.query_json,
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
  gap: 10px;
}

.action-row {
  margin-top: 10px;
}

.result-card {
  margin-top: 16px;
}

.inline-query-options {
  display: flex;
  align-items: center;
  gap: 12px;
}

.input-hint {
  margin-top: 6px;
  color: #64748b;
  font-size: 12px;
  line-height: 1.4;
}

</style>
