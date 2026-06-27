<template>
  <div class="page">
    <el-card class="policy-card">
      <template #header>
        <div class="header-row">
          <span>备份策略（MySQL / MongoDB 分区）</span>
          <div class="header-actions">
            <el-button @click="openToolConfigDialog">备份工具配置</el-button>
            <el-button @click="openAgentDialog">Agent配置</el-button>
            <el-button type="primary" @click="openCreatePolicyDialog">新建策略</el-button>
            <el-button @click="refreshAll">刷新</el-button>
          </div>
        </div>
      </template>

      <el-row :gutter="20">
        <el-col :xs="24">
          <h4 class="sub-title">MySQL 策略</h4>
          <el-table :data="mysqlPoliciesData" stripe style="width: 100%">
            <el-table-column prop="id" label="ID" width="80" />
            <el-table-column prop="name" label="名称" min-width="160" />
            <el-table-column label="备份实例" min-width="200">
              <template #default="scope">
                {{ getInstanceLabel(scope.row.db_type, scope.row.target_id) }}
              </template>
            </el-table-column>
            <el-table-column prop="cron_expr" label="调度" min-width="140" />
            <el-table-column prop="retain_days" label="保留天数" width="100" />
            <el-table-column label="Agent" min-width="120">
              <template #default="scope">
                {{ scope.row.agent_name || '本地执行' }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="280">
              <template #default="scope">
                <el-button link type="primary" @click="run(scope.row, true)">DryRun</el-button>
                <el-button link type="success" @click="run(scope.row, false)">执行</el-button>
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
              :total="mysqlPage.total"
              @size-change="handleMysqlSizeChange"
              @current-change="handleMysqlCurrentChange"
            />
          </div>
        </el-col>

        <el-col :xs="24" style="margin-top: 20px">
          <h4 class="sub-title">MongoDB 策略</h4>
          <el-table :data="mongoPoliciesData" stripe style="width: 100%">
            <el-table-column prop="id" label="ID" width="80" />
            <el-table-column prop="name" label="名称" min-width="160" />
            <el-table-column label="备份实例" min-width="200">
              <template #default="scope">
                {{ getInstanceLabel(scope.row.db_type, scope.row.target_id) }}
              </template>
            </el-table-column>
            <el-table-column prop="cron_expr" label="调度" min-width="140" />
            <el-table-column prop="retain_days" label="保留天数" width="100" />
            <el-table-column label="Agent" min-width="120">
              <template #default="scope">
                {{ scope.row.agent_name || '本地执行' }}
              </template>
            </el-table-column>
            <el-table-column label="操作" width="280">
              <template #default="scope">
                <el-button link type="primary" @click="run(scope.row, true)">DryRun</el-button>
                <el-button link type="success" @click="run(scope.row, false)">执行</el-button>
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
        </el-col>
      </el-row>
    </el-card>

    <el-card>
      <template #header>
        <div class="header-row">
          <span>通知地址配置（企微 Webhook / 邮件）</span>
          <el-button type="primary" @click="openNotifyCreate">新增通知地址</el-button>
        </div>
      </template>

      <el-table :data="notifyTargets" stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column label="渠道" width="120">
          <template #default="scope">
            {{ scope.row.channel === "wecom" ? "企微Webhook" : "邮件" }}
          </template>
        </el-table-column>
        <el-table-column prop="address" label="地址" min-width="260" />
        <el-table-column label="状态" width="90">
          <template #default="scope">
            <el-tag v-if="scope.row.enabled" type="success">启用</el-tag>
            <el-tag v-else type="info">停用</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180">
          <template #default="scope">
            <el-button link type="primary" @click="openNotifyEdit(scope.row)">编辑</el-button>
            <el-button link type="danger" @click="removeNotifyTarget(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>



    <el-dialog v-model="dialogVisible" title="新建备份策略" width="760px">
      <el-form :model="form" label-width="130px">
        <el-form-item label="策略名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="数据库类型">
          <el-select v-model="form.db_type" style="width: 100%" @change="onDbTypeChange">
            <el-option label="MySQL" value="mysql" />
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
            <el-option
              v-for="item in currentManagedInstances"
              :key="item.id"
              :label="item.label"
              :value="item.id"
            />
          </el-select>
          <div class="hint-text">备份实例来自数据库管理中已纳管实例。</div>
        </el-form-item>
        <el-form-item label="备份工具">
          <el-select v-model="form.backup_tool_config_id" style="width: 100%" placeholder="选择已配置的工具" clearable @change="onBackupToolConfigChange">
            <el-option
              v-for="tool in currentDbTypeTools"
              :key="tool.id"
              :label="`${tool.name} (${tool.tool_path})`"
              :value="tool.id"
            />
          </el-select>
          <div class="hint-text">选择 Agent 后，仅显示该 Agent 下的工具；本地执行仅显示本地工具。</div>
        </el-form-item>
        <el-form-item label="调度(cron)"><el-input v-model="form.cron_expr" placeholder="例如: 0 2 * * *" /></el-form-item>
        <el-form-item label="本地存储路径"><el-input v-model="form.storage_path" /></el-form-item>
        <el-form-item label="保留天数"><el-input-number v-model="form.retain_days" :min="1" style="width: 100%" /></el-form-item>

        <el-form-item label="压缩"><el-switch v-model="form.compress" /></el-form-item>
        <el-form-item label="启用策略"><el-switch v-model="form.enabled" /></el-form-item>

        <el-divider>执行 Agent</el-divider>
        <el-form-item label="选择 Agent">
          <el-select v-model="form.backup_agent_id" filterable style="width: 100%" placeholder="默认本地执行" @change="onBackupAgentChange">
            <el-option label="本地执行" :value="null" />
            <el-option
              v-for="agent in enabledAgents"
              :key="agent.id"
              :label="`${agent.name} (${agent.url})`"
              :value="agent.id"
            />
          </el-select>
          <div class="hint-text">
            选择 Agent 后，备份将在远程 Agent 上执行；留空则本地执行。
          </div>
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
          <el-select v-model="form.notify_target_ids" multiple collapse-tags collapse-tags-tooltip style="width: 100%" placeholder="可选，按地址精确发送">
            <el-option
              v-for="target in enabledNotifyTargets"
              :key="target.id"
              :label="formatNotifyTarget(target)"
              :value="target.id"
            />
          </el-select>
          <div class="hint-text">
            可在上方“通知地址配置”中维护；若不选地址，则按“通知渠道 + 全局配置”发送。
          </div>
        </el-form-item>

        <el-divider>S3 异地存储</el-divider>
        <el-form-item label="启用S3上传"><el-switch v-model="form.s3_enabled" /></el-form-item>
        <el-form-item v-if="form.s3_enabled" label="S3存储配置">
          <el-select v-model="form.s3_storage_config_id" filterable style="width: 100%" placeholder="请选择S3存储配置">
            <el-option
              v-for="config in enabledS3StorageConfigs"
              :key="config.id"
              :label="formatS3StorageConfig(config)"
              :value="config.id"
            />
          </el-select>
          <div class="hint-text">
            可在"S3存储配置"页面维护公共S3配置，此处直接选择使用。
          </div>
        </el-form-item>
        <el-form-item v-if="form.s3_enabled" label="上传方式">
          <el-select v-model="form.s3_upload_mode" style="width: 100%">
            <el-option label="原生方式 (boto3)" value="native" />
            <el-option label="us3 方式" value="us3" />
          </el-select>
          <div class="hint-text">文件大于 80G 建议使用 us3 方式，示例：/data/us3cli-linux64 cp /data/backup/xxx.enc us3://bucket/prefix/</div>
        </el-form-item>
        <el-form-item v-if="form.s3_enabled && form.s3_upload_mode === 'us3'" label="us3命令路径">
          <el-input v-model="form.us3_cli_path" placeholder="/data/us3cli-linux64" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onCreatePolicy">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="notifyDialogVisible" :title="notifyEditingId ? '编辑通知地址' : '新增通知地址'" width="560px">
      <el-form :model="notifyForm" label-width="110px">
        <el-form-item label="名称"><el-input v-model="notifyForm.name" /></el-form-item>
        <el-form-item label="渠道">
          <el-select v-model="notifyForm.channel" style="width: 100%">
            <el-option label="企微Webhook" value="wecom" />
            <el-option label="邮件" value="email" />
          </el-select>
        </el-form-item>
        <el-form-item :label="notifyForm.channel === 'wecom' ? 'Webhook地址' : '邮箱地址'">
          <el-input
            v-model="notifyForm.address"
            :placeholder="notifyForm.channel === 'wecom' ? 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...' : 'ops@example.com'"
          />
        </el-form-item>
        <el-form-item label="启用"><el-switch v-model="notifyForm.enabled" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="notifyDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="notifySaving" @click="saveNotifyTarget">保存</el-button>
      </template>
    </el-dialog>

    <!-- 备份工具配置管理对话框 -->
    <el-dialog v-model="toolConfigDialogVisible" title="备份工具配置" width="900px">
      <div style="margin-bottom: 15px">
        <el-button type="primary" size="small" @click="openToolConfigCreate">新增工具配置</el-button>
      </div>

      <el-table :data="backupToolConfigs" stripe>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="名称" min-width="120" />
        <el-table-column label="数据库类型" width="100">
          <template #default="scope">
            {{ scope.row.db_type === 'mysql' ? 'MySQL' : 'MongoDB' }}
          </template>
        </el-table-column>
        <el-table-column prop="tool_path" label="工具路径" min-width="200" />
        <el-table-column prop="description" label="描述" min-width="150" />
        <el-table-column label="状态" width="80">
          <template #default="scope">
            <el-tag v-if="scope.row.enabled" type="success">启用</el-tag>
            <el-tag v-else type="info">停用</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180">
          <template #default="scope">
            <el-button link type="primary" size="small" @click="verifyToolConfig(scope.row)">验证</el-button>
            <el-button link type="primary" size="small" @click="openToolConfigEdit(scope.row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="deleteToolConfig(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <template #footer>
        <el-button @click="toolConfigDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 新增/编辑备份工具配置对话框 -->
    <el-dialog v-model="toolConfigFormVisible" :title="toolConfigEditingId ? '编辑工具配置' : '新增工具配置'" width="560px">
      <el-form :model="toolConfigForm" label-width="110px">
        <el-form-item label="名称"><el-input v-model="toolConfigForm.name" placeholder="如: 生产环境MySQL" /></el-form-item>
        <el-form-item label="数据库类型">
          <el-select v-model="toolConfigForm.db_type" style="width: 100%">
            <el-option label="MySQL" value="mysql" />
            <el-option label="MongoDB" value="mongodb" />
          </el-select>
        </el-form-item>
        <el-form-item label="工具路径">
          <el-input v-model="toolConfigForm.tool_path" placeholder="/usr/bin/mysqldump 或 /usr/local/bin/mongodump" />
        </el-form-item>
        <el-form-item label="描述"><el-input v-model="toolConfigForm.description" type="textarea" :rows="2" /></el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="toolConfigForm.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="toolConfigFormVisible = false">取消</el-button>
        <el-button type="primary" :loading="toolConfigSaving" @click="saveToolConfig">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, inject, onMounted, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  createBackupPolicy,
  createBackupToolConfig,
  createNotifyTarget,
  deleteBackupPolicy,
  deleteBackupToolConfig,
  deleteNotifyTarget,
  listBackupAgents,
  listBackupLogs,
  listBackupPoliciesByType,
  listBackupToolConfigs,
  listManagedInstances,
  listNotifyTargets,
  listS3StorageConfigs,
  runBackup,
  updateBackupPolicy,
  updateBackupToolConfig,
  updateNotifyTarget,
  verifyBackupToolConfig,
} from "../api/modules/backups";

const mysqlPolicies = ref([]);
const mongoPolicies = ref([]);
const dialogVisible = ref(false);
const saving = ref(false);

const mysqlPage = reactive({
  current: 1,
  size: 10,
  total: 0
});

const mongoPage = reactive({
  current: 1,
  size: 10,
  total: 0
});

const managedInstancesMap = reactive({
  mysql: [],
  mongodb: [],
});

const notifyTargets = ref([]);
const notifyDialogVisible = ref(false);
const notifySaving = ref(false);
const notifyEditingId = ref(null);

const s3StorageConfigs = ref([]);

const agents = ref([]);

// 备份工具配置相关
const backupToolConfigs = ref([]);
const toolConfigDialogVisible = ref(false);
const toolConfigFormVisible = ref(false);
const toolConfigSaving = ref(false);
const toolConfigEditingId = ref(null);
const toolConfigForm = reactive({
  name: "",
  db_type: "mysql",
  tool_path: "",
  description: "",
  enabled: true,
});

const form = reactive({
  name: "",
  db_type: "mysql",
  target_type: "instance",
  target_id: null,
  backup_type: "full",
  tool_name: "mysqldump",
  backup_tool_config_id: null,
  cron_expr: "0 2 * * *",
  storage_path: "/tmp",
  retain_days: 7,
  compress: true,
  enabled: true,
  notify_on_failure: true,
  notify_channels: ["wecom", "email"],
  notify_target_ids: [],
  s3_enabled: false,
  s3_storage_config_id: null,
  s3_upload_mode: "native",
  us3_cli_path: "/data/us3cli-linux64",
});

const notifyForm = reactive({
  name: "",
  channel: "wecom",
  address: "",
  enabled: true,
});

const currentManagedInstances = computed(() => managedInstancesMap[form.db_type] || []);
const enabledNotifyTargets = computed(() => notifyTargets.value.filter((item) => item.enabled));
const enabledS3StorageConfigs = computed(() => s3StorageConfigs.value.filter((item) => item.enabled));
const enabledAgents = computed(() => agents.value.filter((item) => item.enabled));
const currentDbTypeTools = computed(() => {
  const toolRows = backupToolConfigs.value.filter((item) => item.db_type === form.db_type && item.enabled);
  if (form.backup_agent_id) {
    return toolRows.filter((item) => item.backup_agent_id === form.backup_agent_id);
  }
  return toolRows.filter((item) => !item.backup_agent_id);
});

const mysqlPoliciesData = computed(() => {
  const start = (mysqlPage.current - 1) * mysqlPage.size;
  const end = start + mysqlPage.size;
  return mysqlPolicies.value.slice(start, end);
});

const mongoPoliciesData = computed(() => {
  const start = (mongoPage.current - 1) * mongoPage.size;
  const end = start + mongoPage.size;
  return mongoPolicies.value.slice(start, end);
});

function resetPolicyForm() {
  form.name = "";
  form.db_type = "mysql";
  form.target_type = "instance";
  form.target_id = null;
  form.backup_type = "full";
  form.tool_name = "mysqldump";
  form.backup_tool_config_id = null;
  form.cron_expr = "0 2 * * *";
  form.storage_path = "/tmp";
  form.retain_days = 7;
  form.compress = true;
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

function resetNotifyForm() {
  notifyForm.name = "";
  notifyForm.channel = "wecom";
  notifyForm.address = "";
  notifyForm.enabled = true;
}

function ensureTargetSelected() {
  const options = currentManagedInstances.value;
  if (!options.length) {
    form.target_id = null;
    return;
  }
  if (!options.some((item) => item.id === form.target_id)) {
    form.target_id = options[0].id;
  }
}

function formatNotifyTarget(target) {
  const channel = target.channel === "wecom" ? "企微" : "邮件";
  return `[${channel}] ${target.name} - ${target.address}`;
}

function formatS3StorageConfig(config) {
  return `${config.name} (${config.bucket}${config.prefix ? '/' + config.prefix : ''})`;
}

function getInstanceLabel(dbType, targetId) {
  const rows = managedInstancesMap[dbType] || [];
  const row = rows.find((item) => item.id === targetId);
  return row?.label || `实例ID: ${targetId}`;
}

async function loadManagedInstances(dbType) {
  try {
    const { data } = await listManagedInstances(dbType);
    managedInstancesMap[dbType] = data.data || [];
    if (form.db_type === dbType) {
      ensureTargetSelected();
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.message || `加载 ${dbType} 实例失败`);
  }
}

async function loadNotifyTargets() {
  try {
    const { data } = await listNotifyTargets();
    notifyTargets.value = data.data || [];
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载通知地址失败");
  }
}

async function loadS3StorageConfigs() {
  try {
    const { data } = await listS3StorageConfigs();
    s3StorageConfigs.value = data.data || [];
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载S3存储配置失败");
  }
}

async function loadBackupToolConfigs() {
  try {
    const { data } = await listBackupToolConfigs();
    backupToolConfigs.value = data.data || [];
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载备份工具配置失败");
  }
}

async function loadAgents() {
  try {
    const { data } = await listBackupAgents();
    agents.value = data.data || [];
  } catch (error) {
    console.error("加载 Agent 列表失败", error);
  }
}

async function openToolConfigDialog() {
  toolConfigDialogVisible.value = true;
  await loadBackupToolConfigs();
}

const router = useRouter();

function openAgentDialog() {
  router.push("/config/agents");
}

function openToolConfigCreate() {
  toolConfigEditingId.value = null;
  toolConfigForm.name = "";
  toolConfigForm.db_type = "mysql";
  toolConfigForm.tool_path = "";
  toolConfigForm.description = "";
  toolConfigForm.enabled = true;
  toolConfigFormVisible.value = true;
}

function openToolConfigEdit(row) {
  toolConfigEditingId.value = row.id;
  toolConfigForm.name = row.name;
  toolConfigForm.db_type = row.db_type;
  toolConfigForm.tool_path = row.tool_path;
  toolConfigForm.description = row.description || "";
  toolConfigForm.enabled = !!row.enabled;
  toolConfigFormVisible.value = true;
}

async function saveToolConfig() {
  if (!toolConfigForm.name || !toolConfigForm.tool_path) {
    ElMessage.warning("请填写名称和工具路径");
    return;
  }

  toolConfigSaving.value = true;
  try {
    const payload = {
      name: toolConfigForm.name,
      db_type: toolConfigForm.db_type,
      tool_path: toolConfigForm.tool_path,
      description: toolConfigForm.description,
      enabled: toolConfigForm.enabled,
    };

    if (toolConfigEditingId.value) {
      await updateBackupToolConfig(toolConfigEditingId.value, payload);
      ElMessage.success("工具配置已更新");
    } else {
      await createBackupToolConfig(payload);
      ElMessage.success("工具配置已创建");
    }

    toolConfigFormVisible.value = false;
    await loadBackupToolConfigs();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "保存工具配置失败");
  } finally {
    toolConfigSaving.value = false;
  }
}

async function deleteToolConfig(row) {
  try {
    await ElMessageBox.confirm(`确认删除工具配置 ${row.name} 吗？`, "提示", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await deleteBackupToolConfig(row.id);
    ElMessage.success("工具配置已删除");
    await loadBackupToolConfigs();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.message || "删除工具配置失败");
    }
  }
}

async function verifyToolConfig(row) {
  try {
    const { data } = await verifyBackupToolConfig(row.id);
    if (data.data?.available) {
      ElMessage.success(`验证通过，版本: ${data.data.version || 'unknown'}`);
    } else {
      ElMessage.error("工具验证失败");
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "验证工具失败");
  }
}

function onBackupToolConfigChange(configId) {
  if (configId) {
    const tool = backupToolConfigs.value.find(t => t.id === configId);
    if (tool) {
      const baseName = tool.db_type === 'mysql' ? 'mysqldump' : 'mongodump';
      form.tool_name = baseName;
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

async function loadPolicies() {
  try {
    const [mysqlRes, mongoRes] = await Promise.all([
      listBackupPoliciesByType("mysql"),
      listBackupPoliciesByType("mongodb"),
    ]);
    mysqlPolicies.value = mysqlRes.data.data || [];
    mongoPolicies.value = mongoRes.data.data || [];
    
    // 更新分页总数据
    mysqlPage.total = mysqlPolicies.value.length;
    mongoPage.total = mongoPolicies.value.length;
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载策略失败");
  }
}

async function run(policy, dryRun) {
  try {
    const { data } = await runBackup(policy.id, dryRun);
    ElMessage.success(data.message || "执行完成");
    await loadLogs(policy.id);
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "执行失败");
  }
}

async function togglePolicy(policy) {
  try {
    await updateBackupPolicy(policy.id, { enabled: !policy.enabled });
    ElMessage.success("状态已更新");
    await loadPolicies();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "更新失败");
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

function handleMongoSizeChange(size) {
  mongoPage.size = size;
  mongoPage.current = 1;
}

function handleMongoCurrentChange(current) {
  mongoPage.current = current;
}

async function onDbTypeChange(value) {
  form.tool_name = value === "mysql" ? "mysqldump" : "mongodump";
  await loadManagedInstances(value);
  ensureTargetSelected();
}

async function openCreatePolicyDialog() {
  resetPolicyForm();
  await onDbTypeChange(form.db_type);
  dialogVisible.value = true;
}

async function onCreatePolicy() {
  if (!form.target_id) {
    ElMessage.warning("请选择备份实例");
    return;
  }

  saving.value = true;
  try {
    await createBackupPolicy({
      name: form.name || `${form.db_type}-policy-${Date.now()}`,
      target_type: form.target_type,
      target_id: form.target_id,
      db_type: form.db_type,
      backup_type: form.backup_type,
      tool_name: form.tool_name,
      backup_tool_config_id: form.backup_tool_config_id || null,
      cron_expr: form.cron_expr,
      storage_path: form.storage_path,
      retain_days: form.retain_days,
      compress: form.compress,
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
      },
    });
    ElMessage.success("策略已创建");
    dialogVisible.value = false;
    await loadPolicies();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "创建策略失败");
  } finally {
    saving.value = false;
  }
}

function openNotifyCreate() {
  notifyEditingId.value = null;
  resetNotifyForm();
  notifyDialogVisible.value = true;
}

function openNotifyEdit(row) {
  notifyEditingId.value = row.id;
  notifyForm.name = row.name;
  notifyForm.channel = row.channel;
  notifyForm.address = row.address;
  notifyForm.enabled = !!row.enabled;
  notifyDialogVisible.value = true;
}

async function saveNotifyTarget() {
  if (!notifyForm.name || !notifyForm.address) {
    ElMessage.warning("请填写名称和地址");
    return;
  }

  notifySaving.value = true;
  try {
    const payload = {
      name: notifyForm.name,
      channel: notifyForm.channel,
      address: notifyForm.address,
      enabled: notifyForm.enabled,
    };

    if (notifyEditingId.value) {
      await updateNotifyTarget(notifyEditingId.value, payload);
      ElMessage.success("通知地址已更新");
    } else {
      await createNotifyTarget(payload);
      ElMessage.success("通知地址已创建");
    }

    notifyDialogVisible.value = false;
    await loadNotifyTargets();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "保存通知地址失败");
  } finally {
    notifySaving.value = false;
  }
}

async function removeNotifyTarget(row) {
  try {
    await ElMessageBox.confirm(`确认删除通知地址 ${row.name} 吗？`, "提示", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await deleteNotifyTarget(row.id);
    ElMessage.success("通知地址已删除");
    await loadNotifyTargets();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.message || "删除通知地址失败");
    }
  }
}

async function refreshAll() {
  await Promise.all([
    loadPolicies(),
    loadNotifyTargets(),
    loadS3StorageConfigs(),
    loadBackupToolConfigs(),
    loadAgents(),
    loadManagedInstances("mysql"),
    loadManagedInstances("mongodb"),
  ]);
}

onMounted(refreshAll);
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 20px;
  padding: 20px;
}

.policy-card {
  margin-bottom: 20px;
}

.pagination-container {
  margin-top: 15px;
  display: flex;
  justify-content: flex-end;
}

.sub-title {
  margin-bottom: 10px;
  font-size: 16px;
  font-weight: 600;
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

.hint-text {
  margin-top: 4px;
  color: #8a96a8;
  font-size: 12px;
  line-height: 1.4;
}
</style>
