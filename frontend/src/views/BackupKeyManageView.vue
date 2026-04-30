<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>备份密钥管理</span>
          <div class="header-actions">
            <el-button type="primary" @click="openCreateDialog">新增/上传密钥</el-button>
            <el-button @click="loadKeys">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table :data="keys" stripe>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column prop="description" label="描述" min-width="180" />
        <el-table-column label="公钥" min-width="220" show-overflow-tooltip>
          <template #default="scope">
            <span class="key-preview">{{ previewKey(scope.row.public_key) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="私钥" width="100">
          <template #default="scope">
            <el-tag v-if="scope.row.has_private_key" type="success" size="small">已上传</el-tag>
            <el-tag v-else type="info" size="small">未上传</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280">
          <template #default="scope">
            <el-button link type="primary" size="small" @click="viewPublicKey(scope.row)">查看公钥</el-button>
            <el-button v-if="scope.row.has_private_key" link type="warning" size="small" @click="viewPrivateKey(scope.row)">查看私钥</el-button>
            <el-button link type="primary" size="small" @click="openEditDialog(scope.row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="deleteKey(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑密钥' : '新增密钥'" width="640px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如：prod-rsa-key" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="公钥" required>
          <el-input v-model="form.public_key" type="textarea" :rows="6" placeholder="粘贴公钥内容 (PEM 格式)" />
          <el-upload
            class="upload-box"
            action=""
            :auto-upload="false"
            :show-file-list="false"
            :before-upload="onPublicKeyFileSelect"
          >
            <el-button type="primary" plain size="small">导入公钥文件</el-button>
          </el-upload>
        </el-form-item>
        <el-form-item label="私钥">
          <el-input v-model="form.private_key" type="textarea" :rows="6" placeholder="粘贴私钥内容 (PEM 格式, 可选)" />
          <el-upload
            class="upload-box"
            action=""
            :auto-upload="false"
            :show-file-list="false"
            :before-upload="onPrivateKeyFileSelect"
          >
            <el-button type="primary" plain size="small">导入私钥文件</el-button>
          </el-upload>
          <div class="key-tip">
            <el-alert type="info" :closable="false" show-icon>
              <template #title>
                加密规则：AES-256-CBC (对称) + RSA (非对称)，32字节密钥
                <br />
                公钥格式支持 PKCS#8 或 PKCS#1 (OPENSSL 格式)
                <br />
                私钥用于解密备份文件，请妥善保管
                <br />
                上传私钥后会进行密钥对验证
              </template>
            </el-alert>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveKey">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="viewerVisible" :title="viewerTitle" width="720px">
      <el-input v-model="viewerText" type="textarea" :rows="12" readonly />
      <template #footer>
        <el-button @click="viewerVisible = false">关闭</el-button>
        <el-button type="primary" @click="copyText(viewerText)">复制</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { createBackupKey, deleteBackupKey, getBackupPrivateKey, listBackupKeys, updateBackupKey } from "../api/modules/backups";

const keys = ref([]);
const dialogVisible = ref(false);
const viewerVisible = ref(false);
const viewerText = ref("");
const viewerTitle = ref("密钥内容");
const saving = ref(false);
const editingId = ref(null);

const form = reactive({
  name: "",
  description: "",
  public_key: "",
  private_key: "",
});

function previewKey(value) {
  const text = String(value || "").trim();
  if (!text) return "-";
  if (text.length <= 48) return text;
  return `${text.slice(0, 24)}...${text.slice(-16)}`;
}

async function loadKeys() {
  try {
    const { data } = await listBackupKeys();
    keys.value = data.data || [];
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载密钥失败");
  }
}

function resetForm() {
  editingId.value = null;
  form.name = "";
  form.description = "";
  form.public_key = "";
  form.private_key = "";
}

function openCreateDialog() {
  resetForm();
  dialogVisible.value = true;
}

function openEditDialog(row) {
  editingId.value = row.id;
  form.name = row.name || "";
  form.description = row.description || "";
  form.public_key = row.public_key || "";
  dialogVisible.value = true;
}

function viewPublicKey(row) {
  viewerTitle.value = "公钥内容";
  viewerText.value = row.public_key || "";
  viewerVisible.value = true;
}

async function viewPrivateKey(row) {
  try {
    const { data } = await getBackupPrivateKey(row.id);
    viewerTitle.value = `私钥内容 - ${row.name || row.id}`;
    viewerText.value = data?.data?.private_key || "";
    viewerVisible.value = true;
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载私钥失败");
  }
}

async function copyText(text) {
  const value = text || "";
  try {
    if (navigator?.clipboard?.writeText && window.isSecureContext) {
      await navigator.clipboard.writeText(value);
      ElMessage.success("已复制");
      return;
    }
    const textarea = document.createElement("textarea");
    textarea.value = value;
    textarea.setAttribute("readonly", "readonly");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(textarea);
    if (!ok) {
      throw new Error("copy failed");
    }
    ElMessage.success("已复制");
  } catch (error) {
    ElMessage.error("复制失败，请手动复制");
  }
}

function copyKey(row) {
  copyText(row.public_key || "");
}

async function onPublicKeyFileSelect(file) {
  try {
    const content = await file.text();
    form.public_key = content.trim();
  } catch (error) {
    ElMessage.error("读取公钥文件失败");
  }
  return false;
}

async function onPrivateKeyFileSelect(file) {
  try {
    const content = await file.text();
    form.private_key = content.trim();
  } catch (error) {
    ElMessage.error("读取私钥文件失败");
  }
  return false;
}

async function saveKey() {
  if (!form.name || !form.public_key) {
    ElMessage.warning("请填写名称和公钥内容");
    return;
  }

  saving.value = true;
  try {
    const payload = {
      name: form.name,
      description: form.description,
      public_key: form.public_key,
      private_key: form.private_key || null,
    };
    if (editingId.value) {
      await updateBackupKey(editingId.value, payload);
      ElMessage.success("密钥已更新");
    } else {
      await createBackupKey(payload);
      ElMessage.success("密钥已创建");
    }
    dialogVisible.value = false;
    await loadKeys();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "保存失败");
  } finally {
    saving.value = false;
  }
}

async function deleteKey(row) {
  try {
    await ElMessageBox.confirm(`确认删除密钥 ${row.name} 吗？`, "提示", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await deleteBackupKey(row.id);
    ElMessage.success("密钥已删除");
    await loadKeys();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.message || "删除失败");
    }
  }
}

onMounted(loadKeys);
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

.upload-box {
  margin-top: 8px;
}

.key-preview {
  color: #475569;
}

.key-tip {
  margin-top: 12px;
}

.key-tip :deep(.el-alert__title) {
  line-height: 1.8;
}
</style>
