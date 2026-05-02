<template>
  <div class="page">
    <div class="page-header">
      <div class="page-header-left">
        <div class="page-title">数据查询操作配置</div>
        <div class="page-subtitle">维护 MySQL / MongoDB / Redis 的数据查询白名单关键字，仅启用的操作允许在数据查询页执行</div>
      </div>
      <div class="page-header-actions">
        <el-button :icon="Refresh" @click="loadData">刷新</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="tip-alert">
      <template #title>
        预置关键字不可删除，但可临时禁用；自定义关键字可增删。修改立即生效（后台缓存将同步失效）。
      </template>
    </el-alert>

    <el-card
      v-for="group in groupMeta"
      :key="group.key"
      class="section-card"
      shadow="never"
    >
      <template #header>
        <div class="section-header">
          <span :class="['group-badge', `group-badge--${group.key}`]">{{ group.label }}</span>
          <span class="section-desc">{{ group.desc }}</span>
          <div class="section-actions">
            <el-button v-if="isAdmin" type="primary" size="small" :icon="Plus" @click="openCreate(group.key)">
              新增关键字
            </el-button>
          </div>
        </div>
      </template>
      <el-table
        :data="groups[group.key] || []"
        stripe
        size="small"
        empty-text="暂无关键字"
      >
        <el-table-column prop="op_key" label="关键字" min-width="160">
          <template #default="scope">
            <span class="op-key">{{ group.key === 'redis' ? scope.row.op_key.toUpperCase() : scope.row.op_key }}</span>
            <el-tag v-if="scope.row.is_builtin" size="small" type="info" effect="plain" class="ml-8">内置</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="label" label="描述" min-width="200">
          <template #default="scope">
            <span v-if="scope.row.label">{{ scope.row.label }}</span>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="100">
          <template #default="scope">
            <el-switch
              v-model="scope.row.enabled"
              :disabled="!isAdmin"
              @change="onToggleEnabled(scope.row)"
            />
          </template>
        </el-table-column>
        <el-table-column label="排序" width="100">
          <template #default="scope">
            <span>{{ scope.row.sort_order }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="160">
          <template #default="scope">
            <el-button v-if="isAdmin" link type="primary" size="small" @click="openEdit(scope.row)">编辑</el-button>
            <el-button
              v-if="isAdmin && !scope.row.is_builtin"
              link
              type="danger"
              size="small"
              @click="onDelete(scope.row)"
            >
              删除
            </el-button>
            <span v-if="!isAdmin" class="muted">无权限</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑关键字' : '新增关键字'"
      width="460px"
    >
      <el-form :model="form" label-width="90px">
        <el-form-item label="数据库">
          <el-tag :type="dbTypeTagType(form.db_type)" size="large" effect="plain">
            {{ dbTypeLabel(form.db_type) }}
          </el-tag>
        </el-form-item>
        <el-form-item label="关键字" required>
          <el-input
            v-model="form.op_key"
            placeholder="例如: SHOW / DESC / find / GET"
            :disabled="editingId && editingIsBuiltin"
          />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.label" placeholder="中文描述，可选" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item label="排序">
          <el-input-number v-model="form.sort_order" :min="0" :step="1" controls-position="right" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Plus, Refresh } from "@element-plus/icons-vue";
import {
  createDataQueryOp,
  deleteDataQueryOp,
  listDataQueryOps,
  updateDataQueryOp,
} from "../api/modules/data_query_ops";

const isAdmin = computed(() => {
  try {
    const user = JSON.parse(localStorage.getItem("dbms_user") || "{}");
    return user.role === "admin";
  } catch {
    return false;
  }
});

const groupMeta = [
  { key: "mysql", label: "MySQL", desc: "允许执行的 SQL 起始关键字（例如 SELECT、SHOW、DESC、EXPLAIN）" },
  { key: "mongodb", label: "MongoDB", desc: "允许的 op 与 run_command 子命令（例如 find、aggregate、ping）" },
  { key: "redis", label: "Redis", desc: "允许的 Redis 只读命令（例如 GET、HGET、LRANGE）" },
];

const groups = reactive({ mysql: [], mongodb: [], redis: [] });

const dialogVisible = ref(false);
const saving = ref(false);
const editingId = ref(null);
const editingIsBuiltin = ref(false);
const form = reactive({
  db_type: "mysql",
  op_key: "",
  label: "",
  enabled: true,
  sort_order: 99,
});

function resetForm(dbType = "mysql") {
  form.db_type = dbType;
  form.op_key = "";
  form.label = "";
  form.enabled = true;
  form.sort_order = 99;
  editingId.value = null;
  editingIsBuiltin.value = false;
}

async function loadData() {
  try {
    const { data } = await listDataQueryOps();
    const payload = data?.data?.groups || {};
    groups.mysql = payload.mysql || [];
    groups.mongodb = payload.mongodb || [];
    groups.redis = payload.redis || [];
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载数据查询操作配置失败");
  }
}

function openCreate(dbType) {
  resetForm(dbType);
  dialogVisible.value = true;
}

function openEdit(row) {
  editingId.value = row.id;
  editingIsBuiltin.value = !!row.is_builtin;
  form.db_type = row.db_type;
  form.op_key = row.op_key;
  form.label = row.label || "";
  form.enabled = !!row.enabled;
  form.sort_order = row.sort_order || 0;
  dialogVisible.value = true;
}

async function onSave() {
  if (!form.op_key || !form.op_key.trim()) {
    ElMessage.warning("请输入关键字");
    return;
  }
  saving.value = true;
  try {
    if (editingId.value) {
      const patch = {
        label: form.label || "",
        enabled: !!form.enabled,
        sort_order: Number(form.sort_order) || 0,
      };
      if (!editingIsBuiltin.value) {
        patch.op_key = form.op_key.trim();
      }
      await updateDataQueryOp(editingId.value, patch);
      ElMessage.success("已更新");
    } else {
      await createDataQueryOp({
        db_type: form.db_type,
        op_key: form.op_key.trim(),
        label: form.label || "",
        enabled: !!form.enabled,
        sort_order: Number(form.sort_order) || 0,
      });
      ElMessage.success("已新增");
    }
    dialogVisible.value = false;
    await loadData();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "保存失败");
  } finally {
    saving.value = false;
  }
}

async function onToggleEnabled(row) {
  try {
    await updateDataQueryOp(row.id, { enabled: !!row.enabled });
    ElMessage.success(row.enabled ? "已启用" : "已禁用");
  } catch (error) {
    row.enabled = !row.enabled; // 回滚
    ElMessage.error(error.response?.data?.message || "切换启用状态失败");
  }
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(
      `确认删除关键字 "${row.op_key}" 吗？删除后该关键字将不再被允许。`,
      "删除确认",
      { type: "warning" }
    );
  } catch {
    return;
  }
  try {
    await deleteDataQueryOp(row.id);
    ElMessage.success("已删除");
    await loadData();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "删除失败");
  }
}

function dbTypeLabel(type) {
  return { mysql: "MySQL", mongodb: "MongoDB", redis: "Redis" }[type] || type;
}
function dbTypeTagType(type) {
  return { mysql: "primary", mongodb: "success", redis: "danger" }[type] || "info";
}

onMounted(loadData);
</script>

<style scoped>
.page {
  padding: 16px 20px 24px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 12px;
  padding: 12px 16px;
  background: linear-gradient(135deg, #eef4ff 0%, #f0f9ff 100%);
  border: 1px solid #dbeafe;
  border-radius: 10px;
}
.page-title {
  font-size: 18px;
  font-weight: 600;
  color: #0f172a;
}
.page-subtitle {
  margin-top: 4px;
  font-size: 12.5px;
  color: #64748b;
}
.page-header-actions {
  display: flex;
  gap: 10px;
}

.tip-alert {
  margin-bottom: 12px;
}

.section-card {
  margin-bottom: 14px;
  border-radius: 10px;
  border: 1px solid #e5e7eb;
}
.section-card :deep(.el-card__header) {
  padding: 10px 16px;
  background: #fafbfc;
  border-bottom: 1px solid #eef0f3;
}
.section-card :deep(.el-card__body) {
  padding: 8px 16px 12px;
}
.section-header {
  display: flex;
  align-items: center;
  gap: 10px;
}
.section-desc {
  color: #94a3b8;
  font-size: 12.5px;
}
.section-actions {
  margin-left: auto;
}

.group-badge {
  display: inline-block;
  padding: 2px 10px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 4px;
  letter-spacing: 0.3px;
}
.group-badge--mysql {
  color: #1565c0;
  background: #e3f2fd;
  border: 1px solid #bbdefb;
}
.group-badge--mongodb {
  color: #2e7d32;
  background: #e8f5e9;
  border: 1px solid #c8e6c9;
}
.group-badge--redis {
  color: #c62828;
  background: #ffebee;
  border: 1px solid #ffcdd2;
}

.op-key {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-weight: 600;
  color: #0f172a;
}
.muted {
  color: #94a3b8;
}
.ml-8 {
  margin-left: 8px;
}
</style>
