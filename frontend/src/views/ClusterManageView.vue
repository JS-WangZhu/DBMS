<template>
  <el-card>
    <template #header>
      <div class="header-row">
        <span>{{ dbLabel }} 集群管理</span>
        <div class="actions">
          <el-select v-model="filters.business_line" clearable placeholder="项目（可选）" style="width: 170px">
            <el-option v-for="line in businessLineOptions" :key="line" :label="line" :value="line" />
          </el-select>
          <el-select v-model="filters.environment" clearable placeholder="环境（可选）" style="width: 170px">
            <el-option v-for="env in environmentOptions" :key="env" :label="env" :value="env" />
          </el-select>
          <el-input v-model="filters.keyword" placeholder="关键字" clearable style="width: 180px" />
          <el-button @click="loadClusters">筛选</el-button>
          <el-button type="primary" @click="openCreateDialog">新建集群</el-button>
          <el-button @click="loadClusters">刷新</el-button>
        </div>
      </div>
    </template>

    <el-table :data="pagedRows" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column
        prop="business_line"
        label="项目"
        min-width="130"
        :filters="businessLineFilters"
        :filter-method="filterByBusinessLine"
        :filter-multiple="false"
      />
      <el-table-column
        prop="environment"
        label="环境"
        min-width="130"
        :filters="environmentFilters"
        :filter-method="filterByEnvironment"
        :filter-multiple="false"
      />
      <el-table-column prop="name" label="集群名称" min-width="180" />
      <el-table-column prop="ha_domain" label="高可用域名" min-width="180" show-overflow-tooltip />
      <el-table-column v-if="dbType === 'mysql'" label="HA切换" width="100">
        <template #default="scope">
          <el-tag :type="scope.row.ha_switch_enabled ? 'success' : 'info'">
            {{ scope.row.ha_switch_enabled ? "已启用" : "未启用" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="240" show-overflow-tooltip />
      <el-table-column prop="created_at" label="创建时间" min-width="180">
        <template #default="scope">
          {{ formatBeijingTime(scope.row.created_at) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160">
        <template #default="scope">
          <el-button link type="primary" @click="openEditDialog(scope.row)">编辑</el-button>
          <el-button link type="danger" @click="removeCluster(scope.row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="pagination-wrap">
      <el-pagination
        background
        layout="total, sizes, prev, pager, next, jumper"
        :total="displayRows.length"
        :current-page="pager.page"
        :page-size="pager.page_size"
        :page-sizes="[20, 50, 100, 200]"
        @current-change="onPageChange"
        @size-change="onPageSizeChange"
      />
    </div>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="560px">
      <el-form :model="form" label-width="105px">
        <el-form-item label="项目"><el-input v-model.trim="form.business_line" placeholder="可选，如：支付/电商" /></el-form-item>
        <el-form-item label="环境"><el-input v-model.trim="form.environment" placeholder="可选，如：prod/test" /></el-form-item>
        <el-form-item label="集群名称"><el-input v-model.trim="form.name" /></el-form-item>
        <el-form-item label="高可用域名"><el-input v-model.trim="form.ha_domain" placeholder="可填域名或IP" /></el-form-item>
        <el-form-item v-if="dbType === 'mysql'" label="启用HA切换">
          <el-switch v-model="form.ha_switch_enabled" />
        </el-form-item>
        <el-form-item label="备注"><el-input v-model.trim="form.description" type="textarea" :rows="3" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSubmit">{{ editingClusterId ? "更新" : "保存" }}</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
  import { ElMessage, ElMessageBox } from "element-plus";
  import { useRoute } from "vue-router";

  import { createCluster, deleteCluster, listClusters, updateCluster } from "../api/modules/clusters";
  import { formatBeijingTime } from "../utils/time";

const route = useRoute();

const dbType = computed(() => route.meta.dbType || "mysql");
const dbLabel = computed(() => route.meta.dbLabel || "DB");

const loading = ref(false);
const saving = ref(false);
const dialogVisible = ref(false);
const rows = ref([]);
const editingClusterId = ref(null);
const pager = reactive({
  page: 1,
  page_size: 20,
});

const filters = reactive({
  business_line: "",
  environment: "",
  keyword: "",
});

const form = reactive({
  business_line: "",
  environment: "",
  name: "",
  ha_domain: "",
  ha_switch_enabled: false,
  description: "",
});

const dialogTitle = computed(() => (editingClusterId.value ? `编辑${dbLabel.value}集群` : `新建${dbLabel.value}集群`));

const displayRows = computed(() => {
  if (!filters.keyword) {
    return rows.value;
  }
  const keyword = filters.keyword.trim().toLowerCase();
  if (!keyword) {
    return rows.value;
  }
  return rows.value.filter((row) => {
    const text = `${row.business_line || row.namespace || ""} ${row.environment || ""} ${row.name || ""} ${row.ha_domain || ""} ${row.description || ""}`.toLowerCase();
    return text.includes(keyword);
  });
});

const pagedRows = computed(() => {
  const start = (pager.page - 1) * pager.page_size;
  return displayRows.value.slice(start, start + pager.page_size);
});

const businessLineFilters = computed(() => {
  const options = [];
  const seen = new Set();
  let hasEmpty = false;
  rows.value.forEach((row) => {
    const value = row.business_line || row.namespace;
    if (value === null || value === undefined || value === "") {
      hasEmpty = true;
      return;
    }
    if (seen.has(value)) {
      return;
    }
    seen.add(value);
    options.push({ text: String(value), value });
  });
  if (hasEmpty) {
    options.unshift({ text: "未设置", value: "__empty__" });
  }
  return options;
});

const environmentFilters = computed(() => {
  const options = [];
  const seen = new Set();
  let hasEmpty = false;
  rows.value.forEach((row) => {
    const value = row.environment;
    if (value === null || value === undefined || value === "") {
      hasEmpty = true;
      return;
    }
    if (seen.has(value)) {
      return;
    }
    seen.add(value);
    options.push({ text: String(value), value });
  });
  if (hasEmpty) {
    options.unshift({ text: "未设置", value: "__empty__" });
  }
  return options;
});

function filterByBusinessLine(value, row) {
  const raw = row.business_line || row.namespace;
  if (value === "__empty__") {
    return raw === null || raw === undefined || raw === "";
  }
  return raw === value;
}

function filterByEnvironment(value, row) {
  const raw = row.environment;
  if (value === "__empty__") {
    return raw === null || raw === undefined || raw === "";
  }
  return raw === value;
}

const businessLineOptions = computed(() => {
  const set = new Set(rows.value.map((row) => row.business_line || row.namespace).filter(Boolean));
  return Array.from(set).sort();
});

const environmentOptions = computed(() => {
  if (!filters.business_line) {
    const set = new Set(rows.value.map((row) => row.environment).filter(Boolean));
    return Array.from(set).sort();
  }
  const set = new Set(
    rows.value
      .filter((row) => (row.business_line || row.namespace) === filters.business_line)
      .map((row) => row.environment)
      .filter(Boolean),
  );
  return Array.from(set).sort();
});

function resetForm() {
  editingClusterId.value = null;
  form.business_line = filters.business_line || "";
  form.environment = filters.environment || "";
  form.name = "";
  form.ha_domain = "";
  form.ha_switch_enabled = false;
  form.description = "";
}

function openCreateDialog() {
  resetForm();
  dialogVisible.value = true;
}

function openEditDialog(row) {
  editingClusterId.value = row.id;
  form.business_line = row.business_line || row.namespace || "";
  form.environment = row.environment || "";
  form.name = row.name || "";
  form.ha_domain = row.ha_domain || "";
  form.ha_switch_enabled = !!row.ha_switch_enabled;
  form.description = row.description || "";
  dialogVisible.value = true;
}

async function loadClusters() {
  loading.value = true;
  try {
    const { data } = await listClusters(dbType.value, {
      business_line: filters.business_line,
      environment: filters.environment,
    });
    rows.value = data.data || [];
    if ((pager.page - 1) * pager.page_size >= displayRows.value.length) {
      pager.page = 1;
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载集群失败");
  } finally {
    loading.value = false;
  }
}

function onPageChange(page) {
  pager.page = Number(page) || 1;
}

function onPageSizeChange(size) {
  pager.page_size = Number(size) || 20;
  pager.page = 1;
}

async function onSubmit() {
  const payload = {
    business_line: (form.business_line || "").trim(),
    environment: (form.environment || "").trim(),
    name: (form.name || "").trim(),
    ha_domain: (form.ha_domain || "").trim(),
    ha_switch_enabled: !!form.ha_switch_enabled,
    description: (form.description || "").trim(),
  };

  if (!payload.name) {
    ElMessage.warning("请填写集群名称");
    return;
  }

  saving.value = true;
  try {
    let saved = null;
    if (editingClusterId.value) {
      const { data } = await updateCluster(editingClusterId.value, payload);
      saved = data?.data || null;
      ElMessage.success("集群更新成功");
    } else {
      const { data } = await createCluster({
        business_line: payload.business_line,
        environment: payload.environment,
        name: payload.name,
        ha_domain: payload.ha_domain,
        ha_switch_enabled: payload.ha_switch_enabled,
        db_type: dbType.value,
        description: payload.description,
      });
      saved = data?.data || null;
      ElMessage.success("集群创建成功");
    }
    dialogVisible.value = false;
    editingClusterId.value = null;
    await loadClusters();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || (editingClusterId.value ? "更新集群失败" : "创建集群失败"));
  } finally {
    saving.value = false;
  }
}

async function removeCluster(row) {
  try {
    const label = [row.business_line || row.namespace, row.environment, row.name].filter(Boolean).join("/");
    await ElMessageBox.confirm(`确认删除集群 ${label || row.name} 吗？`, "提示", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await deleteCluster(row.id);
    ElMessage.success("集群已删除");
    await loadClusters();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.message || "删除集群失败");
    }
  }
}

onMounted(loadClusters);

watch(
  () => dbType.value,
  async () => {
    filters.keyword = "";
    filters.business_line = "";
    filters.environment = "";
    pager.page = 1;
    resetForm();
    await loadClusters();
  },
);

watch(
  () => [filters.keyword, filters.business_line, filters.environment],
  () => {
    pager.page = 1;
  },
);
</script>

<style scoped>
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.actions {
  display: inline-flex;
  gap: 8px;
}

.pagination-wrap {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}
</style>
