<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>域名配置管理</span>
          <div class="header-actions">
            <el-input v-model="keyword" clearable placeholder="搜索配置名称" style="width: 240px" @keyup.enter="onSearch" />
            <el-button @click="onSearch">搜索</el-button>
            <el-button @click="loadConfigs">刷新</el-button>
            <el-button type="primary" @click="openCreateDialog">新增配置</el-button>
          </div>
        </div>
      </template>

      <el-table :data="configs" stripe v-loading="loading">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="配置名称" min-width="140" />
        <el-table-column prop="description" label="描述" min-width="160" />
        <el-table-column prop="access_key" label="AccessKey" min-width="180" show-overflow-tooltip />
        <el-table-column label="SecretKey" width="120">
          <template #default="scope">
            <el-tag :type="scope.row.secret_key_set ? 'success' : 'info'">{{ scope.row.secret_key_set ? "已配置" : "未配置" }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="管理域名" min-width="240">
          <template #default="scope">
            <el-tag v-for="domain in scope.row.domains" :key="domain" class="domain-tag">{{ domain }}</el-tag>
          </template>
        </el-table-column>
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
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑域名配置' : '新增域名配置'" width="680px">
      <el-form :model="form" label-width="120px">
        <el-form-item label="配置名称"><el-input v-model="form.name" placeholder="例如: 生产阿里云DNS" /></el-form-item>
        <el-form-item label="描述"><el-input v-model="form.description" placeholder="可选" /></el-form-item>
        <el-form-item label="AccessKey"><el-input v-model="form.access_key" /></el-form-item>
        <el-form-item label="SecretKey">
          <el-input v-model="form.secret_key" type="password" show-password :placeholder="editingId ? '留空表示不修改' : '请输入 SecretKey'" />
        </el-form-item>
        <el-form-item label="管理域名">
          <el-input v-model="form.domainsText" type="textarea" :rows="4" placeholder="每行或逗号分隔一个域名，例如 example.com" />
        </el-form-item>
        <el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveConfig">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  createAliyunDomainConfig,
  deleteAliyunDomainConfig,
  listAliyunDomainConfigs,
  updateAliyunDomainConfig,
} from "../api/modules/aliyun_dns";

const configs = ref([]);
const loading = ref(false);
const saving = ref(false);
const dialogVisible = ref(false);
const editingId = ref(null);
const keyword = ref("");

const form = reactive({
  name: "",
  description: "",
  access_key: "",
  secret_key: "",
  domainsText: "",
  enabled: true,
});

function parseDomains() {
  return form.domainsText
    .split(/[\n,，]/)
    .map((item) => item.trim().toLowerCase())
    .filter(Boolean);
}

function resetForm() {
  form.name = "";
  form.description = "";
  form.access_key = "";
  form.secret_key = "";
  form.domainsText = "";
  form.enabled = true;
}

async function loadConfigs() {
  loading.value = true;
  try {
    const { data } = await listAliyunDomainConfigs({ keyword: keyword.value.trim() || undefined, page_size: 200 });
    configs.value = data.data?.items || [];
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载域名配置失败");
  } finally {
    loading.value = false;
  }
}

async function onSearch() {
  await loadConfigs();
}

function openCreateDialog() {
  editingId.value = null;
  resetForm();
  dialogVisible.value = true;
}

function openEditDialog(row) {
  editingId.value = row.id;
  form.name = row.name || "";
  form.description = row.description || "";
  form.access_key = row.access_key || "";
  form.secret_key = "";
  form.domainsText = (row.domains || []).join("\n");
  form.enabled = !!row.enabled;
  dialogVisible.value = true;
}

async function saveConfig() {
  if (!form.name || !form.access_key || (!editingId.value && !form.secret_key) || !parseDomains().length) {
    ElMessage.warning("请填写配置名称、AK/SK 和管理域名");
    return;
  }
  saving.value = true;
  try {
    const payload = {
      name: form.name,
      description: form.description,
      access_key: form.access_key,
      domains: parseDomains(),
      enabled: form.enabled,
    };
    if (form.secret_key) {
      payload.secret_key = form.secret_key;
    }
    if (editingId.value) {
      await updateAliyunDomainConfig(editingId.value, payload);
      ElMessage.success("域名配置已更新");
    } else {
      await createAliyunDomainConfig(payload);
      ElMessage.success("域名配置已创建");
    }
    dialogVisible.value = false;
    await loadConfigs();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "保存失败");
  } finally {
    saving.value = false;
  }
}

async function removeConfig(row) {
  try {
    await ElMessageBox.confirm(`确认删除域名配置 ${row.name} 吗？`, "提示", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await ElMessageBox.prompt(`请再次输入配置名称 ${row.name} 确认删除`, "二次确认", {
      type: "warning",
      confirmButtonText: "确认删除",
      cancelButtonText: "取消",
      inputValidator: (value) => value === row.name || "输入内容与配置名称不一致",
    });
    await deleteAliyunDomainConfig(row.id);
    ElMessage.success("域名配置已删除");
    await loadConfigs();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.message || "删除失败");
    }
  }
}

onMounted(loadConfigs);
</script>

<style scoped>
.page { padding: 20px; }
.header-row { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
.header-actions { display: flex; gap: 10px; align-items: center; }
.domain-tag { margin: 2px 6px 2px 0; }
</style>
