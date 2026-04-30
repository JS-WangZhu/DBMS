<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>高可用配置管理</span>
          <div class="header-actions">
            <el-button type="primary" @click="openCreateDialog">新增配置</el-button>
            <el-button @click="loadConfigs">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column prop="name" label="配置名称" min-width="180" />
        <el-table-column prop="script_path" label="脚本路径" min-width="320" show-overflow-tooltip />
        <el-table-column prop="command_template" label="命令参数模板" min-width="320" show-overflow-tooltip>
          <template #default="{ row }">
            {{ row.command_template || "-" }}
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="180" show-overflow-tooltip />
        <el-table-column label="企微通知" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            {{ formatNotifyTargets(row.notify_targets) }}
          </template>
        </el-table-column>
        <el-table-column label="默认" width="80">
          <template #default="{ row }">
            <el-tag :type="row.is_default ? 'success' : 'info'">{{ row.is_default ? "是" : "否" }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="80">
          <template #default="{ row }">
            <el-switch v-model="row.enabled" @change="toggleEnabled(row)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240">
          <template #default="{ row }">
            <el-button link type="primary" @click="verifyConfig(row)">验证</el-button>
            <el-button link type="primary" @click="openEditDialog(row)">编辑</el-button>
            <el-button link type="danger" @click="removeConfig(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="isEditing ? '编辑配置' : '新增配置'" width="760px">
      <el-form :model="form" label-width="120px">
        <el-form-item label="配置名称" required>
          <el-input v-model="form.name" placeholder="如: 公用DNS切换脚本" />
        </el-form-item>
        <el-form-item label="脚本路径" required>
          <el-input v-model="form.script_path" placeholder="如: C:\\scripts\\mysql-ha-switch.bat" />
        </el-form-item>
        <el-form-item label="命令参数模板">
          <el-input
            v-model="form.command_template"
            type="textarea"
            :rows="4"
            placeholder='如: --source ${source_address} --target ${target_address} --domain ${ha_domain} --info "${switch_info_json}"'
          />
          <div class="form-tip">
            仅配置脚本后的参数部分，脚本路径会自动作为第一个参数执行。可用变量：
            `${source_address}`、`${target_address}`、`${ha_domain}`、`${switch_mode}`、`${switch_label}`、
            `${cluster_name}`、`${business_line}`、`${environment}`、`${source_name}`、`${target_name}`、
            `${source_host}`、`${source_ip}`、`${source_port}`、`${target_host}`、`${target_ip}`、`${target_port}`、
            `${switch_info_json}`。
          </div>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="企微通知">
          <el-select
            v-model="form.notify_target_ids"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            clearable
            style="width: 100%"
            placeholder="选择通知地址"
          >
            <el-option
              v-for="item in notifyTargetOptions"
              :key="item.id"
              :label="notifyTargetLabel(item)"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="设为默认">
          <el-checkbox v-model="form.is_default" />
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
import { createHAConfig, deleteHAConfig, listHAConfigs, updateHAConfig, verifyHAConfig } from "../api/modules/ha";
import { listNotifyTargets } from "../api/modules/backups";

const rows = ref([]);
const loading = ref(false);
const dialogVisible = ref(false);
const isEditing = ref(false);
const saving = ref(false);
const notifyTargetOptions = ref([]);

const form = ref({
  id: null,
  name: "",
  script_path: "",
  command_template: "",
  description: "",
  notify_target_ids: [],
  enabled: true,
  is_default: false,
});

async function loadConfigs() {
  loading.value = true;
  try {
    const { data } = await listHAConfigs();
    rows.value = data?.data || [];
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载配置失败");
  } finally {
    loading.value = false;
  }
}

async function loadNotifyTargetOptions() {
  try {
    const { data } = await listNotifyTargets({ channel: "wecom" });
    notifyTargetOptions.value = data?.data || [];
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载通知地址失败");
  }
}

function formatNotifyTargets(targets) {
  if (!Array.isArray(targets) || !targets.length) {
    return "-";
  }
  return targets.map((item) => item.name).join("、");
}

function notifyTargetLabel(item) {
  return `${item.name}${item.enabled ? "" : "（已停用）"}`;
}

function openCreateDialog() {
  isEditing.value = false;
  form.value = {
    id: null,
    name: "",
    script_path: "",
    command_template: "",
    description: "",
    notify_target_ids: [],
    enabled: true,
    is_default: false,
  };
  dialogVisible.value = true;
}

function openEditDialog(row) {
  isEditing.value = true;
  form.value = {
    ...row,
    command_template: row.command_template || "",
    notify_target_ids: Array.isArray(row.notify_target_ids) ? [...row.notify_target_ids] : [],
  };
  dialogVisible.value = true;
}

async function saveConfig() {
  if (!form.value.name || !form.value.script_path) {
    return ElMessage.warning("请填写配置名称和脚本路径");
  }
  saving.value = true;
  try {
    if (isEditing.value) {
      await updateHAConfig(form.value.id, form.value);
      ElMessage.success("修改成功");
    } else {
      await createHAConfig(form.value);
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
    await updateHAConfig(row.id, { enabled: row.enabled });
    ElMessage.success(row.enabled ? "已启用" : "已禁用");
  } catch (error) {
    row.enabled = !row.enabled;
    ElMessage.error(error.response?.data?.message || "操作失败");
  }
}

async function verifyConfig(row) {
  try {
    const { data } = await verifyHAConfig({ script_path: row.script_path });
    ElMessage.success(`验证通过，版本: ${data?.data?.version || "unknown"}`);
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "验证失败");
  }
}

async function removeConfig(row) {
  try {
    await ElMessageBox.confirm(`确定删除配置 "${row.name}" 吗?`, "提示", { type: "warning" });
    await deleteHAConfig(row.id);
    ElMessage.success("删除成功");
    await loadConfigs();
  } catch (error) {
    if (error !== "cancel") {
      ElMessage.error(error.response?.data?.message || "删除失败");
    }
  }
}

onMounted(async () => {
  await Promise.all([loadConfigs(), loadNotifyTargetOptions()]);
});
</script>

<style scoped>
.page { padding: 20px; }
.header-row { display: flex; justify-content: space-between; align-items: center; }
.header-actions { display: flex; gap: 10px; }
.form-tip { margin-top: 6px; color: var(--el-text-color-secondary); line-height: 1.6; font-size: 12px; }
</style>
