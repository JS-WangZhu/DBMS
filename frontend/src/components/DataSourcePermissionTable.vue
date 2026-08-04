<template>
  <div class="permission-table">
    <div class="filter-panel">
      <div class="filter-header">
        <span class="filter-title">筛选数据源</span>
        <div class="filter-actions">
          <el-button v-if="hasFilters" link type="primary" @click="resetFilters">清空筛选</el-button>
          <el-button type="success" plain :disabled="disabled || !filteredPermissions.length" @click="enableFilteredPermission('can_query')">一键查询</el-button>
          <el-button type="danger" plain :disabled="disabled || !filteredPermissions.length" @click="enableFilteredPermission('can_change')">一键变更</el-button>
          <el-button type="warning" plain :disabled="disabled || !filteredPermissions.length" @click="enableFilteredPermission('can_execute')">一键执行</el-button>
        </div>
      </div>
      <div class="filter-grid">
        <label class="filter-field keyword-field">
          <span>关键字</span>
          <el-input v-model="keyword" clearable placeholder="搜索数据源名称" />
        </label>
        <label class="filter-field">
          <span>项目</span>
          <el-select v-model="project" clearable filterable placeholder="全部项目">
            <el-option v-for="item in projects" :key="item" :label="item" :value="item" />
          </el-select>
        </label>
        <label class="filter-field">
          <span>环境</span>
          <el-select v-model="environment" clearable filterable placeholder="全部环境">
            <el-option v-for="item in environments" :key="item" :label="item" :value="item" />
          </el-select>
        </label>
        <label class="filter-field">
          <span>数据库类型</span>
          <el-select v-model="dbType" clearable filterable placeholder="全部类型">
            <el-option v-for="item in dbTypes" :key="item" :label="String(item).toUpperCase()" :value="item" />
          </el-select>
        </label>
      </div>
    </div>

    <el-table :data="filteredPermissions" stripe empty-text="未找到匹配的数据源">
      <el-table-column label="数据源" min-width="260">
        <template #default="{ row }">{{ dataSourceLabel(row.cluster_id) }}</template>
      </el-table-column>
      <el-table-column label="直接查询" width="130">
        <template #default="{ row }">
          <el-switch :model-value="row.can_query" :disabled="disabled" @update:model-value="update(row.cluster_id, 'can_query', $event)" />
        </template>
      </el-table-column>
      <el-table-column label="直接变更" width="130">
        <template #default="{ row }">
          <el-switch :model-value="row.can_change" :disabled="disabled" @update:model-value="update(row.cluster_id, 'can_change', $event)" />
        </template>
      </el-table-column>
      <el-table-column label="直接执行" width="130">
        <template #default="{ row }">
          <el-switch :model-value="row.can_execute" :disabled="disabled" @update:model-value="update(row.cluster_id, 'can_execute', $event)" />
        </template>
      </el-table-column>
      <el-table-column label="最终有效" width="240">
        <template #default="{ row }">
          <template v-if="effective[row.cluster_id]">
            <el-tag v-if="effective[row.cluster_id].can_query" type="success">查询</el-tag>
            <el-tag v-if="effective[row.cluster_id].can_change" type="danger">变更</el-tag>
            <el-tag v-if="effective[row.cluster_id].can_execute" type="warning">执行</el-tag>
          </template>
          <span v-else>-</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";

const props = defineProps({
  modelValue: { type: Array, required: true },
  clusters: { type: Array, required: true },
  effective: { type: Object, default: () => ({}) },
  disabled: Boolean,
});
const emit = defineEmits(["update:modelValue"]);

const keyword = ref("");
const project = ref("");
const environment = ref("");
const dbType = ref("");

const clusterMap = computed(() => new Map(props.clusters.map((item) => [item.id, item])));
const uniqueValues = (getter) => [...new Set(props.clusters.map(getter).filter(Boolean))].sort((a, b) => String(a).localeCompare(String(b), "zh-CN"));
const projects = computed(() => uniqueValues((item) => item.business_line || item.namespace));
const environments = computed(() => uniqueValues((item) => item.environment));
const dbTypes = computed(() => uniqueValues((item) => item.db_type));
const hasFilters = computed(() => Boolean(keyword.value.trim() || project.value || environment.value || dbType.value));
const clusterText = (cluster = {}) => [cluster.db_type, cluster.business_line, cluster.namespace, cluster.environment, cluster.name].filter(Boolean).join(" ").toLowerCase();
const dataSourceLabel = (id) => {
  const item = clusterMap.value.get(id) || {};
  return [item.db_type?.toUpperCase(), item.business_line || item.namespace, item.environment, item.name].filter(Boolean).join(" / ");
};

const filteredPermissions = computed(() => {
  const value = keyword.value.trim().toLowerCase();
  return props.modelValue.filter((permission) => {
    const cluster = clusterMap.value.get(permission.cluster_id) || {};
    if (project.value && (cluster.business_line || cluster.namespace) !== project.value) return false;
    if (environment.value && cluster.environment !== environment.value) return false;
    if (dbType.value && cluster.db_type !== dbType.value) return false;
    return !value || clusterText(cluster).includes(value);
  });
});

function update(id, key, value) {
  emit("update:modelValue", props.modelValue.map((item) => item.cluster_id === id ? { ...item, [key]: value } : item));
}

function enableFilteredPermission(key) {
  const filteredIds = new Set(filteredPermissions.value.map((item) => item.cluster_id));
  emit("update:modelValue", props.modelValue.map((item) => filteredIds.has(item.cluster_id) ? { ...item, [key]: true } : item));
}

function resetFilters() {
  keyword.value = "";
  project.value = "";
  environment.value = "";
  dbType.value = "";
}
</script>

<style scoped>
.permission-table { margin-top: 16px; }
.filter-panel { padding: 14px 16px 16px; margin-bottom: 14px; border: 1px solid var(--el-border-color-lighter); border-radius: 8px; background: var(--el-fill-color-light); }
.filter-header { display: flex; justify-content: space-between; align-items: center; min-height: 24px; margin-bottom: 10px; }
.filter-title { color: var(--el-text-color-primary); font-size: 14px; font-weight: 600; }
.filter-actions { display: flex; align-items: center; gap: 8px; }
.filter-actions :deep(.el-button + .el-button) { margin-left: 0; }
.filter-grid { display: grid; grid-template-columns: minmax(220px, 1.4fr) repeat(3, minmax(150px, 1fr)); gap: 12px; align-items: end; }
.filter-field { display: flex; min-width: 0; flex-direction: column; gap: 6px; color: var(--el-text-color-secondary); font-size: 12px; }
.filter-field :deep(.el-input), .filter-field :deep(.el-select) { width: 100%; }
.filter-field :deep(.el-input__wrapper), .filter-field :deep(.el-select__wrapper) { background: var(--el-bg-color); }
.el-tag + .el-tag { margin-left: 6px; }

@media (max-width: 1200px) {
  .filter-grid { grid-template-columns: repeat(2, minmax(180px, 1fr)); }
}

@media (max-width: 760px) {
  .filter-grid { grid-template-columns: 1fr; }
}
</style>
