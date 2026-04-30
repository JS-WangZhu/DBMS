<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>通知地址管理</span>
          <div class="header-actions">
            <el-button type="primary" @click="openCreateDialog">新增通知地址</el-button>
            <el-button @click="loadNotifyTargets">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table :data="notifyTargets" stripe>
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column label="渠道" width="120">
          <template #default="scope">
            {{ scope.row.channel === "wecom" ? "企微Webhook" : "邮件" }}
          </template>
        </el-table-column>
        <el-table-column prop="address" label="地址" min-width="260" />
        <el-table-column label="状态" width="90">
          <template #default="scope">
            <el-tag v-if="scope.row.enabled" type="success">启用</el-tag>
            <el-tag v-else type="info">停用</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="240">
          <template #default="scope">
            <el-button link type="primary" @click="openEditDialog(scope.row)">编辑</el-button>
            <el-button link type="warning" @click="sendTest(scope.row)">发送测试</el-button>
            <el-button link type="danger" @click="removeNotifyTarget(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑通知地址' : '新增通知地址'" width="560px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="渠道">
          <el-select v-model="form.channel" style="width: 100%" @change="onChannelChange">
            <el-option label="企微Webhook" value="wecom" />
            <el-option label="邮件" value="email" />
          </el-select>
        </el-form-item>
        <el-form-item :label="form.channel === 'wecom' ? 'Webhook地址' : '邮箱地址'">
          <el-input
            v-model="form.address"
            :placeholder="form.channel === 'wecom' ? 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...' : 'ops@example.com'"
          />
        </el-form-item>
        <el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveNotifyTarget">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  createNotifyTarget,
  deleteNotifyTarget,
  listNotifyTargets,
  testNotifyTarget,
  updateNotifyTarget,
} from "../api/modules/backups";

const notifyTargets = ref([]);
const dialogVisible = ref(false);
const saving = ref(false);
const editingId = ref(null);

const form = reactive({
  name: "",
  channel: "wecom",
  address: "",
  enabled: true,
});

async function loadNotifyTargets() {
  try {
    const { data } = await listNotifyTargets();
    notifyTargets.value = data.data || [];
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载通知地址失败");
  }
}

function onChannelChange() {
  form.address = "";
}

function openCreateDialog() {
  editingId.value = null;
  form.name = "";
  form.channel = "wecom";
  form.address = "";
  form.enabled = true;
  dialogVisible.value = true;
}

function openEditDialog(row) {
  editingId.value = row.id;
  form.name = row.name;
  form.channel = row.channel;
  form.address = row.address;
  form.enabled = !!row.enabled;
  dialogVisible.value = true;
}

async function saveNotifyTarget() {
  if (!form.name || !form.address) {
    ElMessage.warning("请填写名称和地址");
    return;
  }

  saving.value = true;
  try {
    const payload = {
      name: form.name,
      channel: form.channel,
      address: form.address,
      enabled: form.enabled,
    };

    if (editingId.value) {
      await updateNotifyTarget(editingId.value, payload);
      ElMessage.success("通知地址已更新");
    } else {
      await createNotifyTarget(payload);
      ElMessage.success("通知地址已创建");
    }

    dialogVisible.value = false;
    await loadNotifyTargets();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "保存失败");
  } finally {
    saving.value = false;
  }
}

async function removeNotifyTarget(row) {
  try {
    await ElMessageBox.confirm(`确认删除通知地址 ${row.name} 吗？`, "提示", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    await deleteNotifyTarget(row.id);
    ElMessage.success("通知地址已删除");
    await loadNotifyTargets();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.message || "删除失败");
    }
  }
}

async function sendTest(row) {
  try {
    await testNotifyTarget(row.id);
    ElMessage.success("测试消息已发送");
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "测试发送失败");
  }
}

onMounted(loadNotifyTargets);
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
