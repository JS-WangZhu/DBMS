<template>
  <el-card>
    <template #header>
      <div class="header-row">
        <span>Redis 定制管理</span>
        <div>
          <el-button type="primary" @click="dialogVisible = true">新增Redis实例</el-button>
          <el-button @click="loadList">刷新</el-button>
        </div>
      </div>
    </template>

    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="name" label="实例名" min-width="120" />
      <el-table-column prop="host_input" label="地址" min-width="180" />
      <el-table-column prop="port" label="端口" width="90" />
      <el-table-column label="定制操作" width="180">
        <template #default="scope">
          <el-button link type="primary" @click="viewHealth(scope.row)">集群健康</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="新增Redis实例" width="560px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="实例名"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="地址"><el-input v-model="form.host_input" placeholder="IP或域名" /></el-form-item>
        <el-form-item label="端口"><el-input-number v-model="form.port" :min="1" :max="65535" style="width: 100%" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="form.password" type="password" show-password /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onCreate">保存</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { Lightning } from "@element-plus/icons-vue";

import { createRedisInstance, listRedisInstances, redisClusterHealth } from "../api/modules/redis";

const loading = ref(false);
const saving = ref(false);
const dialogVisible = ref(false);
const rows = ref([]);
const form = reactive({ name: "", host_input: "", port: 6379, password: "" });

async function loadList() {
  loading.value = true;
  try {
    const { data } = await listRedisInstances();
    rows.value = data.data || [];
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载失败");
  } finally {
    loading.value = false;
  }
}

async function onCreate() {
  saving.value = true;
  try {
    await createRedisInstance({ ...form });
    ElMessage.success("创建成功");
    dialogVisible.value = false;
    await loadList();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "创建失败");
  } finally {
    saving.value = false;
  }
}

async function viewHealth(row) {
  try {
    const { data } = await redisClusterHealth(row.id);
    await ElMessageBox.alert(`<pre style='white-space:pre-wrap'>${JSON.stringify(data.data, null, 2)}</pre>`, "集群健康", {
      dangerouslyUseHTMLString: true,
    });
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "获取失败");
  }
}

onMounted(loadList);
</script>

<style scoped>
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
