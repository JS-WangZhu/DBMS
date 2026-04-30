<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>{{ title }} 实例管理</span>
          <div>
            <el-button type="primary" @click="dialogVisible = true">新增实例</el-button>
            <el-button @click="loadList">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table :data="rows" v-loading="loading" stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="实例名" min-width="120" />
        <el-table-column prop="host_input" label="地址" min-width="180" />
        <el-table-column prop="resolved_ip" label="解析IP" min-width="140" />
        <el-table-column prop="port" label="端口" width="90" />
        <el-table-column prop="username" label="账号" min-width="100" />
        <el-table-column prop="role_label" label="角色" min-width="100" />
        <el-table-column label="操作" width="280">
          <template #default="scope">
            <el-button link type="primary" @click="onRefreshResolve(scope.row)">解析刷新</el-button>
            <el-button link type="success" @click="onCollect(scope.row)">采集</el-button>
            <el-button link type="warning" @click="showSnapshot(scope.row)">快照</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" title="新增实例" width="560px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="实例名">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="地址">
          <el-input v-model="form.host_input" placeholder="IP或域名" />
        </el-form-item>
        <el-form-item label="端口">
          <el-input-number v-model="form.port" :min="1" :max="65535" style="width: 100%" />
        </el-form-item>
        <el-form-item label="用户名">
          <el-input v-model="form.username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password />
        </el-form-item>
        <el-form-item label="角色">
          <el-input v-model="form.role_label" placeholder="例如master/slave/primary" />
        </el-form-item>
      </el-form>

      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onCreate">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Coin, Files, Lightning, DataAnalysis } from "@element-plus/icons-vue";

import { createInstance, listInstances, refreshResolve } from "../api/modules/instances";
import { collectNow, latestSnapshot } from "../api/modules/monitoring";

const props = defineProps({
  dbType: {
    type: String,
    required: true,
  },
});

const labels = {
  mysql: "MySQL",
  mongodb: "MongoDB",
  redis: "Redis",
  doris: "Doris",
};

const icons = {
  mysql: Coin,
  mongodb: Files,
  redis: Lightning,
  doris: DataAnalysis,
};

const title = computed(() => labels[props.dbType] || props.dbType);
const dbIcon = computed(() => icons[props.dbType] || Coin);

const loading = ref(false);
const saving = ref(false);
const dialogVisible = ref(false);
const rows = ref([]);

const form = reactive({
  name: "",
  host_input: "",
  port: defaultPort(props.dbType),
  username: "",
  password: "",
  role_label: "",
});

function defaultPort(dbType) {
  if (dbType === "mysql") return 3306;
  if (dbType === "mongodb") return 27017;
  if (dbType === "redis") return 6379;
  if (dbType === "doris") return 9030;
  return 0;
}

function resetForm() {
  form.name = "";
  form.host_input = "";
  form.port = defaultPort(props.dbType);
  form.username = "";
  form.password = "";
  form.role_label = "";
}

async function loadList() {
  loading.value = true;
  try {
    const { data } = await listInstances(props.dbType);
    rows.value = data.data || [];
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载失败");
  } finally {
    loading.value = false;
  }
}

async function onCreate() {
  if (!form.name || !form.host_input || !form.port) {
    ElMessage.warning("请填写必填字段");
    return;
  }

  saving.value = true;
  try {
    await createInstance({
      name: form.name,
      db_type: props.dbType,
      host_input: form.host_input,
      port: form.port,
      username: form.username,
      password: form.password,
      role_label: form.role_label,
      enabled: true,
    });
    ElMessage.success("创建成功");
    dialogVisible.value = false;
    resetForm();
    await loadList();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "创建失败");
  } finally {
    saving.value = false;
  }
}

async function onRefreshResolve(row) {
  try {
    const { data } = await refreshResolve(row.id);
    const changed = data.data.changed ? "有变化" : "无变化";
    ElMessage.success(`解析刷新完成: ${changed}`);
    await loadList();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "刷新失败");
  }
}

async function onCollect(row) {
  try {
    await collectNow(row.id);
    ElMessage.success("采集成功");
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "采集失败");
  }
}

async function showSnapshot(row) {
  try {
    const { data } = await latestSnapshot(row.id);
    await ElMessageBox.alert(`<pre style='white-space:pre-wrap'>${JSON.stringify(data.data.payload_json, null, 2)}</pre>`, "最新快照", {
      dangerouslyUseHTMLString: true,
      confirmButtonText: "关闭",
    });
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "未找到快照");
  }
}

watch(
  () => props.dbType,
  () => {
    form.port = defaultPort(props.dbType);
    loadList();
  },
);

onMounted(() => {
  loadList();
});
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
