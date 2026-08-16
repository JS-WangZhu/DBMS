<template>
  <div class="page data-copy-page">
    <div class="page-header">
      <div>
        <div class="page-title">数据复制任务管理</div>
        <div class="page-subtitle">通过 Canal 或 MongoShake 捕获数据库变更并推送至 Kafka</div>
      </div>
      <div class="header-actions">
        <el-button @click="loadData">刷新</el-button>
        <el-button type="primary" @click="openCreate">创建任务</el-button>
      </div>
    </div>

    <el-alert
      title="当前为前端草稿模式：任务可创建和维护，但不会真实调用下游接口。"
      type="info"
      :closable="false"
      show-icon
      class="draft-alert"
    />

    <div class="summary-grid">
      <div class="summary-card"><span>任务总数</span><strong>{{ tasks.length }}</strong><small>MySQL 与 MongoDB</small></div>
      <div class="summary-card"><span>MySQL / Canal</span><strong>{{ mysqlCount }}</strong><small>Binlog 变更捕获</small></div>
      <div class="summary-card"><span>MongoDB / MongoShake</span><strong>{{ mongoCount }}</strong><small>Oplog / Change Stream</small></div>
      <div class="summary-card"><span>配置待完善</span><strong class="warning-number">{{ incompleteCount }}</strong><small>缺少关联配置</small></div>
    </div>

    <el-card shadow="never">
      <div class="toolbar">
        <el-input v-model="filters.keyword" clearable placeholder="搜索任务名称 / Topic" style="width:240px" />
        <el-select v-model="filters.db_type" clearable placeholder="数据库类型" style="width:150px">
          <el-option label="MySQL" value="mysql" /><el-option label="MongoDB" value="mongodb" />
        </el-select>
        <el-select v-model="filters.status" clearable placeholder="任务状态" style="width:150px">
          <el-option label="草稿" value="draft" /><el-option label="已停止" value="stopped" />
        </el-select>
        <span class="toolbar-spacer" />
        <el-button @click="resetFilters">重置</el-button>
      </div>

      <el-table :data="filteredTasks" stripe empty-text="暂无数据复制任务，请先创建任务">
        <el-table-column prop="name" label="任务名称" min-width="180" show-overflow-tooltip />
        <el-table-column label="复制链路" min-width="215">
          <template #default="{ row }">
            <div class="pipeline-cell">
              <el-tag :type="row.db_type === 'mysql' ? 'primary' : 'success'" effect="plain">{{ dbLabel(row.db_type) }}</el-tag>
              <span>→</span><span>{{ connectorLabel(row.db_type) }}</span><span>→</span><strong>Kafka</strong>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="源集群" min-width="150"><template #default="{ row }">{{ row.source_cluster_name || `集群 #${row.source_cluster_id}` }}</template></el-table-column>
        <el-table-column prop="topic" label="Kafka Topic" min-width="180" show-overflow-tooltip />
        <el-table-column label="复制范围" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ scopeText(row) }}</template>
        </el-table-column>
        <el-table-column label="配置状态" width="115">
          <template #default="{ row }"><el-tag :type="isComplete(row) ? 'success' : 'warning'">{{ isComplete(row) ? "完整" : "待完善" }}</el-tag></template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }"><el-tag :type="row.status === 'stopped' ? 'info' : ''">{{ row.status === "stopped" ? "已停止" : "草稿" }}</el-tag></template>
        </el-table-column>
        <el-table-column label="操作" width="255" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="primary" @click="duplicateTask(row)">复制</el-button>
            <el-tooltip content="后端接口接入后开放真实下发" placement="top">
              <el-button link type="success" @click="previewDispatch(row)">下发</el-button>
            </el-tooltip>
            <el-button link type="danger" @click="removeTask(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑复制任务' : '创建复制任务'" width="900px" top="4vh" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="125px">
        <div class="form-section-title"><span>1</span>基础信息</div>
        <el-row :gutter="18">
          <el-col :span="12"><el-form-item label="任务名称" prop="name"><el-input v-model="form.name" placeholder="例如：订单变更同步 Kafka" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="数据库类型" prop="db_type"><el-select v-model="form.db_type" style="width:100%" @change="onDbTypeChange"><el-option label="MySQL" value="mysql" /><el-option label="MongoDB" value="mongodb" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="复制组件"><el-input :model-value="connectorLabel(form.db_type)" disabled><template #prepend>{{ form.db_type === 'mysql' ? 'Binlog' : 'Oplog' }}</template></el-input></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="下游接口" prop="endpoint_id"><el-select v-model="form.endpoint_id" style="width:100%" placeholder="请选择执行接口"><el-option v-for="item in enabledEndpoints" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item></el-col>
        </el-row>

        <div class="form-section-title"><span>2</span>数据源与账号</div>
        <el-row :gutter="18">
          <el-col :span="12"><el-form-item label="源集群" prop="source_cluster_id"><el-select v-model="form.source_cluster_id" filterable style="width:100%" placeholder="请选择源数据库集群"><el-option v-for="item in clusters" :key="item.id" :label="clusterLabel(item)" :value="item.id" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="复制账号" prop="account_id"><el-select v-model="form.account_id" style="width:100%" placeholder="请选择托管账号"><el-option v-for="item in availableAccounts" :key="item.id" :label="`${item.name} (${item.username})`" :value="item.id" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="数据库" prop="database"><el-input v-model="form.database" :placeholder="form.db_type === 'mysql' ? '例如：order_db' : '例如：order'" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item :label="form.db_type === 'mysql' ? '数据表' : '集合'"><el-input v-model="form.objects" placeholder="多个使用英文逗号；* 表示全部" /></el-form-item></el-col>
        </el-row>

        <div class="form-section-title"><span>3</span>Kafka 目标</div>
        <el-row :gutter="18">
          <el-col :span="12"><el-form-item label="Kafka 配置" prop="kafka_id"><el-select v-model="form.kafka_id" style="width:100%" placeholder="请选择 Kafka 集群"><el-option v-for="item in enabledKafkaConfigs" :key="item.id" :label="item.name" :value="item.id" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="目标 Topic" prop="topic"><el-input v-model="form.topic" placeholder="例如：db_cdc_order" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="消息格式"><el-select v-model="form.message_format" style="width:100%"><el-option label="JSON" value="json" /><el-option label="Canal JSON" value="canal_json" /><el-option label="Debezium JSON" value="debezium_json" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="分区键"><el-select v-model="form.partition_key" style="width:100%"><el-option label="主键" value="primary_key" /><el-option label="数据库 + 表" value="table" /><el-option label="不指定" value="none" /></el-select></el-form-item></el-col>
        </el-row>

        <div class="form-section-title"><span>4</span>同步策略</div>
        <el-row :gutter="18">
          <el-col :span="12"><el-form-item label="同步模式"><el-select v-model="form.sync_mode" style="width:100%"><el-option label="仅增量" value="incremental" /><el-option label="全量 + 增量" value="full_incremental" /></el-select></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="起始位点"><el-select v-model="form.start_position" style="width:100%"><el-option label="从最新位点开始" value="latest" /><el-option label="指定时间" value="timestamp" /><el-option v-if="form.db_type === 'mysql'" label="指定 Binlog 位点" value="binlog" /></el-select></el-form-item></el-col>
          <el-col v-if="form.start_position === 'timestamp'" :span="12"><el-form-item label="起始时间"><el-date-picker v-model="form.start_time" type="datetime" value-format="YYYY-MM-DD HH:mm:ss" style="width:100%" /></el-form-item></el-col>
          <template v-if="form.start_position === 'binlog' && form.db_type === 'mysql'">
            <el-col :span="12"><el-form-item label="Binlog 文件"><el-input v-model="form.binlog_file" placeholder="mysql-bin.000001" /></el-form-item></el-col>
            <el-col :span="12"><el-form-item label="Binlog 位置"><el-input-number v-model="form.binlog_position" :min="4" style="width:100%" /></el-form-item></el-col>
          </template>
          <el-col :span="12"><el-form-item label="DDL 事件"><el-switch v-model="form.include_ddl" active-text="推送" inactive-text="忽略" /></el-form-item></el-col>
          <el-col :span="12"><el-form-item label="自动启动"><el-switch v-model="form.auto_start" active-text="下发后启动" inactive-text="手动启动" /></el-form-item></el-col>
          <el-col :span="24"><el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="2" placeholder="填写用途、负责人或变更说明" /></el-form-item></el-col>
        </el-row>
      </el-form>
      <template #footer><el-button @click="dialogVisible=false">取消</el-button><el-button type="primary" @click="saveTask">保存草稿</el-button></template>
    </el-dialog>

    <el-dialog v-model="dispatchVisible" title="下发预览" width="650px">
      <el-descriptions v-if="dispatchTask" :column="1" border>
        <el-descriptions-item label="任务">{{ dispatchTask.name }}</el-descriptions-item>
        <el-descriptions-item label="执行组件">{{ connectorLabel(dispatchTask.db_type) }}</el-descriptions-item>
        <el-descriptions-item label="下游接口">{{ configName(endpoints, dispatchTask.endpoint_id) }}</el-descriptions-item>
        <el-descriptions-item label="消息目标">{{ configName(kafkaConfigs, dispatchTask.kafka_id) }} / {{ dispatchTask.topic }}</el-descriptions-item>
      </el-descriptions>
      <el-alert title="后端接口尚未接入，本次不会发送请求。" type="warning" :closable="false" show-icon class="dispatch-alert" />
      <template #footer><el-button type="primary" @click="dispatchVisible=false">我知道了</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { listClusters } from "../api/modules/clusters";
import { DATA_COPY_STORAGE_KEYS, nextDraftId, readDraftList, writeDraftList } from "../utils/dataCopyDraftStore";

const tasks = ref([]); const kafkaConfigs = ref([]); const accounts = ref([]); const endpoints = ref([]); const clusters = ref([]);
const dialogVisible = ref(false); const dispatchVisible = ref(false); const dispatchTask = ref(null); const editingId = ref(null); const formRef = ref(null);
const filters = reactive({ keyword: "", db_type: "", status: "" });
const form = reactive(defaultForm());
const rules = { name: [{ required: true, message: "请输入任务名称", trigger: "blur" }], db_type: [{ required: true, message: "请选择数据库类型", trigger: "change" }], endpoint_id: [{ required: true, message: "请选择下游接口", trigger: "change" }], source_cluster_id: [{ required: true, message: "请选择源集群", trigger: "change" }], account_id: [{ required: true, message: "请选择复制账号", trigger: "change" }], database: [{ required: true, message: "请输入数据库", trigger: "blur" }], kafka_id: [{ required: true, message: "请选择 Kafka 配置", trigger: "change" }], topic: [{ required: true, message: "请输入目标 Topic", trigger: "blur" }] };

const enabledKafkaConfigs = computed(() => kafkaConfigs.value.filter((item) => item.enabled));
const enabledEndpoints = computed(() => endpoints.value.filter((item) => item.enabled));
const availableAccounts = computed(() => accounts.value.filter((item) => item.enabled && item.db_type === form.db_type));
const mysqlCount = computed(() => tasks.value.filter((item) => item.db_type === "mysql").length);
const mongoCount = computed(() => tasks.value.filter((item) => item.db_type === "mongodb").length);
const incompleteCount = computed(() => tasks.value.filter((item) => !isComplete(item)).length);
const filteredTasks = computed(() => tasks.value.filter((item) => { const keyword = filters.keyword.trim().toLowerCase(); return (!keyword || `${item.name} ${item.topic}`.toLowerCase().includes(keyword)) && (!filters.db_type || item.db_type === filters.db_type) && (!filters.status || item.status === filters.status); }));

function defaultForm() { return { name: "", db_type: "mysql", endpoint_id: null, source_cluster_id: null, account_id: null, database: "", objects: "*", kafka_id: null, topic: "", message_format: "json", partition_key: "primary_key", sync_mode: "incremental", start_position: "latest", start_time: "", binlog_file: "", binlog_position: 4, include_ddl: false, auto_start: false, remark: "", status: "draft" }; }
function loadData() { tasks.value = readDraftList(DATA_COPY_STORAGE_KEYS.tasks); kafkaConfigs.value = readDraftList(DATA_COPY_STORAGE_KEYS.kafka); accounts.value = readDraftList(DATA_COPY_STORAGE_KEYS.accounts); endpoints.value = readDraftList(DATA_COPY_STORAGE_KEYS.endpoints); }
async function loadClusters() { clusters.value = []; try { const { data } = await listClusters(form.db_type); clusters.value = data?.data || []; } catch (error) { ElMessage.warning(error.response?.data?.message || "源集群加载失败，可稍后重试"); } }
function resetForm(data = {}) { Object.assign(form, defaultForm(), JSON.parse(JSON.stringify(data))); }
async function openCreate() { loadData(); editingId.value = null; resetForm(); dialogVisible.value = true; await loadClusters(); }
async function openEdit(row) { loadData(); editingId.value = row.id; resetForm(row); dialogVisible.value = true; await loadClusters(); }
async function onDbTypeChange() { form.source_cluster_id = null; form.account_id = null; form.start_position = "latest"; await loadClusters(); }
async function saveTask() { await formRef.value?.validate(); const cluster = clusters.value.find((item) => item.id === form.source_cluster_id); const item = { ...form, id: editingId.value || nextDraftId(tasks.value), source_cluster_name: cluster?.name || "", connector: form.db_type === "mysql" ? "canal" : "mongoshake", updated_at: new Date().toISOString() }; const index = tasks.value.findIndex((row) => row.id === item.id); if (index >= 0) tasks.value.splice(index, 1, item); else tasks.value.unshift(item); writeDraftList(DATA_COPY_STORAGE_KEYS.tasks, tasks.value); dialogVisible.value = false; ElMessage.success("任务草稿已保存"); }
function duplicateTask(row) { const item = { ...JSON.parse(JSON.stringify(row)), id: nextDraftId(tasks.value), name: `${row.name}-副本`, status: "draft", updated_at: new Date().toISOString() }; tasks.value.unshift(item); writeDraftList(DATA_COPY_STORAGE_KEYS.tasks, tasks.value); ElMessage.success("已复制为新草稿"); }
async function removeTask(row) { await ElMessageBox.confirm(`确认删除任务“${row.name}”？`, "删除确认", { type: "warning" }); tasks.value = tasks.value.filter((item) => item.id !== row.id); writeDraftList(DATA_COPY_STORAGE_KEYS.tasks, tasks.value); ElMessage.success("已删除"); }
function previewDispatch(row) { dispatchTask.value = row; dispatchVisible.value = true; }
function resetFilters() { Object.assign(filters, { keyword: "", db_type: "", status: "" }); }
function dbLabel(type) { return type === "mysql" ? "MySQL" : "MongoDB"; }
function connectorLabel(type) { return type === "mysql" ? "Canal" : "MongoShake"; }
function clusterLabel(item) { return `${item.name || `集群-${item.id}`} · ${item.environment || "未标环境"}`; }
function configName(items, id) { return items.find((item) => item.id === id)?.name || "未配置"; }
function scopeText(row) { return `${row.database || "-"}.${row.objects || "*"}`; }
function isComplete(row) { return Boolean(row.endpoint_id && row.source_cluster_id && row.account_id && row.kafka_id && row.topic && row.database); }
onMounted(loadData);
</script>

<style scoped>
.data-copy-page { display: flex; flex-direction: column; gap: 16px; }.draft-alert { margin-top: -4px; }.summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }.summary-card { min-height: 112px; padding: 18px 20px; border: 1px solid var(--border-soft); background: var(--bg-secondary); display: grid; grid-template-columns: 1fr auto; align-items: center; box-shadow: var(--shadow-sm); }.summary-card span { color: var(--text-regular); font-weight: 600; }.summary-card strong { color: var(--brand); font-size: 30px; }.summary-card .warning-number { color: var(--warning); }.summary-card small { grid-column: 1 / -1; color: var(--text-soft); }.header-actions,.toolbar { display: flex; align-items: center; gap: 10px; }.toolbar { margin-bottom: 16px; }.toolbar-spacer { flex: 1; }.pipeline-cell { display: flex; align-items: center; gap: 7px; color: var(--text-soft); }.pipeline-cell strong { color: var(--text-primary); }.form-section-title { display: flex; align-items: center; gap: 9px; margin: 6px 0 18px; padding-bottom: 10px; border-bottom: 1px solid var(--border-soft); color: var(--text-primary); font-weight: 650; }.form-section-title:not(:first-child) { margin-top: 14px; }.form-section-title span { width: 24px; height: 24px; display: inline-grid; place-items: center; background: var(--brand-soft); color: var(--brand); }.dispatch-alert { margin-top: 16px; }
@media (max-width: 1100px) { .summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
