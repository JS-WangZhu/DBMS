<template>
  <div class="page data-copy-page">
    <div class="page-header">
      <div>
        <div class="page-title">数据复制配置中心</div>
        <div class="page-subtitle">统一维护 Kafka 集群、数据库复制账号和任务下发接口</div>
      </div>
      <el-tag type="warning" effect="plain">前端草稿模式</el-tag>
    </div>

    <el-alert
      title="当前仅完成前端交互，配置保存在本机浏览器；后端接入后将改为加密托管并通过下游接口下发。"
      type="info"
      :closable="false"
      show-icon
      class="draft-alert"
    />

    <div class="summary-grid">
      <div class="summary-card">
        <span>Kafka 集群</span><strong>{{ kafkaConfigs.length }}</strong><small>消息目标</small>
      </div>
      <div class="summary-card">
        <span>复制账号</span><strong>{{ accounts.length }}</strong><small>MySQL / MongoDB</small>
      </div>
      <div class="summary-card">
        <span>下游接口</span><strong>{{ endpoints.length }}</strong><small>任务执行入口</small>
      </div>
    </div>

    <el-card shadow="never">
      <el-tabs v-model="activeTab">
        <el-tab-pane label="Kafka 集群" name="kafka">
          <div class="section-toolbar">
            <div class="section-copy">
              <strong>Kafka 集群</strong><span>维护 Broker、认证方式和默认参数</span>
            </div>
            <el-button type="primary" @click="openCreate('kafka')">新增 Kafka 配置</el-button>
          </div>
          <el-table :data="kafkaConfigs" stripe empty-text="暂无 Kafka 配置">
            <el-table-column prop="name" label="配置名称" min-width="150" />
            <el-table-column prop="brokers" label="Broker 地址" min-width="260" show-overflow-tooltip />
            <el-table-column label="认证方式" width="140">
              <template #default="{ row }">{{ authLabel(row.auth_type) }}</template>
            </el-table-column>
            <el-table-column prop="default_topic_prefix" label="Topic 前缀" min-width="150" />
            <el-table-column label="状态" width="100">
              <template #default="{ row }"><el-tag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? "启用" : "停用" }}</el-tag></template>
            </el-table-column>
            <el-table-column label="操作" width="170" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openEdit('kafka', row)">编辑</el-button>
                <el-button link type="danger" @click="removeItem('kafka', row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="复制账号" name="accounts">
          <div class="section-toolbar">
            <div class="section-copy">
              <strong>数据库复制账号</strong><span>账号仅在创建任务时引用，正式接入后由后端加密存储</span>
            </div>
            <el-button type="primary" @click="openCreate('account')">新增复制账号</el-button>
          </div>
          <el-table :data="accounts" stripe empty-text="暂无复制账号">
            <el-table-column prop="name" label="账号名称" min-width="150" />
            <el-table-column label="数据库类型" width="130">
              <template #default="{ row }"><el-tag :type="row.db_type === 'mysql' ? 'primary' : 'success'">{{ dbLabel(row.db_type) }}</el-tag></template>
            </el-table-column>
            <el-table-column prop="username" label="用户名" min-width="150" />
            <el-table-column label="密码" width="120"><template #default="{ row }">{{ maskSecret(row.password_set) }}</template></el-table-column>
            <el-table-column prop="auth_database" label="认证库" min-width="130" />
            <el-table-column label="状态" width="100">
              <template #default="{ row }"><el-tag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? "启用" : "停用" }}</el-tag></template>
            </el-table-column>
            <el-table-column label="操作" width="170" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openEdit('account', row)">编辑</el-button>
                <el-button link type="danger" @click="removeItem('account', row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="下游接口" name="endpoints">
          <div class="section-toolbar">
            <div class="section-copy">
              <strong>下游执行接口</strong><span>用于创建、启动、停止和查询 Canal / MongoShake 任务</span>
            </div>
            <el-button type="primary" @click="openCreate('endpoint')">新增下游接口</el-button>
          </div>
          <el-table :data="endpoints" stripe empty-text="暂无下游接口">
            <el-table-column prop="name" label="接口名称" min-width="150" />
            <el-table-column prop="base_url" label="服务地址" min-width="260" show-overflow-tooltip />
            <el-table-column label="鉴权" width="130"><template #default="{ row }">{{ endpointAuthLabel(row.auth_type) }}</template></el-table-column>
            <el-table-column prop="timeout_seconds" label="超时(秒)" width="110" />
            <el-table-column label="状态" width="100">
              <template #default="{ row }"><el-tag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? "启用" : "停用" }}</el-tag></template>
            </el-table-column>
            <el-table-column label="操作" width="170" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openEdit('endpoint', row)">编辑</el-button>
                <el-button link type="danger" @click="removeItem('endpoint', row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="680px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="120px">
        <template v-if="editingType === 'kafka'">
          <el-form-item label="配置名称" prop="name"><el-input v-model="form.name" placeholder="例如：生产 Kafka" /></el-form-item>
          <el-form-item label="Broker 地址" prop="brokers"><el-input v-model="form.brokers" placeholder="kafka-01:9092,kafka-02:9092" /></el-form-item>
          <el-form-item label="认证方式"><el-select v-model="form.auth_type" style="width:100%"><el-option label="无认证" value="none" /><el-option label="SASL/PLAIN" value="sasl_plain" /><el-option label="SASL/SCRAM" value="sasl_scram" /></el-select></el-form-item>
          <el-form-item v-if="form.auth_type !== 'none'" label="用户名" prop="username"><el-input v-model="form.username" /></el-form-item>
          <el-form-item v-if="form.auth_type !== 'none'" label="密码" prop="password"><el-input v-model="form.password" type="password" show-password /></el-form-item>
          <el-form-item label="Topic 前缀"><el-input v-model="form.default_topic_prefix" placeholder="例如：db_cdc_" /></el-form-item>
        </template>
        <template v-else-if="editingType === 'account'">
          <el-form-item label="账号名称" prop="name"><el-input v-model="form.name" placeholder="例如：生产 MySQL 复制账号" /></el-form-item>
          <el-form-item label="数据库类型" prop="db_type"><el-radio-group v-model="form.db_type"><el-radio-button value="mysql">MySQL</el-radio-button><el-radio-button value="mongodb">MongoDB</el-radio-button></el-radio-group></el-form-item>
          <el-form-item label="用户名" prop="username"><el-input v-model="form.username" /></el-form-item>
          <el-form-item label="密码" prop="password"><el-input v-model="form.password" type="password" show-password /></el-form-item>
          <el-form-item v-if="form.db_type === 'mongodb'" label="认证库"><el-input v-model="form.auth_database" placeholder="admin" /></el-form-item>
          <el-alert v-if="form.db_type === 'mysql'" title="Canal 账号需具备 REPLICATION SLAVE、REPLICATION CLIENT 和 SELECT 权限。" type="warning" :closable="false" />
          <el-alert v-else title="MongoShake 账号需具备读取 oplog/change stream 所需权限。" type="warning" :closable="false" />
        </template>
        <template v-else>
          <el-form-item label="接口名称" prop="name"><el-input v-model="form.name" placeholder="例如：华东复制服务" /></el-form-item>
          <el-form-item label="服务地址" prop="base_url"><el-input v-model="form.base_url" placeholder="https://copy-service.example.com/api" /></el-form-item>
          <el-form-item label="鉴权方式"><el-select v-model="form.auth_type" style="width:100%"><el-option label="无认证" value="none" /><el-option label="Bearer Token" value="bearer" /><el-option label="API Key" value="api_key" /></el-select></el-form-item>
          <el-form-item v-if="form.auth_type !== 'none'" label="凭据" prop="credential"><el-input v-model="form.credential" type="password" show-password /></el-form-item>
          <el-form-item label="请求超时"><el-input-number v-model="form.timeout_seconds" :min="1" :max="300" /><span class="unit">秒</span></el-form-item>
        </template>
        <el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>
        <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="2" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogVisible=false">取消</el-button><el-button type="primary" @click="saveItem">保存草稿</el-button></template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { DATA_COPY_STORAGE_KEYS, maskSecret, nextDraftId, readDraftList, sanitizeDraftConfig, writeDraftList } from "../utils/dataCopyDraftStore";

const activeTab = ref("kafka");
const dialogVisible = ref(false);
const editingType = ref("kafka");
const editingId = ref(null);
const formRef = ref(null);
const kafkaConfigs = ref([]);
const accounts = ref([]);
const endpoints = ref([]);
const form = reactive({});
const rules = { name: [{ required: true, message: "请输入名称", trigger: "blur" }], brokers: [{ required: true, message: "请输入 Broker 地址", trigger: "blur" }], db_type: [{ required: true, message: "请选择数据库类型", trigger: "change" }], username: [{ required: true, message: "请输入用户名", trigger: "blur" }], base_url: [{ required: true, message: "请输入服务地址", trigger: "blur" }] };

const dialogTitle = computed(() => `${editingId.value ? "编辑" : "新增"}${{ kafka: " Kafka 配置", account: "复制账号", endpoint: "下游接口" }[editingType.value]}`);
function defaults(type) { if (type === "kafka") return { name: "", brokers: "", auth_type: "none", username: "", password: "", default_topic_prefix: "db_cdc_", enabled: true, remark: "" }; if (type === "account") return { name: "", db_type: "mysql", username: "", password: "", auth_database: "admin", enabled: true, remark: "" }; return { name: "", base_url: "", auth_type: "bearer", credential: "", timeout_seconds: 30, enabled: true, remark: "" }; }
function listFor(type) { return type === "kafka" ? kafkaConfigs : type === "account" ? accounts : endpoints; }
function keyFor(type) { return type === "kafka" ? DATA_COPY_STORAGE_KEYS.kafka : type === "account" ? DATA_COPY_STORAGE_KEYS.accounts : DATA_COPY_STORAGE_KEYS.endpoints; }
function loadData() { kafkaConfigs.value = readDraftList(DATA_COPY_STORAGE_KEYS.kafka); accounts.value = readDraftList(DATA_COPY_STORAGE_KEYS.accounts); endpoints.value = readDraftList(DATA_COPY_STORAGE_KEYS.endpoints); }
function openCreate(type) { editingType.value = type; editingId.value = null; Object.keys(form).forEach((key) => delete form[key]); Object.assign(form, defaults(type)); dialogVisible.value = true; }
function openEdit(type, row) { editingType.value = type; editingId.value = row.id; Object.keys(form).forEach((key) => delete form[key]); Object.assign(form, defaults(type), JSON.parse(JSON.stringify(row))); dialogVisible.value = true; }
async function saveItem() { await formRef.value?.validate(); const target = listFor(editingType.value); const previous = target.value.find((row) => row.id === editingId.value) || {}; if (editingType.value === "account" && !form.password && !previous.password_set) { ElMessage.warning("请输入复制账号密码"); return; } if (editingType.value === "kafka" && form.auth_type !== "none" && !form.password && !previous.password_set) { ElMessage.warning("请输入 Kafka 认证密码"); return; } if (editingType.value === "endpoint" && form.auth_type !== "none" && !form.credential && !previous.credential_set) { ElMessage.warning("请输入下游接口凭据"); return; } const raw = { ...form, id: editingId.value || nextDraftId(target.value), updated_at: new Date().toISOString() }; const item = sanitizeDraftConfig(editingType.value, raw, previous); const index = target.value.findIndex((row) => row.id === item.id); if (index >= 0) target.value.splice(index, 1, item); else target.value.unshift(item); writeDraftList(keyFor(editingType.value), target.value); dialogVisible.value = false; ElMessage.success("前端草稿已保存（敏感值未落盘）"); }
async function removeItem(type, row) { await ElMessageBox.confirm(`确认删除“${row.name}”？`, "删除确认", { type: "warning" }); const target = listFor(type); target.value = target.value.filter((item) => item.id !== row.id); writeDraftList(keyFor(type), target.value); ElMessage.success("已删除"); }
function dbLabel(type) { return type === "mysql" ? "MySQL" : "MongoDB"; }
function authLabel(type) { return { none: "无认证", sasl_plain: "SASL/PLAIN", sasl_scram: "SASL/SCRAM" }[type] || type; }
function endpointAuthLabel(type) { return { none: "无认证", bearer: "Bearer Token", api_key: "API Key" }[type] || type; }
onMounted(loadData);
</script>

<style scoped>
.data-copy-page { display: flex; flex-direction: column; gap: 16px; }
.draft-alert { margin-top: -4px; }
.summary-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
.summary-card { min-height: 112px; padding: 18px 20px; border: 1px solid var(--border-soft); background: var(--bg-secondary); display: grid; grid-template-columns: 1fr auto; align-items: center; box-shadow: var(--shadow-sm); }
.summary-card span { color: var(--text-regular); font-weight: 600; }.summary-card strong { color: var(--brand); font-size: 30px; }.summary-card small { grid-column: 1 / -1; color: var(--text-soft); }
.section-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin: 4px 0 16px; }.section-copy { display: flex; flex-direction: column; gap: 3px; }.section-copy span { color: var(--text-soft); font-size: 13px; }.unit { margin-left: 8px; color: var(--text-soft); }
@media (max-width: 900px) { .summary-grid { grid-template-columns: 1fr; } }
</style>
