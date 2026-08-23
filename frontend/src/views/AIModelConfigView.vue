<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>AI 模型管理</span>
          <el-button type="primary" @click="openCreateDialog">新增配置</el-button>
        </div>
      </template>

      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column prop="name" label="配置名称" width="180" />
        <el-table-column prop="api_url" label="API URL" min-width="260" show-overflow-tooltip />
        <el-table-column prop="model_name" label="模型名称" width="180" />
        <el-table-column label="默认" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_default ? 'success' : 'info'">{{ row.is_default ? '是' : '否' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="80">
          <template #default="{ row }">
            <el-switch v-model="row.enabled" @change="toggleEnabled(row)" />
          </template>
        </el-table-column>
        <el-table-column label="Thinking" width="105">
          <template #default="{ row }">
            <el-switch v-model="row.thinking_enabled" @change="toggleThinking(row)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240">
          <template #default="{ row }">
            <el-button link type="success" :loading="testingId === row.id" @click="testConfig(row)">检测</el-button>
            <el-button link type="primary" @click="openEditDialog(row)">编辑</el-button>
            <el-button link type="danger" @click="removeConfig(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="isEditing ? '编辑配置' : '新增配置'" width="600px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="配置名称" required>
          <el-input v-model="form.name" placeholder="如: OpenAI-GPT4" />
        </el-form-item>
        <el-form-item label="API URL" required>
          <el-input v-model="form.api_url" placeholder="OpenAI 兼容接口地址" />
        </el-form-item>
        <el-form-item label="API Key" required>
          <el-input v-model="form.api_key" type="password" show-password placeholder="API密钥" />
        </el-form-item>
        <el-form-item label="模型名称" required>
          <el-input v-model="form.model_name" placeholder="如: gpt-3.5-turbo" />
        </el-form-item>
        <el-form-item label="设为默认">
          <el-checkbox v-model="form.is_default" />
        </el-form-item>
        <el-form-item label="启用 Thinking">
          <el-switch v-model="form.thinking_enabled" />
          <span class="form-tip">仅对支持 enable_thinking 的 OpenAI 兼容模型生效</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveConfig">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { listAIConfigs, createAIConfig, updateAIConfig, deleteAIConfig, testAIConfig } from "../api/modules/ai";
import { useTabActivationRefresh } from "../composables/useTabActivationRefresh";

const rows = ref([]);
const loading = ref(false);
const dialogVisible = ref(false);
const isEditing = ref(false);
const saving = ref(false);
const testingId = ref(null);

const form = ref({
  id: null,
  name: "",
  api_url: "",
  api_key: "",
  model_name: "",
  is_default: false,
  thinking_enabled: false,
});

async function loadConfigs() {
  loading.value = true;
  try {
    const { data } = await listAIConfigs();
    rows.value = data?.data || [];
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载配置失败");
  } finally {
    loading.value = false;
  }
}

function openCreateDialog() {
  isEditing.value = false;
  form.value = { id: null, name: "", api_url: "", api_key: "", model_name: "", is_default: false, thinking_enabled: false };
  dialogVisible.value = true;
}

function openEditDialog(row) {
  isEditing.value = true;
  form.value = { ...row, api_key: "******" };
  dialogVisible.value = true;
}

async function saveConfig() {
  if (!form.value.name || !form.value.api_url || !form.value.api_key || !form.value.model_name) {
    return ElMessage.warning("请填写必填项");
  }
  saving.value = true;
  try {
    if (isEditing.value) {
      await updateAIConfig(form.value.id, form.value);
      ElMessage.success("修改成功");
    } else {
      await createAIConfig(form.value);
      ElMessage.success("创建成功");
    }
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
    await updateAIConfig(row.id, { enabled: row.enabled });
    ElMessage.success(row.enabled ? "已启用" : "已禁用");
  } catch (error) {
    row.enabled = !row.enabled;
    ElMessage.error("操作失败");
  }
}

async function toggleThinking(row) {
  try {
    await updateAIConfig(row.id, { thinking_enabled: row.thinking_enabled });
    ElMessage.success(row.thinking_enabled ? "Thinking 已启用" : "Thinking 已关闭");
  } catch (error) {
    row.thinking_enabled = !row.thinking_enabled;
    ElMessage.error(error.response?.data?.message || "操作失败");
  }
}

async function testConfig(row) {
  testingId.value = row.id;
  try {
    const { data } = await testAIConfig(row.id);
    ElMessage.success(data.message || `检测成功：${data.data?.reply || "模型可用"}`);
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "模型检测失败");
  } finally {
    testingId.value = null;
  }
}

async function removeConfig(row) {
  try {
    await ElMessageBox.confirm(`确定删除配置 "${row.name}" 吗?`, "提示", { type: "warning" });
    await deleteAIConfig(row.id);
    ElMessage.success("删除成功");
    await loadConfigs();
  } catch (error) {
    if (error !== "cancel") ElMessage.error("删除失败");
  }
}

onMounted(loadConfigs);
useTabActivationRefresh(loadConfigs);
</script>

<style scoped>
.page { padding: 20px; }
.header-row { display: flex; justify-content: space-between; align-items: center; }
.form-tip { margin-left: 10px; color: #909399; font-size: 12px; }
</style>
