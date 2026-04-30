<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>存储配置管理</span>
          <div class="header-actions">
            <el-input v-model="keyword" clearable placeholder="搜索名称/Bucket/Prefix/Endpoint" style="width: 320px" @keyup.enter="onSearch" />
            <el-button @click="onSearch">搜索</el-button>
            <el-button @click="onReset">重置</el-button>
            <el-button type="primary" @click="openCreateDialog">新增配置</el-button>
          </div>
        </div>
      </template>

      <el-table :data="configs" stripe v-loading="loading">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column prop="description" label="描述" min-width="180" />
        <el-table-column prop="bucket" label="Bucket" min-width="140" />
        <el-table-column prop="prefix" label="Prefix" min-width="120" />
        <el-table-column prop="region" label="Region" min-width="100" />
        <el-table-column prop="endpoint_url" label="Endpoint" min-width="180" show-overflow-tooltip />
        <el-table-column label="状态" width="90">
          <template #default="scope">
            <el-tag v-if="scope.row.enabled" type="success">启用</el-tag>
            <el-tag v-else type="info">停用</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180">
          <template #default="scope">
            <el-button link type="primary" @click="openEditDialog(scope.row)">编辑</el-button>
            <el-button link type="danger" @click="removeConfig(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pager-wrap">
        <el-pagination
          background
          layout="total, sizes, prev, pager, next"
          :total="total"
          :current-page="page"
          :page-size="pageSize"
          :page-sizes="[10, 20, 50, 100]"
          @current-change="onPageChange"
          @size-change="onPageSizeChange"
        />
      </div>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑S3存储配置' : '新增S3存储配置'" width="680px">
      <el-form :model="form" label-width="120px">
        <el-form-item label="配置名称">
          <el-input v-model="form.name" placeholder="例如: 生产环境S3" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" placeholder="可选，描述该配置的用途" />
        </el-form-item>
        <el-form-item label="Bucket">
          <el-input v-model="form.bucket" placeholder="S3 Bucket名称" />
        </el-form-item>
        <el-form-item label="Prefix">
          <el-input v-model="form.prefix" placeholder="可选，文件前缀路径，例如: dbms-backup" />
        </el-form-item>
        <el-form-item label="Region">
          <el-input v-model="form.region" placeholder="可选，例如: us-east-1" />
        </el-form-item>
        <el-form-item label="Endpoint">
          <el-input v-model="form.endpoint_url" placeholder="可选，自定义Endpoint URL" />
        </el-form-item>
        <el-form-item label="Access Key">
          <el-input v-model="form.access_key" placeholder="AWS Access Key" />
        </el-form-item>
        <el-form-item label="Secret Key">
          <el-input v-model="form.secret_key" type="password" show-password placeholder="AWS Secret Key" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
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
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  createS3StorageConfig,
  deleteS3StorageConfig,
  listS3StorageConfigsDirect,
  updateS3StorageConfig,
} from "../api/modules/backups";

const configs = ref([]);
const loading = ref(false);
const dialogVisible = ref(false);
const saving = ref(false);
const editingId = ref(null);
const keyword = ref("");
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);

const form = reactive({
  name: "",
  description: "",
  bucket: "",
  prefix: "",
  region: "",
  endpoint_url: "",
  access_key: "",
  secret_key: "",
  enabled: true,
});

function resetForm() {
  form.name = "";
  form.description = "";
  form.bucket = "";
  form.prefix = "";
  form.region = "";
  form.endpoint_url = "";
  form.access_key = "";
  form.secret_key = "";
  form.enabled = true;
}

async function loadConfigs() {
  loading.value = true;
  try {
    const { data } = await listS3StorageConfigsDirect({
      keyword: keyword.value.trim() || undefined,
      page: page.value,
      page_size: pageSize.value,
    });
    const payload = data?.data || {};
    configs.value = payload.items || [];
    total.value = payload.total || 0;
    page.value = payload.page || page.value;
    pageSize.value = payload.page_size || pageSize.value;
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载S3存储配置失败");
  } finally {
    loading.value = false;
  }
}

async function onSearch() {
  page.value = 1;
  await loadConfigs();
}

async function onReset() {
  keyword.value = "";
  page.value = 1;
  pageSize.value = 20;
  await loadConfigs();
}

async function onPageChange(nextPage) {
  page.value = nextPage;
  await loadConfigs();
}

async function onPageSizeChange(nextSize) {
  pageSize.value = nextSize;
  page.value = 1;
  await loadConfigs();
}

function openCreateDialog() {
  editingId.value = null;
  resetForm();
  dialogVisible.value = true;
}

function openEditDialog(row) {
  editingId.value = row.id;
  form.name = row.name;
  form.description = row.description || "";
  form.bucket = row.bucket;
  form.prefix = row.prefix || "";
  form.region = row.region || "";
  form.endpoint_url = row.endpoint_url || "";
  form.access_key = row.access_key;
  form.secret_key = row.secret_key;
  form.enabled = row.enabled;
  dialogVisible.value = true;
}

async function onSave() {
  if (!form.name) {
    ElMessage.warning("请填写配置名称");
    return;
  }
  if (!form.bucket) {
    ElMessage.warning("请填写Bucket");
    return;
  }
  if (!form.access_key) {
    ElMessage.warning("请填写Access Key");
    return;
  }
  if (!form.secret_key) {
    ElMessage.warning("请填写Secret Key");
    return;
  }

  saving.value = true;
  try {
    const payload = {
      name: form.name,
      description: form.description,
      bucket: form.bucket,
      prefix: form.prefix,
      region: form.region,
      endpoint_url: form.endpoint_url,
      access_key: form.access_key,
      secret_key: form.secret_key,
      enabled: form.enabled,
    };

    if (editingId.value) {
      await updateS3StorageConfig(editingId.value, payload);
      ElMessage.success("S3存储配置已更新");
    } else {
      await createS3StorageConfig(payload);
      ElMessage.success("S3存储配置已创建");
    }

    dialogVisible.value = false;
    await loadConfigs();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "保存S3存储配置失败");
  } finally {
    saving.value = false;
  }
}

async function removeConfig(row) {
  try {
    await ElMessageBox.confirm(`确认删除S3存储配置 ${row.name} 吗？`, "提示", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await deleteS3StorageConfig(row.id);
    ElMessage.success("S3存储配置已删除");
    await loadConfigs();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.message || "删除S3存储配置失败");
    }
  }
}

onMounted(loadConfigs);
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

.header-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}

.pager-wrap {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}
</style>
