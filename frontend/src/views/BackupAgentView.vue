<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>Agent管理</span>
          <div class="header-actions">
            <el-button type="primary" @click="openCreateDialog">新增 Agent</el-button>
            <el-button @click="loadAgents">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table :data="agents" stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="名称" min-width="150" />
        <el-table-column prop="url" label="URL" min-width="220" />
        <el-table-column prop="description" label="描述" min-width="180" />
        <el-table-column label="默认" width="80">
          <template #default="scope">
            <el-tag v-if="scope.row.is_default" type="success">是</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="scope">
            <el-tag v-if="scope.row.enabled" type="success">启用</el-tag>
            <el-tag v-else type="info">停用</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="健康状态" width="120">
          <template #default="scope">
            <el-tag v-if="healthStatus[scope.row.id] === 'healthy'" type="success">正常</el-tag>
            <el-tag v-else-if="healthStatus[scope.row.id] === 'unreachable'" type="danger">不可达</el-tag>
            <el-tag v-else-if="healthStatus[scope.row.id] === 'disabled'" type="info">已禁用</el-tag>
            <span v-else class="health-loading">检查中...</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="scope">
            <el-button link type="primary" size="small" @click="testAgent(scope.row)">测试</el-button>
            <el-button link type="primary" size="small" @click="openEditDialog(scope.row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="deleteAgent(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新增/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑 Agent' : '新增 Agent'" width="560px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如：DC1 机房 Agent" />
        </el-form-item>
        <el-form-item label="URL" required>
          <el-input v-model="form.url" placeholder="http://192.168.1.100:5001" />
          <div class="hint-text">Agent 服务的 HTTP 地址</div>
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="form.api_key" placeholder="Agent 验证密钥" />
          <div class="hint-text">与 Agent 服务配置的 AGENT_API_KEY 一致</div>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="可选描述信息" />
        </el-form-item>
        <el-form-item label="设为默认">
          <el-switch v-model="form.is_default" />
          <div class="hint-text">设为默认 Agent，供需要 Agent 能力的功能优先使用</div>
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveAgent">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  createBackupAgent,
  deleteBackupAgent,
  getBackupAgentHealth,
  listBackupAgents,
  testBackupAgent,
  updateBackupAgent,
} from "../api/modules/backups";

const agents = ref([]);
const dialogVisible = ref(false);
const saving = ref(false);
const editingId = ref(null);
const healthStatus = reactive({});

const form = reactive({
  name: "",
  url: "",
  api_key: "",
  description: "",
  is_default: false,
  enabled: true,
});

async function loadAgents() {
  try {
    const { data } = await listBackupAgents();
    agents.value = data.data || [];
    // Load health status for each agent
    agents.value.forEach(async (agent) => {
      if (agent.enabled) {
        await checkHealth(agent);
      } else {
        healthStatus[agent.id] = "disabled";
      }
    });
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载 Agent 列表失败");
  }
}

async function checkHealth(agent) {
  try {
    const { data } = await getBackupAgentHealth(agent.id);
    const status = data.data?.status || "unknown";
    healthStatus[agent.id] = status === "healthy" ? "healthy" : status === "unreachable" ? "unreachable" : "unknown";
  } catch (error) {
    healthStatus[agent.id] = "unreachable";
  }
}

async function testAgent(agent) {
  try {
    ElMessage.info("正在测试连接...");
    const { data } = await testBackupAgent(agent.id);
    if (data.data?.ok) {
      ElMessage.success("Agent 连接成功");
    } else {
      ElMessage.warning(data.data?.message || "Agent 连接失败");
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "测试连接失败");
  }
}

function openCreateDialog() {
  editingId.value = null;
  form.name = "";
  form.url = "";
  form.api_key = "";
  form.description = "";
  form.is_default = false;
  form.enabled = true;
  dialogVisible.value = true;
}

function openEditDialog(agent) {
  editingId.value = agent.id;
  form.name = agent.name;
  form.url = agent.url;
  form.api_key = agent.api_key || "";
  form.description = agent.description || "";
  form.is_default = !!agent.is_default;
  form.enabled = !!agent.enabled;
  dialogVisible.value = true;
}

async function saveAgent() {
  if (!form.name || !form.url) {
    ElMessage.warning("请填写名称和 URL");
    return;
  }

  if (!form.url.startsWith("http://") && !form.url.startsWith("https://")) {
    ElMessage.warning("URL 必须以 http:// 或 https:// 开头");
    return;
  }

  saving.value = true;
  try {
    const payload = {
      name: form.name,
      url: form.url,
      api_key: form.api_key,
      description: form.description,
      is_default: form.is_default,
      enabled: form.enabled,
    };

    if (editingId.value) {
      await updateBackupAgent(editingId.value, payload);
      ElMessage.success("Agent 已更新");
    } else {
      await createBackupAgent(payload);
      ElMessage.success("Agent 已创建");
    }

    dialogVisible.value = false;
    await loadAgents();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "保存失败");
  } finally {
    saving.value = false;
  }
}

async function deleteAgent(agent) {
  try {
    await ElMessageBox.confirm(`确认删除 Agent ${agent.name} 吗？`, "提示", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await deleteBackupAgent(agent.id);
    ElMessage.success("Agent 已删除");
    await loadAgents();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.message || "删除失败");
    }
  }
}

onMounted(loadAgents);
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

.hint-text {
  margin-top: 4px;
  color: #8a96a8;
  font-size: 12px;
  line-height: 1.4;
}

.health-loading {
  font-size: 12px;
  color: #909399;
}
</style>
