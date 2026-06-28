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
          <el-button v-if="isAdmin" type="primary" @click="openCreateDialog">新建集群</el-button>
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
      <el-table-column v-if="dbType === 'mysql'" :label="'HA管理模式'" width="120">
        <template #default="scope">
          <el-tag :type="haModeTagType(scope.row.ha_mode)">
            {{ haModeLabel(scope.row.ha_mode) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column v-if="dbType === 'mysql'" label="访问路由" min-width="220">
        <template #default="scope">
          <div class="route-summary">
            <span>查询：{{ routeSummary(scope.row, "query") }}</span>
            <span>变更：{{ routeSummary(scope.row, "change") }}</span>
          </div>
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
          <el-button v-if="isAdmin" link type="primary" @click="openEditDialog(scope.row)">编辑</el-button>
          <el-button v-if="isAdmin" link type="danger" @click="removeCluster(scope.row)">删除</el-button>
          <span v-if="!isAdmin" class="no-perm-hint">无权限</span>
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
        :page-sizes="[10, 20, 50, 100, 200]"
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
        <el-form-item v-if="dbType === 'mysql'" :label="'HA管理模式'">
          <el-select v-model="form.ha_mode" style="width: 100%">
            <el-option v-for="item in haModeOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <template v-if="dbType === 'mysql'">
          <el-form-item label="查询路由">
            <div class="route-form-row">
              <el-segmented v-model="form.data_access_route_json.query.mode" :options="routeModeOptions" />
              <el-select
                v-if="form.data_access_route_json.query.mode === 'manual'"
                v-model="form.data_access_route_json.query.instance_id"
                clearable
                filterable
                placeholder="选择查询实例"
                class="route-instance-select"
              >
                <el-option
                  v-for="instance in currentClusterInstances"
                  :key="instance.id"
                  :label="instanceLabel(instance)"
                  :value="instance.id"
                />
              </el-select>
            </div>
          </el-form-item>
          <el-form-item label="变更路由">
            <div class="route-form-row">
              <el-segmented v-model="form.data_access_route_json.change.mode" :options="routeModeOptions" />
              <el-select
                v-if="form.data_access_route_json.change.mode === 'manual'"
                v-model="form.data_access_route_json.change.instance_id"
                clearable
                filterable
                placeholder="选择变更实例"
                class="route-instance-select"
              >
                <el-option
                  v-for="instance in currentClusterInstances"
                  :key="instance.id"
                  :label="instanceLabel(instance)"
                  :value="instance.id"
                />
              </el-select>
            </div>
          </el-form-item>
        </template>
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
  import { listInstances } from "../api/modules/instances";
  import { formatBeijingTime } from "../utils/time";

const route = useRoute();

const dbType = computed(() => route.meta.dbType || "mysql");
const dbLabel = computed(() => route.meta.dbLabel || "DB");

const isAdmin = computed(() => {
  try {
    const user = JSON.parse(localStorage.getItem("dbms_user") || "{}");
    return user.role === "admin";
  } catch {
    return false;
  }
});

const loading = ref(false);
const saving = ref(false);
const dialogVisible = ref(false);
const rows = ref([]);
const instances = ref([]);
const editingClusterId = ref(null);
const pager = reactive({
  page: 1,
  page_size: 10,
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
  ha_mode: "none",
  data_access_route_json: {
    query: { mode: "auto", instance_id: null },
    change: { mode: "auto", instance_id: null },
  },
  description: "",
});

const routeModeOptions = [
  { label: "自动", value: "auto" },
  { label: "手动", value: "manual" },
];
const haModeOptions = [
  { label: "无", value: "none" },
  { label: "ORC", value: "orc" },
  { label: "DBMS", value: "dbms" },
];

function normalizeHaMode(value) {
  return ["none", "orc", "dbms"].includes(value) ? value : "none";
}

function haModeLabel(value) {
  return { none: "无", orc: "ORC 托管", dbms: "DBMS 托管" }[normalizeHaMode(value)];
}

function haModeTagType(value) {
  return { none: "info", orc: "warning", dbms: "success" }[normalizeHaMode(value)];
}

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

const currentClusterInstances = computed(() => {
  if (!editingClusterId.value) return [];
  return instances.value.filter((item) => Number(item.cluster_id) === Number(editingClusterId.value));
});

function normalizeRouteConfig(value) {
  const source = value && typeof value === "object" ? value : {};
  const normalizePart = (key) => {
    const item = source[key] && typeof source[key] === "object" ? source[key] : {};
    const mode = item.mode === "manual" ? "manual" : "auto";
    return {
      mode,
      instance_id: mode === "manual" ? (item.instance_id || null) : null,
    };
  };
  return {
    query: normalizePart("query"),
    change: normalizePart("change"),
  };
}

function instanceLabel(instance) {
  const address = `${instance.resolved_ip || instance.host_input || "-"}:${instance.port || "-"}`;
  return `${instance.name || `实例-${instance.id}`} (${address})`;
}

function routeSummary(row, key) {
  const route = normalizeRouteConfig(row.data_access_route_json);
  const item = route[key] || { mode: "auto" };
  if (item.mode !== "manual") return "自动";
  const instance = instances.value.find((ins) => Number(ins.id) === Number(item.instance_id));
  return instance ? instanceLabel(instance) : `实例 ${item.instance_id || "-"}`;
}

function resetForm() {
  editingClusterId.value = null;
  form.business_line = filters.business_line || "";
  form.environment = filters.environment || "";
  form.name = "";
  form.ha_domain = "";
  form.ha_mode = "none";
  form.data_access_route_json = normalizeRouteConfig(null);
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
  form.ha_mode = normalizeHaMode(row.ha_mode);
  form.data_access_route_json = normalizeRouteConfig(row.data_access_route_json);
  form.description = row.description || "";
  dialogVisible.value = true;
}

async function loadInstancesForRoutes() {
  if (dbType.value !== "mysql") {
    instances.value = [];
    return;
  }
  try {
    const { data } = await listInstances(dbType.value);
    instances.value = data.data || [];
  } catch {
    instances.value = [];
  }
}

async function loadClusters() {
  loading.value = true;
  try {
    await loadInstancesForRoutes();
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
  pager.page_size = Number(size) || 10;
  pager.page = 1;
}

async function onSubmit() {
  const payload = {
    business_line: (form.business_line || "").trim(),
    environment: (form.environment || "").trim(),
    name: (form.name || "").trim(),
    ha_domain: (form.ha_domain || "").trim(),
    ha_mode: dbType.value === "mysql" ? normalizeHaMode(form.ha_mode) : "none",
    data_access_route_json: normalizeRouteConfig(form.data_access_route_json),
    description: (form.description || "").trim(),
  };

  if (!payload.name) {
    ElMessage.warning("请填写集群名称");
    return;
  }

  if (dbType.value === "mysql") {
    if (payload.data_access_route_json.query.mode === "manual" && !payload.data_access_route_json.query.instance_id) {
      ElMessage.warning("请选择查询路由实例");
      return;
    }
    if (payload.data_access_route_json.change.mode === "manual" && !payload.data_access_route_json.change.instance_id) {
      ElMessage.warning("请选择变更路由实例");
      return;
    }
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
        ha_mode: payload.ha_mode,
        data_access_route_json: payload.data_access_route_json,
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

.no-perm-hint {
  color: #94a3b8;
  font-size: 12px;
}

.route-summary {
  display: flex;
  flex-direction: column;
  gap: 2px;
  line-height: 1.35;
}

.route-form-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.route-instance-select {
  flex: 1;
}
</style>
