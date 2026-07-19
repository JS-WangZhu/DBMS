<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>{{ dbLabel }} 策略</span>
          <div class="header-actions">
            <el-input v-model="policyKeyword" clearable placeholder="搜索策略名称、实例或 cron" style="width: 260px" @input="mysqlPage.current = 1" />
            <el-button type="primary" @click="openCreatePolicyDialog">新建策略</el-button>
            <el-button @click="refreshAll">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table :data="mysqlPoliciesData" stripe style="width: 100%">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column label="备份实例" min-width="200">
          <template #default="scope">{{ getInstanceLabel(scope.row.target_id) }}</template>
        </el-table-column>
        <el-table-column v-if="postgresqlMode" label="备份库" min-width="180">
          <template #default="scope">{{ getPostgresqlDatabaseSummary(scope.row) }}</template>
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
          v-model:current-page="mysqlPage.current"
          v-model:page-size="mysqlPage.size"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="filteredMysqlPolicies.length"
          @size-change="handleMysqlSizeChange"
          @current-change="handleMysqlCurrentChange"
        />
      </div>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" :width="postgresqlMode ? '960px' : '760px'">
      <el-form :model="form" label-width="130px">
        <el-form-item label="策略名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="数据库类型">
          <el-select v-model="form.db_type" style="width: 100%" disabled>
            <el-option :label="dbLabel" :value="DB_TYPE" />
          </el-select>
        </el-form-item>
        <el-form-item label="目标类型">
          <el-select v-model="form.target_type" style="width: 100%">
            <el-option label="实例" value="instance" />
          </el-select>
        </el-form-item>
        <el-form-item label="备份实例">
          <el-select v-model="form.target_id" filterable style="width: 100%" placeholder="请选择已纳管实例" @change="onTargetInstanceChange">
            <el-option v-for="item in managedInstances" :key="item.id" :label="item.label" :value="item.id" />
          </el-select>
        </el-form-item>
        <template v-if="postgresqlMode">
          <el-form-item label="备份格式">
            <el-tag type="success">Custom 二进制（pg_restore）</el-tag>
            <span class="hint-text pg-format-hint">多库分别生成 .dump 后统一打包</span>
          </el-form-item>
          <el-form-item label="需要备份的库" required>
            <el-select
              v-model="form.postgresql_databases"
              multiple
              filterable
              allow-create
              default-first-option
              style="width: 100%"
              placeholder="请选择或手工输入一个或多个数据库"
              :loading="postgresqlDatabasesLoading"
              @change="onPostgresqlDatabasesChange"
            >
              <el-option v-for="database in postgresqlDatabaseOptions" :key="database" :label="database" :value="database" />
            </el-select>
            <el-button link type="primary" :loading="postgresqlDatabasesLoading" @click="loadPostgresqlDatabases">刷新数据库</el-button>
          </el-form-item>
          <el-form-item v-if="form.postgresql_databases.length" label="排除表">
            <div class="pg-database-scopes">
              <el-card v-for="database in form.postgresql_databases" :key="database" shadow="never" class="pg-database-card">
                <template #header>
                  <div class="pg-database-header">
                    <strong>{{ database }}</strong>
                    <el-button link type="primary" :loading="!!postgresqlTableLoading[database]" @click="loadPostgresqlTables(database)">刷新表</el-button>
                  </div>
                </template>
                <el-select
                  v-model="form.postgresql_excluded_tables[database]"
                  multiple
                  filterable
                  allow-create
                  default-first-option
                  collapse-tags
                  collapse-tags-tooltip
                  style="width: 100%"
                  :loading="!!postgresqlTableLoading[database]"
                  placeholder="可选；未选择时备份该库全部表"
                  @visible-change="visible => visible && ensurePostgresqlTables(database)"
                >
                  <el-option v-for="table in (postgresqlTableOptions[database] || [])" :key="table" :label="table" :value="table" />
                </el-select>
              </el-card>
            </div>
          </el-form-item>
        </template>
        <el-form-item label="备份工具">
          <el-select v-model="form.backup_tool_config_id" style="width: 100%" placeholder="选择已配置工具" clearable @change="onBackupToolConfigChange">
            <el-option v-for="tool in currentDbTypeTools" :key="tool.id" :label="`${tool.name} (${tool.tool_path})`" :value="tool.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="调度(cron)"><el-input v-model="form.cron_expr" placeholder="例如: 0 2 * * *" /></el-form-item>
        <el-form-item label="本地存储路径"><el-input v-model="form.storage_path" /></el-form-item>
        <el-form-item label="保留天数"><el-input-number v-model="form.retain_days" :min="1" style="width: 100%" /></el-form-item>
        <el-form-item :label="postgresqlMode ? 'pg_dump 压缩' : '压缩方式'">
          <el-select v-model="form.compress_method" style="width: 100%">
            <template v-if="postgresqlMode">
              <el-option label="默认（pg_dump 默认 gzip）" value="default" />
              <el-option label="gzip" value="gzip" />
              <el-option label="lz4" value="lz4" />
              <el-option label="zstd" value="zstd" />
              <el-option label="不压缩" value="none" />
            </template>
            <template v-else>
              <el-option label="不压缩" value="none" />
              <el-option label="gzip" value="gzip" />
              <el-option label="zstd" value="zstd" />
            </template>
          </el-select>
          <div v-if="postgresqlMode" class="hint-text">压缩由 pg_dump 在写入每个 Custom .dump 时完成；多库外层 tar 不再重复压缩。</div>
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
  listPostgresqlBackupDatabases,
  listPostgresqlBackupTables,
  listNotifyTargets,
  listBackupKeys,
  listS3StorageConfigs,
  runBackup,
  updateBackupPolicy,
} from "../api/modules/backups";

const props = defineProps({
  dbType: { type: String, default: "mysql" },
  dbLabel: { type: String, default: "MySQL" },
  toolName: { type: String, default: "mysqldump" },
  postgresqlMode: { type: Boolean, default: false },
});

const DB_TYPE = props.dbType;
const dbLabel = props.dbLabel;
const DEFAULT_TOOL = props.toolName;
const postgresqlMode = props.postgresqlMode;

const mysqlPolicies = ref([]);
const policyKeyword = ref("");
const dialogVisible = ref(false);
const saving = ref(false);
const editingPolicyId = ref(null);

const mysqlPage = reactive({
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
const postgresqlDatabaseOptions = ref([]);
const postgresqlDatabasesLoading = ref(false);
const postgresqlTableOptions = reactive({});
const postgresqlTableLoading = reactive({});

  const form = reactive({
    name: "",
    db_type: DB_TYPE,
    target_type: "instance",
    target_id: null,
  backup_type: "full",
  tool_name: DEFAULT_TOOL,
  backup_tool_config_id: null,
  cron_expr: "0 2 * * *",
    storage_path: "/tmp",
    retain_days: 7,
    compress: true,
    compress_method: postgresqlMode ? "default" : "gzip",
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
  postgresql_databases: [],
  postgresql_excluded_tables: {},
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

const filteredMysqlPolicies = computed(() => {
  const keyword = policyKeyword.value.trim().toLowerCase();
  if (!keyword) return mysqlPolicies.value;
  return mysqlPolicies.value.filter((policy) =>
    [policy.name, getInstanceLabel(policy.target_id), policy.cron_expr]
      .some((value) => String(value || "").toLowerCase().includes(keyword))
  );
});

const mysqlPoliciesData = computed(() => {
  const start = (mysqlPage.current - 1) * mysqlPage.size;
  const end = start + mysqlPage.size;
  return filteredMysqlPolicies.value.slice(start, end);
});

const dialogTitle = computed(() => (editingPolicyId.value ? `编辑 ${dbLabel} 备份策略` : `新建 ${dbLabel} 备份策略`));

function resetPolicyForm() {
  editingPolicyId.value = null;
  form.name = "";
  form.db_type = DB_TYPE;
  form.target_type = "instance";
  form.target_id = null;
  form.backup_type = "full";
  form.tool_name = DEFAULT_TOOL;
  form.backup_tool_config_id = null;
  form.cron_expr = "0 2 * * *";
    form.storage_path = "/tmp";
    form.retain_days = 7;
    form.compress = true;
    form.compress_method = postgresqlMode ? "default" : "gzip";
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
  form.postgresql_databases = [];
  form.postgresql_excluded_tables = {};
  postgresqlDatabaseOptions.value = [];
  Object.keys(postgresqlTableOptions).forEach((key) => delete postgresqlTableOptions[key]);
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

async function loadPostgresqlDatabases() {
  if (!postgresqlMode || !form.target_id) return;
  postgresqlDatabasesLoading.value = true;
  try {
    const params = { instance_id: form.target_id };
    if (form.backup_agent_id) params.backup_agent_id = form.backup_agent_id;
    const { data } = await listPostgresqlBackupDatabases(params);
    postgresqlDatabaseOptions.value = data.data || [];
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载 PostgreSQL 数据库失败");
  } finally {
    postgresqlDatabasesLoading.value = false;
  }
}

async function loadPostgresqlTables(database) {
  if (!postgresqlMode || !form.target_id || !database) return;
  postgresqlTableLoading[database] = true;
  try {
    const params = { instance_id: form.target_id, database };
    if (form.backup_agent_id) params.backup_agent_id = form.backup_agent_id;
    const { data } = await listPostgresqlBackupTables(params);
    postgresqlTableOptions[database] = data.data || [];
  } catch (error) {
    ElMessage.error(error.response?.data?.message || `加载数据库 ${database} 的表失败`);
  } finally {
    postgresqlTableLoading[database] = false;
  }
}

function ensurePostgresqlTables(database) {
  if (!postgresqlTableOptions[database]) loadPostgresqlTables(database);
}

function onPostgresqlDatabasesChange(databases) {
  const next = {};
  databases.forEach((database) => {
    next[database] = form.postgresql_excluded_tables[database] || [];
  });
  form.postgresql_excluded_tables = next;
}

async function onTargetInstanceChange() {
  if (!postgresqlMode) return;
  form.postgresql_databases = [];
  form.postgresql_excluded_tables = {};
  await loadPostgresqlDatabases();
}

function getPostgresqlDatabaseSummary(policy) {
  const rows = policy.extra_json?.postgresql_backup?.databases;
  return Array.isArray(rows) && rows.length ? rows.map((row) => row.name).join(", ") : "未配置";
}

async function loadPolicies() {
  try {
    const { data } = await listBackupPoliciesByType(DB_TYPE);
    mysqlPolicies.value = data.data || [];
    mysqlPage.total = mysqlPolicies.value.length;
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
    const postgresql = extra.postgresql_backup || {};
  editingPolicyId.value = policy.id;
  form.name = policy.name || "";
  form.db_type = policy.db_type || DB_TYPE;
  form.target_type = policy.target_type || "instance";
  form.target_id = policy.target_id || null;
  form.backup_type = policy.backup_type || "full";
  form.tool_name = policy.tool_name || DEFAULT_TOOL;
  form.backup_tool_config_id = policy.backup_tool_config_id || null;
  form.cron_expr = policy.cron_expr || "0 2 * * *";
    form.storage_path = policy.storage_path || "/tmp";
    form.retain_days = policy.retain_days || 7;
    form.compress = !!policy.compress;
    form.compress_method = policy.compress_method || (policy.compress ? (postgresqlMode ? "default" : "gzip") : "none");
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
  const databaseRows = Array.isArray(postgresql.databases) ? postgresql.databases : [];
  form.postgresql_databases = databaseRows.map((row) => row.name).filter(Boolean);
  form.postgresql_excluded_tables = Object.fromEntries(databaseRows.map((row) => [
    row.name,
    row.table_filter?.mode === "exclude" && Array.isArray(row.table_filter.tables) ? row.table_filter.tables : [],
  ]));
}

async function openCreatePolicyDialog() {
  resetPolicyForm();
  await loadManagedInstances();
  if (managedInstances.value.length > 0) {
    form.target_id = managedInstances.value[0].id;
  }
  if (postgresqlMode) await loadPostgresqlDatabases();
  dialogVisible.value = true;
}

async function openEditPolicyDialog(policy) {
  resetPolicyForm();
  await loadManagedInstances();
  applyPolicyToForm(policy);
  if (postgresqlMode) {
    await loadPostgresqlDatabases();
    await Promise.all(form.postgresql_databases.filter((database) => form.postgresql_excluded_tables[database]?.length).map(loadPostgresqlTables));
  }
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
        ...(postgresqlMode ? {
          postgresql_backup: {
            format: "custom",
            databases: form.postgresql_databases.map((database) => {
              const tables = form.postgresql_excluded_tables[database] || [];
              return {
                name: database,
                table_filter: { mode: tables.length ? "exclude" : "all", tables },
              };
            }),
          },
        } : {}),
      },
    };
  }

  async function onSavePolicy() {
    if (!form.target_id) {
      ElMessage.warning("请选择备份实例");
      return;
    }
    if (postgresqlMode && !form.postgresql_databases.length) {
      ElMessage.warning("请至少选择一个需要备份的数据库");
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

function handleMysqlSizeChange(size) {
  mysqlPage.size = size;
  mysqlPage.current = 1;
}

function handleMysqlCurrentChange(current) {
  mysqlPage.current = current;
}

function onBackupToolConfigChange(configId) {
  if (configId) {
    const tool = backupToolConfigs.value.find((t) => t.id === configId);
    if (tool) {
      form.tool_name = DEFAULT_TOOL;
    }
  }
}

async function onBackupAgentChange() {
  if (postgresqlMode) {
    form.postgresql_databases = [];
    form.postgresql_excluded_tables = {};
    await loadPostgresqlDatabases();
  }
  if (!form.backup_tool_config_id) return;
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

  .pg-format-hint { margin-left: 10px; color: var(--el-text-color-secondary); }
.pg-database-scopes { display: flex; flex-direction: column; gap: 10px; width: 100%; }
.pg-database-card { width: 100%; }
.pg-database-header { display: flex; justify-content: space-between; align-items: center; }

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
