<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>MongoDB 策略</span>
          <div class="header-actions">
            <el-button type="primary" @click="openCreatePolicyDialog">新建策略</el-button>
            <el-button @click="refreshAll">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table :data="mongoPoliciesData" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column label="备份实例" min-width="200">
          <template #default="scope">{{ getInstanceLabel(scope.row.target_id) }}</template>
        </el-table-column>
        <el-table-column prop="cron_expr" label="调度" min-width="140" />
        <el-table-column prop="retain_days" label="保留天数" width="100" />
        <el-table-column label="Agent" min-width="120">
          <template #default="scope">{{ scope.row.agent_name || "本地执行" }}</template>
        </el-table-column>
        <el-table-column label="操作" width="280">
          <template #default="scope">
            <el-button link type="primary" @click="run(scope.row, true)">DryRun</el-button>
            <el-button link type="success" @click="run(scope.row, false)">执行</el-button>
            <el-button link type="primary" @click="openEditPolicyDialog(scope.row)">编辑</el-button>
            <el-button link :type="scope.row.enabled ? 'danger' : 'info'" @click="togglePolicy(scope.row)">
              {{ scope.row.enabled ? "停用" : "启用" }}
            </el-button>
            <el-button link type="danger" @click="removePolicy(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="mongoPage.current"
          v-model:page-size="mongoPage.size"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="mongoPage.total"
          @size-change="handleMongoSizeChange"
          @current-change="handleMongoCurrentChange"
        />
      </div>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="760px">
      <el-form :model="form" label-width="130px">
        <el-form-item label="策略名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="数据库类型">
          <el-select v-model="form.db_type" style="width: 100%" disabled>
            <el-option label="MongoDB" value="mongodb" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标类型">
          <el-select v-model="form.target_type" style="width: 100%">
            <el-option label="实例" value="instance" />
          </el-select>
        </el-form-item>
        <el-form-item label="备份实例">
          <el-select v-model="form.target_id" filterable style="width: 100%" placeholder="请选择已纳管实例">
            <el-option v-for="item in managedInstances" :key="item.id" :label="item.label" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="备份工具">
          <el-select v-model="form.backup_tool_config_id" style="width: 100%" placeholder="选择已配置工具" clearable @change="onBackupToolConfigChange">
            <el-option v-for="tool in currentDbTypeTools" :key="tool.id" :label="`${tool.name} (${tool.tool_path})`" :value="tool.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="调度(cron)"><el-input v-model="form.cron_expr" placeholder="例如: 0 2 * * *" /></el-form-item>
        <el-form-item label="本地存储路径"><el-input v-model="form.storage_path" /></el-form-item>
        <el-form-item label="保留天数"><el-input-number v-model="form.retain_days" :min="1" style="width: 100%" /></el-form-item>
        <el-form-item label="压缩方式">
          <el-select v-model="form.compress_method" style="width: 100%">
            <el-option label="不压缩" value="none" />
            <el-option label="gzip" value="gzip" />
            <el-option label="zstd" value="zstd" />
          </el-select>
        </el-form-item>
        <el-form-item label="备份加密"><el-switch v-model="form.encrypt_enabled" /></el-form-item>
        <el-form-item v-if="form.encrypt_enabled" label="公钥">
          <div class="encrypt-box">
            <el-select v-model="form.encrypt_key_id" filterable clearable placeholder="选择托管密钥" style="width: 100%" @change="onKeySelectChange">
              <el-option v-for="key in backupKeys" :key="key.id" :label="key.name" :value="key.id" />
            </el-select>
            <el-input
              v-if="showPublicKeyInput"
              v-model="form.encrypt_public_key"
              type="textarea"
              :rows="4"
              placeholder="粘贴 PEM 格式公钥"
            />
            <el-upload v-if="showPublicKeyInput" :show-file-list="false" :auto-upload="false" :on-change="onPublicKeyUpload">
              <el-button>上传公钥</el-button>
            </el-upload>
          </div>
        </el-form-item>
        <el-form-item label="启用策略"><el-switch v-model="form.enabled" /></el-form-item>

        <el-divider>执行 Agent</el-divider>
        <el-form-item label="选择 Agent">
          <el-select v-model="form.backup_agent_id" filterable style="width: 100%" placeholder="默认本地执行" @change="onBackupAgentChange">
            <el-option label="本地执行" :value="null" />
            <el-option v-for="agent in enabledAgents" :key="agent.id" :label="`${agent.name} (${agent.url})`" :value="agent.id" />
          </el-select>
        </el-form-item>

        <el-divider>失败通知</el-divider>
        <el-form-item label="失败通知"><el-switch v-model="form.notify_on_failure" /></el-form-item>
        <el-form-item label="通知渠道">
          <el-checkbox-group v-model="form.notify_channels">
            <el-checkbox label="wecom">企微Webhook</el-checkbox>
            <el-checkbox label="email">邮件</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="通知地址选择">
          <el-select v-model="form.notify_target_ids" multiple collapse-tags collapse-tags-tooltip style="width: 100%" placeholder="可选">
            <el-option v-for="target in enabledNotifyTargets" :key="target.id" :label="formatNotifyTarget(target)" :value="target.id" />
          </el-select>
        </el-form-item>

        <el-divider>S3 异地存储</el-divider>
        <el-form-item label="启用S3上传"><el-switch v-model="form.s3_enabled" /></el-form-item>
        <el-form-item v-if="form.s3_enabled" label="S3存储配置">
          <el-select v-model="form.s3_storage_config_id" filterable style="width: 100%" placeholder="请选择S3存储配置">
            <el-option v-for="config in enabledS3StorageConfigs" :key="config.id" :label="formatS3StorageConfig(config)" :value="config.id" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.s3_enabled" label="上传方式">
          <el-select v-model="form.s3_upload_mode" style="width: 100%">
            <el-option label="原生方式 (boto3)" value="native" />
            <el-option label="us3 方式" value="us3" />
          </el-select>
          <div class="hint-text">文件大于 80G 建议选择 us3 方式，示例：/data/us3cli-linux64 cp /data/backup/xxx.enc us3://bucket/prefix/</div>
        </el-form-item>
        <el-form-item v-if="form.s3_enabled && form.s3_upload_mode === 'us3'" label="us3命令路径">
          <el-input v-model="form.us3_cli_path" placeholder="/data/us3cli-linux64" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSavePolicy">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  createBackupPolicy,
  deleteBackupPolicy,
  listBackupAgents,
  listBackupPoliciesByType,
  listBackupToolConfigs,
  listManagedInstances,
  listNotifyTargets,
  listBackupKeys,
  listS3StorageConfigs,
  runBackup,
  updateBackupPolicy,
} from "../api/modules/backups";

const DB_TYPE = "mongodb";

const mongoPolicies = ref([]);
const dialogVisible = ref(false);
const saving = ref(false);
const editingPolicyId = ref(null);

const mongoPage = reactive({
  current: 1,
  size: 10,
  total: 0,
});

const managedInstances = ref([]);
const notifyTargets = ref([]);
const s3StorageConfigs = ref([]);
const backupToolConfigs = ref([]);
const agents = ref([]);
const backupKeys = ref([]);

const form = reactive({
  name: "",
  db_type: "mongodb",
  target_type: "instance",
  target_id: null,
  backup_type: "full",
  tool_name: "mongodump",
  backup_tool_config_id: null,
  cron_expr: "0 2 * * *",
    storage_path: "/tmp",
    retain_days: 7,
    compress: true,
    compress_method: "gzip",
    encrypt_enabled: false,
    encrypt_key_id: null,
    encrypt_public_key: "",
    enabled: true,
  backup_agent_id: null,
  notify_on_failure: true,
  notify_channels: ["wecom", "email"],
  notify_target_ids: [],
  s3_enabled: false,
  s3_storage_config_id: null,
  s3_upload_mode: "native",
  us3_cli_path: "/data/us3cli-linux64",
});

const enabledNotifyTargets = computed(() => notifyTargets.value.filter((item) => item.enabled));
const enabledS3StorageConfigs = computed(() => s3StorageConfigs.value.filter((item) => item.enabled));
const currentDbTypeTools = computed(() => {
  const toolRows = backupToolConfigs.value.filter((item) => item.db_type === DB_TYPE && item.enabled);
  if (form.backup_agent_id) {
    return toolRows.filter((item) => item.backup_agent_id === form.backup_agent_id);
  }
  return toolRows.filter((item) => !item.backup_agent_id);
});
const enabledAgents = computed(() => agents.value.filter((item) => item.enabled));
const showPublicKeyInput = computed(() => form.encrypt_enabled && !form.encrypt_key_id);

const mongoPoliciesData = computed(() => {
  const start = (mongoPage.current - 1) * mongoPage.size;
  const end = start + mongoPage.size;
  return mongoPolicies.value.slice(start, end);
});

const dialogTitle = computed(() => (editingPolicyId.value ? "编辑 MongoDB 备份策略" : "新建 MongoDB 备份策略"));

function resetPolicyForm() {
  editingPolicyId.value = null;
  form.name = "";
  form.db_type = "mongodb";
  form.target_type = "instance";
  form.target_id = null;
  form.backup_type = "full";
  form.tool_name = "mongodump";
  form.backup_tool_config_id = null;
  form.cron_expr = "0 2 * * *";
    form.storage_path = "/tmp";
    form.retain_days = 7;
    form.compress = true;
    form.compress_method = "gzip";
    form.encrypt_enabled = false;
    form.encrypt_key_id = null;
    form.encrypt_public_key = "";
    form.enabled = true;
  form.backup_agent_id = null;
  form.notify_on_failure = true;
  form.notify_channels = ["wecom", "email"];
  form.notify_target_ids = [];
  form.s3_enabled = false;
  form.s3_storage_config_id = null;
  form.s3_upload_mode = "native";
  form.us3_cli_path = "/data/us3cli-linux64";
}

function formatNotifyTarget(target) {
  const channel = target.channel === "wecom" ? "企微" : "邮件";
  return `[${channel}] ${target.name} - ${target.address}`;
}

function formatS3StorageConfig(config) {
  return `${config.name} (${config.bucket}${config.prefix ? "/" + config.prefix : ""})`;
}

function getInstanceLabel(targetId) {
  const row = managedInstances.value.find((item) => item.id === targetId);
  return row?.label || `实例ID: ${targetId}`;
}

async function loadManagedInstances() {
  try {
    const { data } = await listManagedInstances(DB_TYPE);
    managedInstances.value = data.data || [];
  } catch (error) {
    console.error("加载实例失败", error);
  }
}

async function loadPolicies() {
  try {
    const { data } = await listBackupPoliciesByType(DB_TYPE);
    mongoPolicies.value = data.data || [];
    mongoPage.total = mongoPolicies.value.length;
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载策略失败");
  }
}

async function loadNotifyTargets() {
  try {
    const { data } = await listNotifyTargets();
    notifyTargets.value = data.data || [];
  } catch (error) {
    console.error("加载通知地址失败", error);
  }
}

async function loadS3StorageConfigs() {
  try {
    const { data } = await listS3StorageConfigs({ enabled: true });
    s3StorageConfigs.value = data.data || [];
  } catch (error) {
    console.error("加载S3配置失败", error);
  }
}

async function loadBackupToolConfigs() {
  try {
    const { data } = await listBackupToolConfigs({ enabled: true });
    backupToolConfigs.value = data.data || [];
  } catch (error) {
    console.error("加载备份工具失败", error);
  }
}

async function loadBackupKeys() {
  try {
    const { data } = await listBackupKeys();
    backupKeys.value = data.data || [];
  } catch (error) {
    console.error("加载备份密钥失败", error);
  }
}

async function loadBackupAgents() {
  try {
    const { data } = await listBackupAgents({ enabled: true });
    agents.value = data.data || [];
  } catch (error) {
    console.error("加载Agent失败", error);
  }
}

async function refreshAll() {
  await Promise.all([
    loadManagedInstances(),
    loadNotifyTargets(),
    loadS3StorageConfigs(),
    loadBackupToolConfigs(),
    loadBackupKeys(),
    loadBackupAgents(),
    loadPolicies(),
  ]);
}

  function applyPolicyToForm(policy) {
    const extra = policy.extra_json || {};
    const notify = extra.notify || {};
    const s3 = extra.s3 || {};
    const encrypt = extra.encrypt || {};
  editingPolicyId.value = policy.id;
  form.name = policy.name || "";
  form.db_type = policy.db_type || "mongodb";
  form.target_type = policy.target_type || "instance";
  form.target_id = policy.target_id || null;
  form.backup_type = policy.backup_type || "full";
  form.tool_name = policy.tool_name || "mongodump";
  form.backup_tool_config_id = policy.backup_tool_config_id || null;
  form.cron_expr = policy.cron_expr || "0 2 * * *";
    form.storage_path = policy.storage_path || "/tmp";
    form.retain_days = policy.retain_days || 7;
    form.compress = !!policy.compress;
    form.compress_method = policy.compress_method || (policy.compress ? "gzip" : "none");
    form.encrypt_enabled = !!encrypt.enabled;
    form.encrypt_key_id = encrypt.key_id ?? null;
    form.encrypt_public_key = encrypt.public_key || "";
    form.enabled = !!policy.enabled;
  form.backup_agent_id = policy.backup_agent_id ?? null;
  form.notify_on_failure = notify.on_failure !== false;
  form.notify_channels = Array.isArray(notify.channels) ? notify.channels : ["wecom", "email"];
  form.notify_target_ids = Array.isArray(notify.target_ids) ? notify.target_ids : [];
  form.s3_enabled = !!s3.enabled;
  form.s3_storage_config_id = policy.s3_storage_config_id || null;
  form.s3_upload_mode = s3.upload_mode === "us3" ? "us3" : "native";
  form.us3_cli_path = s3.us3_cli_path || "/data/us3cli-linux64";
}

async function openCreatePolicyDialog() {
  resetPolicyForm();
  await loadManagedInstances();
  if (managedInstances.value.length > 0) {
    form.target_id = managedInstances.value[0].id;
  }
  dialogVisible.value = true;
}

async function openEditPolicyDialog(policy) {
  resetPolicyForm();
  await loadManagedInstances();
  applyPolicyToForm(policy);
  dialogVisible.value = true;
}

function buildPolicyPayload() {
    return {
    name: form.name || `${DB_TYPE}-policy-${Date.now()}`,
    target_type: form.target_type,
    target_id: form.target_id,
    db_type: form.db_type,
    backup_type: form.backup_type,
    tool_name: form.tool_name,
    backup_tool_config_id: form.backup_tool_config_id || null,
    cron_expr: form.cron_expr,
    storage_path: form.storage_path,
    retain_days: form.retain_days,
      compress: form.compress_method !== "none",
      compress_method: form.compress_method,
      enabled: form.enabled,
    backup_agent_id: form.backup_agent_id,
    s3_storage_config_id: form.s3_enabled ? form.s3_storage_config_id : null,
      extra_json: {
        notify: {
          on_failure: form.notify_on_failure,
          channels: form.notify_channels,
          target_ids: form.notify_target_ids,
        },
        s3: {
          enabled: form.s3_enabled,
          upload_mode: form.s3_upload_mode,
          us3_cli_path: form.us3_cli_path,
        },
        compress_method: form.compress_method,
        encrypt: {
          enabled: form.encrypt_enabled,
          key_id: form.encrypt_key_id,
          public_key: form.encrypt_public_key,
        },
      },
    };
  }

  async function onSavePolicy() {
    if (!form.target_id) {
      ElMessage.warning("请选择备份实例");
      return;
    }
    if (form.encrypt_enabled && !form.encrypt_key_id && !form.encrypt_public_key) {
      ElMessage.warning("启用加密时请上传或粘贴公钥");
      return;
    }

  saving.value = true;
  try {
    const payload = buildPolicyPayload();
    if (editingPolicyId.value) {
      await updateBackupPolicy(editingPolicyId.value, payload);
      ElMessage.success("策略已更新");
    } else {
      await createBackupPolicy(payload);
      ElMessage.success("策略已创建");
    }
    dialogVisible.value = false;
    await loadPolicies();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "保存策略失败");
  } finally {
    saving.value = false;
  }
}

async function togglePolicy(policy) {
  await updateBackupPolicy(policy.id, { enabled: !policy.enabled });
  await loadPolicies();
}

async function run(policy, dryRun) {
  try {
    await runBackup(policy.id, dryRun);
    ElMessage.success("任务已触发");
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "触发失败");
  }
}

async function removePolicy(policy) {
  try {
    await ElMessageBox.confirm(`确认删除备份策略 ${policy.name} 吗？`, "提示", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await deleteBackupPolicy(policy.id);
    ElMessage.success("备份策略已删除");
    await loadPolicies();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.message || "删除备份策略失败");
    }
  }
}

function handleMongoSizeChange(size) {
  mongoPage.size = size;
  mongoPage.current = 1;
}

function handleMongoCurrentChange(current) {
  mongoPage.current = current;
}

function onBackupToolConfigChange(configId) {
  if (configId) {
    const tool = backupToolConfigs.value.find((t) => t.id === configId);
    if (tool) {
      form.tool_name = tool.db_type === "mysql" ? "mysqldump" : "mongodump";
    }
  }
}

function onBackupAgentChange() {
  if (!form.backup_tool_config_id) {
    return;
  }
  const keep = currentDbTypeTools.value.some((item) => item.id === form.backup_tool_config_id);
  if (!keep) {
    form.backup_tool_config_id = null;
  }
}

function onPublicKeyUpload(uploadFile) {
  const file = uploadFile?.raw || uploadFile;
  if (!file) {
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    form.encrypt_public_key = String(reader.result || "");
  };
  reader.readAsText(file);
}

function onKeySelectChange(keyId) {
  const key = backupKeys.value.find((item) => item.id === keyId);
  if (key) {
    form.encrypt_public_key = key.public_key || "";
  }
}
onMounted(refreshAll);
</script>

<style scoped>
.page {
  padding: 20px;
}

  .pagination-container {
    margin-top: 15px;
    display: flex;
    justify-content: flex-end;
  }

  .encrypt-box {
    display: flex;
    flex-direction: column;
    gap: 8px;
    width: 100%;
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
</style>
