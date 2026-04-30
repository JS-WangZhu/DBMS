<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>备份工具管理</span>
          <div class="header-actions">
            <el-button type="primary" @click="openCreateDialog">新增工具配置</el-button>
            <el-button @click="loadToolConfigs">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table :data="toolConfigs" stripe>
        <el-table-column prop="id" label="ID" width="60" />
        <el-table-column prop="name" label="名称" min-width="150" />
        <el-table-column label="数据库类型" width="100">
          <template #default="scope">
            <el-tag v-if="scope.row.db_type === 'mysql'" type="primary">MySQL</el-tag>
            <el-tag v-else-if="scope.row.db_type === 'mongodb'" type="success">MongoDB</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="tool_path" label="工具路径" min-width="250" />
        <el-table-column label="执行地址" width="120">
          <template #default="scope">
            <el-tag v-if="scope.row.agent_name" type="warning">{{ scope.row.agent_name }}</el-tag>
            <el-tag v-else type="info">本地执行</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="180" />
        <el-table-column label="状态" width="80">
          <template #default="scope">
            <el-tag v-if="scope.row.enabled" type="success">启用</el-tag>
            <el-tag v-else type="info">停用</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180">
          <template #default="scope">
            <el-button link type="primary" size="small" @click="verifyToolConfig(scope.row)">验证</el-button>
            <el-button link type="primary" size="small" @click="openEditDialog(scope.row)">编辑</el-button>
            <el-button link type="danger" size="small" @click="deleteToolConfig(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑工具配置' : '新增工具配置'" width="560px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="如: 生产环境MySQL" />
        </el-form-item>
        <el-form-item label="数据库类型" required>
          <el-select v-model="form.db_type" style="width: 100%">
            <el-option label="MySQL" value="mysql" />
            <el-option label="MongoDB" value="mongodb" />
          </el-select>
        </el-form-item>
        <el-form-item label="工具路径" required>
          <el-input v-model="form.tool_path" :placeholder="toolPathPlaceholder" />
        </el-form-item>
        <el-form-item label="执行地址">
          <el-select v-model="form.backup_agent_id" style="width: 100%" placeholder="选择 Agent (留空则本地执行)" clearable>
            <el-option v-for="agent in backupAgents" :key="agent.id" :label="`${agent.name} (${agent.url})`" :value="agent.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveToolConfig">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  createBackupToolConfig,
  deleteBackupToolConfig,
  listBackupToolConfigs,
  listBackupAgents,
  updateBackupToolConfig,
  verifyBackupToolConfig,
  verifyToolOnAgent,
} from "../api/modules/backups";

const toolConfigs = ref([]);
const backupAgents = ref([]);
const dialogVisible = ref(false);
const saving = ref(false);
const editingId = ref(null);

const form = reactive({
  name: "",
  db_type: "mysql",
  tool_path: "",
  description: "",
  enabled: true,
  backup_agent_id: null,
});

const toolPathPlaceholder = computed(() => {
  if (form.db_type === "mongodb") {
    return "/usr/bin/mongodump";
  }
  return "/usr/bin/mysqldump";
});

async function loadBackupAgents() {
  try {
    const { data } = await listBackupAgents();
    backupAgents.value = data.data || [];
  } catch (error) {
    console.error("Failed to load backup agents:", error);
    backupAgents.value = [];
  }
}

async function loadToolConfigs() {
  try {
    const { data } = await listBackupToolConfigs();
    toolConfigs.value = data.data || [];
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载工具配置失败");
  }
}

function openCreateDialog() {
  editingId.value = null;
  form.name = "";
  form.db_type = "mysql";
  form.tool_path = "";
  form.description = "";
  form.enabled = true;
  form.backup_agent_id = null;
  dialogVisible.value = true;
}

function openEditDialog(row) {
  editingId.value = row.id;
  form.name = row.name;
  form.db_type = row.db_type;
  form.tool_path = row.tool_path;
  form.description = row.description || "";
  form.enabled = !!row.enabled;
  form.backup_agent_id = row.backup_agent_id || null;
  dialogVisible.value = true;
}

async function saveToolConfig() {
  if (!form.name || !form.tool_path) {
    ElMessage.warning("请填写名称和工具路径");
    return;
  }

  saving.value = true;
  try {
    const payload = {
      name: form.name,
      db_type: form.db_type,
      tool_path: form.tool_path,
      description: form.description,
      enabled: form.enabled,
      backup_agent_id: form.backup_agent_id,
    };

    if (editingId.value) {
      await updateBackupToolConfig(editingId.value, payload);
      ElMessage.success("工具配置已更新");
    } else {
      await createBackupToolConfig(payload);
      ElMessage.success("工具配置已创建");
    }

    dialogVisible.value = false;
    await loadToolConfigs();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "保存失败");
  } finally {
    saving.value = false;
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
    await loadToolConfigs();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.message || "删除失败");
    }
  }
}

async function verifyToolConfig(row) {
  try {
    if (row.backup_agent_id) {
      const { data } = await verifyToolOnAgent({
        backup_agent_id: row.backup_agent_id,
        tool_path: row.tool_path,
      });
      if (data.data?.available) {
        ElMessage.success(`验证通过，版本: ${data.data.version || 'unknown'}`);
      } else {
        ElMessage.error("工具验证失败: " + (data.data?.message || ""));
      }
    } else {
      const { data } = await verifyBackupToolConfig(row.id);
      if (data.data?.available) {
        ElMessage.success(`验证通过，版本: ${data.data.version || 'unknown'}`);
      } else {
        ElMessage.error("工具验证失败");
      }
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "验证工具失败");
  }
}

onMounted(() => {
  loadToolConfigs();
  loadBackupAgents();
});
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
</style>
