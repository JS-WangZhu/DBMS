<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>调度管理</span>
          <div class="header-actions">
            <el-button :loading="loading" @click="loadData">刷新</el-button>
            <el-button type="primary" @click="openCreate">新增任务</el-button>
          </div>
        </div>
      </template>

      <div class="toolbar">
        <el-select v-model="filters.task_type" clearable placeholder="任务类型" style="width: 160px" @change="loadData">
          <el-option label="Shell脚本" value="shell" />
          <el-option label="Python脚本" value="python" />
          <el-option label="HTTP请求" value="http" />
          <el-option label="SQL请求" value="sql" />
        </el-select>
      </div>

      <el-table :data="rows" stripe v-loading="loading">
        <el-table-column prop="name" label="任务名称" min-width="180" show-overflow-tooltip />
        <el-table-column label="类型" width="110">
          <template #default="{ row }">{{ taskTypeText(row.task_type) }}</template>
        </el-table-column>
        <el-table-column prop="cron_expr" label="调度" width="140" />
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? "启用" : "停用" }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="最近结果" width="110">
          <template #default="{ row }">
            <el-tag v-if="row.last_status" :type="row.last_status === 'success' ? 'success' : 'danger'">
              {{ row.last_status === "success" ? "成功" : "失败" }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="最近执行" min-width="170">
          <template #default="{ row }">{{ formatDateTime(row.last_run_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="270" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="runNow(row)">执行</el-button>
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link :type="row.enabled ? 'warning' : 'success'" @click="toggleEnabled(row)">
              {{ row.enabled ? "停用" : "启用" }}
            </el-button>
            <el-button link type="danger" @click="removeTask(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑任务' : '新增任务'" width="860px" top="5vh">
      <el-form :model="form" label-width="120px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="任务名称">
              <el-input v-model="form.name" placeholder="请输入任务名称" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="任务类型">
              <el-select v-model="form.task_type" style="width: 100%" @change="onTaskTypeChange">
                <el-option label="Shell脚本" value="shell" />
                <el-option label="Python脚本" value="python" />
                <el-option label="HTTP请求" value="http" />
                <el-option label="SQL请求" value="sql" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="Cron表达式">
              <el-input v-model="form.cron_expr" placeholder="例如 0 2 * * *" />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="超时(秒)">
              <el-input-number v-model="form.timeout_seconds" :min="1" :max="86400" controls-position="right" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="启用">
              <el-switch v-model="form.enabled" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="描述">
              <el-input v-model="form.description" type="textarea" :rows="2" />
            </el-form-item>
          </el-col>
        </el-row>

        <template v-if="form.task_type === 'shell'">
          <el-form-item label="Shell脚本">
            <el-input v-model="form.content_json.script" type="textarea" :rows="10" placeholder="例如：echo hello" />
          </el-form-item>
        </template>
        <template v-else-if="form.task_type === 'python'">
          <el-form-item label="Python脚本">
            <el-input v-model="form.content_json.script" type="textarea" :rows="10" placeholder="例如：print('hello')" />
          </el-form-item>
        </template>
        <template v-else-if="form.task_type === 'http'">
          <el-row :gutter="16">
            <el-col :span="6">
              <el-form-item label="方法">
                <el-select v-model="form.content_json.method" style="width: 100%">
                  <el-option label="GET" value="GET" />
                  <el-option label="POST" value="POST" />
                  <el-option label="PUT" value="PUT" />
                  <el-option label="DELETE" value="DELETE" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="18">
              <el-form-item label="URL">
                <el-input v-model="form.content_json.url" placeholder="https://example.com/api" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item label="请求头JSON">
            <el-input v-model="httpHeadersText" type="textarea" :rows="4" placeholder='{"Authorization":"Bearer xxx"}' />
          </el-form-item>
          <el-form-item label="请求体">
            <el-input v-model="form.content_json.body" type="textarea" :rows="5" />
          </el-form-item>
        </template>
        <template v-else>
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="数据库类型">
                <el-select v-model="form.content_json.db_type" style="width: 100%" @change="loadSqlTargets">
                  <el-option label="MySQL" value="mysql" />
                  <el-option label="MongoDB" value="mongodb" />
                  <el-option label="Redis" value="redis" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="目标范围">
                <el-select v-model="form.content_json.target_mode" style="width: 100%" @change="loadSqlTargets">
                  <el-option label="集群自动路由" value="cluster" />
                  <el-option label="指定实例" value="instance" />
                  <el-option label="全部实例" value="all" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="SQL类型">
                <el-select v-model="form.content_json.sql_operation" style="width: 100%">
                  <el-option label="查询" value="query" />
                  <el-option label="变更" value="change" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col v-if="form.content_json.target_mode === 'cluster'" :span="12">
              <el-form-item label="集群">
                <el-select v-model="form.content_json.cluster_id" filterable style="width: 100%">
                  <el-option v-for="item in clusters" :key="item.id" :label="item.name" :value="item.id" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col v-if="form.content_json.target_mode === 'instance'" :span="12">
              <el-form-item label="实例">
                <el-select v-model="form.content_json.instance_id" filterable style="width: 100%">
                  <el-option v-for="item in instances" :key="item.id" :label="instanceLabel(item)" :value="item.id" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col v-if="form.content_json.db_type !== 'redis'" :span="12">
              <el-form-item label="数据库">
                <el-input v-model="form.content_json.database" placeholder="MySQL库名 / MongoDB库名" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-form-item :label="form.content_json.db_type === 'redis' ? 'Redis命令' : '请求内容'">
            <el-input v-model="form.content_json.sql" type="textarea" :rows="8" placeholder="MySQL SQL / Mongo 命令 / Redis 命令" />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveTask">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { listClusters } from "../api/modules/clusters";
import { listInstances } from "../api/modules/instances";
import {
  createTaskSchedule,
  deleteTaskSchedule,
  listTaskSchedules,
  runTaskSchedule,
  updateTaskSchedule,
} from "../api/modules/tasks";

const loading = ref(false);
const saving = ref(false);
const rows = ref([]);
const dialogVisible = ref(false);
const editingId = ref(null);
const clusters = ref([]);
const instances = ref([]);
const httpHeadersText = ref("{}");
const filters = reactive({ task_type: "" });
const form = reactive(defaultForm());

function defaultForm() {
  return {
    name: "",
    description: "",
    task_type: "shell",
    cron_expr: "0 * * * *",
    enabled: true,
    timeout_seconds: 300,
    content_json: { script: "" },
  };
}

function assignForm(data) {
  Object.assign(form, defaultForm(), data);
  form.content_json = { ...(data.content_json || defaultContent(form.task_type)) };
  httpHeadersText.value = JSON.stringify(form.content_json.headers || {}, null, 2);
}

function defaultContent(type) {
  if (type === "http") return { method: "GET", url: "", headers: {}, body: "" };
  if (type === "sql") return { db_type: "mysql", target_mode: "cluster", sql_operation: "query", route_mode: "auto", database: "", sql: "" };
  return { script: "" };
}

function taskTypeText(type) {
  return { shell: "Shell脚本", python: "Python脚本", http: "HTTP请求", sql: "SQL请求" }[type] || type;
}

function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function instanceLabel(item) {
  return `${item.name || `实例-${item.id}`} (${item.resolved_ip || item.host_input || "-"}:${item.port || "-"})`;
}

async function loadData() {
  loading.value = true;
  try {
    const params = {};
    if (filters.task_type) params.task_type = filters.task_type;
    const { data } = await listTaskSchedules(params);
    rows.value = data?.data || [];
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载任务失败");
  } finally {
    loading.value = false;
  }
}

async function loadSqlTargets() {
  if (form.task_type !== "sql") return;
  const dbType = form.content_json.db_type || "mysql";
  try {
    const [{ data: clusterResp }, { data: instanceResp }] = await Promise.all([
      listClusters(dbType),
      listInstances(dbType),
    ]);
    clusters.value = clusterResp?.data || [];
    instances.value = instanceResp?.data || [];
  } catch {
    clusters.value = [];
    instances.value = [];
  }
}

function openCreate() {
  editingId.value = null;
  assignForm(defaultForm());
  dialogVisible.value = true;
}

async function openEdit(row) {
  editingId.value = row.id;
  assignForm(row);
  dialogVisible.value = true;
  await loadSqlTargets();
}

function onTaskTypeChange(type) {
  form.content_json = defaultContent(type);
  httpHeadersText.value = "{}";
  loadSqlTargets();
}

function buildPayload() {
  if (!`${form.name || ""}`.trim()) {
    throw new Error("请填写任务名称");
  }
  if (!`${form.cron_expr || ""}`.trim()) {
    throw new Error("请填写 Cron 表达式");
  }
  const payload = {
    name: form.name,
    description: form.description,
    task_type: form.task_type,
    cron_expr: form.cron_expr,
    enabled: form.enabled,
    timeout_seconds: form.timeout_seconds,
    content_json: { ...form.content_json },
  };
  if (form.task_type === "http") {
    if (!`${payload.content_json.url || ""}`.trim()) {
      throw new Error("请填写 HTTP URL");
    }
    try {
      payload.content_json.headers = JSON.parse(httpHeadersText.value || "{}");
    } catch {
      throw new Error("请求头必须是合法 JSON");
    }
  }
  if ((form.task_type === "shell" || form.task_type === "python") && !`${payload.content_json.script || ""}`.trim()) {
    throw new Error("请填写脚本内容");
  }
  if (form.task_type === "sql" && !`${payload.content_json.sql || ""}`.trim()) {
    throw new Error("请填写 SQL/命令内容");
  }
  return payload;
}

async function saveTask() {
  saving.value = true;
  try {
    const payload = buildPayload();
    if (editingId.value) {
      await updateTaskSchedule(editingId.value, payload);
    } else {
      await createTaskSchedule(payload);
    }
    ElMessage.success("保存成功");
    dialogVisible.value = false;
    await loadData();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || error.message || "保存失败");
  } finally {
    saving.value = false;
  }
}

async function toggleEnabled(row) {
  await updateTaskSchedule(row.id, { enabled: !row.enabled });
  await loadData();
}

async function runNow(row) {
  await runTaskSchedule(row.id);
  ElMessage.success("任务已开始执行");
}

async function removeTask(row) {
  await ElMessageBox.confirm(`确认删除任务 ${row.name}？`, "删除确认", { type: "warning" });
  await deleteTaskSchedule(row.id);
  ElMessage.success("已删除");
  await loadData();
}

onMounted(loadData);
</script>

<style scoped>
.page { padding: 20px; }
.header-row { display: flex; justify-content: space-between; align-items: center; }
.header-actions { display: flex; gap: 10px; }
.toolbar { display: flex; gap: 10px; margin-bottom: 12px; }
</style>
