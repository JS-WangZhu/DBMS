<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>JumpServer管理</span>
          <div class="header-actions">
            <el-button @click="downloadMappingTemplate">下载映射模板</el-button>
            <el-button type="success" @click="openImportDialog">导入实例映射</el-button>
            <el-button type="primary" @click="openCreateDialog">新增配置</el-button>
            <el-button @click="loadConfigs">刷新</el-button>
          </div>
        </div>
      </template>

      <el-alert
        class="page-tip"
        type="info"
        :closable="false"
        title="数据库实例通过此处配置的地址跳转到 JumpServer；实际登录和资产访问权限仍由 JumpServer 校验。"
      />

      <el-table :data="rows" v-loading="loading" stripe border>
        <el-table-column prop="name" label="配置名称" min-width="160" />
        <el-table-column prop="base_url" label="JumpServer地址" min-width="260" show-overflow-tooltip />
        <el-table-column prop="web_url_template" label="资产访问模板" min-width="320" show-overflow-tooltip />
        <el-table-column label="连接测试" width="180">
          <template #default="{ row }">
            <el-tag v-if="row.last_test_status" :type="row.last_test_status === 'success' ? 'success' : 'danger'">
              {{ row.last_test_status === "success" ? "成功" : "失败" }}
            </el-tag>
            <span v-else>-</span>
            <span v-if="row.last_test_at" class="test-time">{{ formatBeijingTime(row.last_test_at) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="SSL校验" width="90">
          <template #default="{ row }">{{ row.verify_ssl ? "开启" : "关闭" }}</template>
        </el-table-column>
        <el-table-column label="启用" width="80">
          <template #default="{ row }">
            <el-switch v-model="row.enabled" @change="toggleEnabled(row)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="210" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" :loading="testingId === row.id" @click="testConnection(row)">测试</el-button>
            <el-button link type="primary" @click="openEditDialog(row)">编辑</el-button>
            <el-button link type="danger" @click="removeConfig(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="importDialogVisible" title="批量导入实例与 JumpServer 映射" width="760px">
      <el-alert
        type="info"
        :closable="false"
        title="建议先下载模板。实例 ID 是匹配主键；数据库类型、实例名、地址和端口用于防止误绑定。校验失败时整批不会写入。"
      />
      <el-upload
        ref="mappingUploadRef"
        class="mapping-upload"
        drag
        accept=".csv,text/csv"
        :auto-upload="false"
        :limit="1"
        :on-change="onMappingFileChange"
        :on-remove="onMappingFileRemove"
        :on-exceed="onMappingFileExceed"
      >
        <div class="upload-title">将 CSV 文件拖到此处，或点击选择文件</div>
        <template #tip>
          <div class="el-upload__tip">UTF-8 编码，最大 2MB、5000 行。</div>
        </template>
      </el-upload>
      <div class="csv-fields">
        CSV 列：<code>instance_id</code>、<code>db_type</code>、<code>instance_name</code>、<code>host</code>、<code>port</code>、
        <code>jumpserver_config_id</code>、<code>jumpserver_config_name</code>、<code>jumpserver_asset_id</code>。
        JumpServer 配置 ID 和名称至少填写一个。
      </div>
      <el-alert
        v-if="importErrors.length"
        class="import-error-alert"
        type="error"
        :closable="false"
        :title="`校验失败，共 ${importErrorCount} 条错误，未导入任何映射`"
      />
      <el-table v-if="importErrors.length" :data="importErrors" size="small" max-height="240" border>
        <el-table-column prop="row" label="CSV行号" width="100" />
        <el-table-column prop="message" label="错误原因" show-overflow-tooltip />
      </el-table>
      <template #footer>
        <el-button @click="importDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="importing" :disabled="!mappingFile" @click="submitMappingImport">开始导入</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="dialogVisible" :title="isEditing ? '编辑 JumpServer' : '新增 JumpServer'" width="720px">
      <el-form :model="form" label-width="130px">
        <el-form-item label="配置名称" required>
          <el-input v-model.trim="form.name" placeholder="例如：生产 JumpServer" />
        </el-form-item>
        <el-form-item label="JumpServer地址" required>
          <el-input v-model.trim="form.base_url" placeholder="https://jumpserver.example.com" />
        </el-form-item>
        <el-form-item label="资产访问模板" required>
          <el-input v-model.trim="form.web_url_template" type="textarea" :rows="3" />
          <div class="form-tip">
            必须包含 <code>{base_url}</code> 和 <code>{asset_id}</code>。不同 JumpServer 版本的 Luna 路径不一致时，可在这里调整。
          </div>
        </el-form-item>
        <el-form-item label="校验SSL证书">
          <el-switch v-model="form.verify_ssl" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveConfig">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  createJumpServerConfig,
  deleteJumpServerConfig,
  downloadJumpServerMappingTemplate,
  importJumpServerMappings,
  listJumpServerConfigs,
  testJumpServerConfig,
  updateJumpServerConfig,
} from "../api/modules/jumpserver";
import { formatBeijingTime } from "../utils/time";
import { useTabActivationRefresh } from "../composables/useTabActivationRefresh";

const DEFAULT_TEMPLATE = "{base_url}/luna/?asset={asset_id}";
const rows = ref([]);
const loading = ref(false);
const saving = ref(false);
const testingId = ref(null);
const dialogVisible = ref(false);
const importDialogVisible = ref(false);
const isEditing = ref(false);
const form = ref({});
const mappingUploadRef = ref(null);
const mappingFile = ref(null);
const importing = ref(false);
const importErrors = ref([]);
const importErrorCount = ref(0);

function emptyForm() {
  return { id: null, name: "", base_url: "", web_url_template: DEFAULT_TEMPLATE, verify_ssl: true, enabled: true };
}

async function loadConfigs() {
  loading.value = true;
  try {
    const { data } = await listJumpServerConfigs();
    rows.value = data?.data || [];
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载 JumpServer 配置失败");
  } finally {
    loading.value = false;
  }
}

function openCreateDialog() {
  isEditing.value = false;
  form.value = emptyForm();
  dialogVisible.value = true;
}

async function downloadMappingTemplate() {
  try {
    const response = await downloadJumpServerMappingTemplate();
    const url = URL.createObjectURL(response.data);
    const link = document.createElement("a");
    link.href = url;
    link.download = "jumpserver-instance-mapping.csv";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "下载映射模板失败");
  }
}

function openImportDialog() {
  mappingFile.value = null;
  importErrors.value = [];
  importErrorCount.value = 0;
  mappingUploadRef.value?.clearFiles();
  importDialogVisible.value = true;
}

function onMappingFileChange(uploadFile) {
  mappingFile.value = uploadFile.raw || null;
  importErrors.value = [];
  importErrorCount.value = 0;
}

function onMappingFileRemove() {
  mappingFile.value = null;
}

function onMappingFileExceed(files) {
  mappingUploadRef.value?.clearFiles();
  const file = files[0];
  if (file) {
    mappingUploadRef.value?.handleStart(file);
    mappingFile.value = file;
  }
}

async function submitMappingImport() {
  if (!mappingFile.value) return;
  importing.value = true;
  importErrors.value = [];
  importErrorCount.value = 0;
  try {
    const { data } = await importJumpServerMappings(mappingFile.value);
    const count = Number(data?.data?.imported_count || 0);
    const skipped = Number(data?.data?.skipped_count || 0);
    ElMessage.success(`成功导入 ${count} 条实例映射${skipped ? `，忽略 ${skipped} 行未填写资产 ID 的实例` : ""}`);
    importDialogVisible.value = false;
    mappingUploadRef.value?.clearFiles();
  } catch (error) {
    const result = error.response?.data?.data || {};
    importErrors.value = Array.isArray(result.errors) ? result.errors : [];
    importErrorCount.value = Number(result.error_count || importErrors.value.length);
    if (!importErrors.value.length) ElMessage.error(error.response?.data?.message || "导入实例映射失败");
  } finally {
    importing.value = false;
  }
}

function openEditDialog(row) {
  isEditing.value = true;
  form.value = { ...row };
  dialogVisible.value = true;
}

async function saveConfig() {
  if (!form.value.name || !form.value.base_url || !form.value.web_url_template) {
    ElMessage.warning("请填写配置名称、JumpServer 地址和资产访问模板");
    return;
  }
  saving.value = true;
  try {
    if (isEditing.value) await updateJumpServerConfig(form.value.id, form.value);
    else await createJumpServerConfig(form.value);
    ElMessage.success("保存成功");
    dialogVisible.value = false;
    await loadConfigs();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "保存失败");
  } finally {
    saving.value = false;
  }
}

async function toggleEnabled(row) {
  try {
    await updateJumpServerConfig(row.id, { enabled: row.enabled });
    ElMessage.success(row.enabled ? "已启用" : "已停用");
  } catch (error) {
    row.enabled = !row.enabled;
    ElMessage.error(error.response?.data?.message || "更新失败");
  }
}

async function testConnection(row) {
  testingId.value = row.id;
  try {
    await testJumpServerConfig(row.id);
    ElMessage.success("JumpServer 连接成功");
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "JumpServer 连接失败");
  } finally {
    testingId.value = null;
    await loadConfigs();
  }
}

async function removeConfig(row) {
  try {
    await ElMessageBox.confirm(`确定删除 JumpServer 配置“${row.name}”吗？`, "提示", { type: "warning" });
    await deleteJumpServerConfig(row.id);
    ElMessage.success("删除成功");
    await loadConfigs();
  } catch (error) {
    if (error !== "cancel") ElMessage.error(error.response?.data?.message || "删除失败");
  }
}

onMounted(loadConfigs);
useTabActivationRefresh(loadConfigs);
</script>

<style scoped>
.page { padding: 20px; }
.header-row { display: flex; align-items: center; justify-content: space-between; }
.header-actions { display: flex; gap: 10px; }
.page-tip { margin-bottom: 16px; }
.form-tip { margin-top: 6px; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.6; }
.test-time { margin-left: 8px; color: var(--el-text-color-secondary); font-size: 12px; }
.mapping-upload { margin-top: 18px; }
.upload-title { color: var(--el-text-color-regular); }
.csv-fields { margin: 14px 0; color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.7; }
.import-error-alert { margin-bottom: 10px; }
</style>
