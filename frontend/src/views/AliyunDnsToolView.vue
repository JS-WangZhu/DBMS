<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>阿里云域名工具</span>
          <div class="header-actions">
            <el-select v-model="selectedConfigId" placeholder="选择配置" style="width: 220px" @change="onConfigChange">
              <el-option v-for="item in configs" :key="item.id" :label="item.name" :value="item.id" />
            </el-select>
            <el-select v-model="selectedDomain" placeholder="选择域名" style="width: 200px">
              <el-option v-for="domain in domainOptions" :key="domain" :label="domain" :value="domain" />
            </el-select>
            <el-input v-model="rrKeyword" clearable placeholder="主机记录关键字" style="width: 160px" @keyup.enter="loadRecords" />
            <el-input v-model="valueKeyword" clearable placeholder="解析地址关键字" style="width: 170px" @keyup.enter="loadRecords" />
            <el-button @click="loadRecords">查询</el-button>
            <el-button type="primary" @click="openCreateDialog">新增解析</el-button>
          </div>
        </div>
      </template>

      <el-table :data="records" stripe v-loading="loading">
        <el-table-column prop="RecordId" label="RecordId" min-width="160" show-overflow-tooltip />
        <el-table-column prop="RR" label="主机记录" width="120" />
        <el-table-column prop="Type" label="类型" width="90" />
        <el-table-column prop="Value" label="记录值" min-width="220" show-overflow-tooltip />
        <el-table-column prop="TTL" label="TTL" width="90" />
        <el-table-column prop="Line" label="线路" width="120" />
        <el-table-column label="状态" width="90">
          <template #default="scope">
            <el-tag :type="isRecordEnabled(scope.row) ? 'success' : 'info'">
              {{ isRecordEnabled(scope.row) ? "启用" : "关闭" }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180">
          <template #default="scope">
            <el-button link type="primary" @click="openEditDialog(scope.row)">编辑</el-button>
            <el-button link type="danger" @click="removeRecord(scope.row)">删除</el-button>
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

    <el-dialog v-model="dialogVisible" :title="editingRecordId ? '修改解析' : '新增解析'" width="620px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="域名"><el-input v-model="selectedDomain" disabled /></el-form-item>
        <el-form-item label="主机记录"><el-input v-model="form.rr" placeholder="@ 或 www" /></el-form-item>
        <el-form-item label="记录类型">
          <el-select v-model="form.type" style="width: 100%">
            <el-option v-for="type in recordTypes" :key="type" :label="type" :value="type" />
          </el-select>
        </el-form-item>
        <el-form-item label="记录值"><el-input v-model="form.value" placeholder="IP、CNAME 或文本值" /></el-form-item>
        <el-form-item label="TTL"><el-input-number v-model="form.ttl" :min="60" :step="60" style="width: 100%" /></el-form-item>
        <el-form-item label="线路"><el-input v-model="form.line" placeholder="可选，默认留空" /></el-form-item>
        <el-form-item label="MX优先级" v-if="form.type === 'MX'">
          <el-input-number v-model="form.priority" :min="1" :max="99" style="width: 100%" />
        </el-form-item>
        <el-form-item v-if="editingRecordId" label="状态">
          <el-switch
            v-model="form.enabled"
            active-text="启用"
            inactive-text="关闭"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button v-if="!editingRecordId" :loading="saving" @click="saveRecord(true)">保存并快速添加下一个</el-button>
        <el-button type="primary" :loading="saving" @click="saveRecord(false)">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  createAliyunDnsRecord,
  deleteAliyunDnsRecord,
  listAliyunDnsRecords,
  listAliyunDomainConfigs,
  updateAliyunDnsRecord,
} from "../api/modules/aliyun_dns";

const configs = ref([]);
const selectedConfigId = ref(null);
const selectedDomain = ref("");
const rrKeyword = ref("");
const valueKeyword = ref("");
const records = ref([]);
const loading = ref(false);
const saving = ref(false);
const dialogVisible = ref(false);
const editingRecordId = ref("");
const editingOriginal = ref(null);
const page = ref(1);
const pageSize = ref(10);
const total = ref(0);
const recordTypes = ["A", "AAAA", "CNAME", "MX", "TXT", "NS", "SRV", "CAA", "PTR"];

const form = reactive({
  rr: "",
  type: "A",
  value: "",
  ttl: 600,
  line: "",
  priority: null,
  enabled: true,
});

const currentConfig = computed(() => configs.value.find((item) => item.id === selectedConfigId.value));
const domainOptions = computed(() => currentConfig.value?.domains || []);

function resetRecordForm() {
  form.rr = "";
  form.type = "A";
  form.value = "";
  form.ttl = 600;
  form.line = "";
  form.priority = null;
  form.enabled = true;
}

async function loadConfigs() {
  try {
    const { data } = await listAliyunDomainConfigs({ enabled: true, page_size: 200 });
    configs.value = data.data?.items || [];
    if (!selectedConfigId.value && configs.value.length) {
      selectedConfigId.value = configs.value[0].id;
      selectedDomain.value = configs.value[0].domains?.[0] || "";
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载域名配置失败");
  }
}

function onConfigChange() {
  selectedDomain.value = domainOptions.value[0] || "";
  records.value = [];
}

async function loadRecords() {
  if (!selectedConfigId.value || !selectedDomain.value) {
    ElMessage.warning("请先选择配置和域名");
    return;
  }
  loading.value = true;
  try {
    const { data } = await listAliyunDnsRecords({
      config_id: selectedConfigId.value,
      domain: selectedDomain.value,
      rr_keyword: rrKeyword.value.trim() || undefined,
      value_keyword: valueKeyword.value.trim() || undefined,
      page: page.value,
      page_size: pageSize.value,
    });
    records.value = data.data?.items || [];
    total.value = data.data?.total || 0;
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "查询解析失败");
  } finally {
    loading.value = false;
  }
}

async function onPageChange(nextPage) {
  page.value = nextPage;
  await loadRecords();
}

async function onPageSizeChange(nextSize) {
  pageSize.value = nextSize;
  page.value = 1;
  await loadRecords();
}

function openCreateDialog() {
  if (!selectedConfigId.value || !selectedDomain.value) {
    ElMessage.warning("请先选择配置和域名");
    return;
  }
  editingRecordId.value = "";
  editingOriginal.value = null;
  resetRecordForm();
  dialogVisible.value = true;
}

function openEditDialog(row) {
  editingRecordId.value = row.RecordId;
  editingOriginal.value = row;
  form.rr = row.RR || "";
  form.type = row.Type || "A";
  form.value = row.Value || "";
  form.ttl = Number(row.TTL || 600);
  form.line = row.Line || "";
  form.priority = row.Priority || null;
  form.enabled = isRecordEnabled(row);
  dialogVisible.value = true;
}

function recordStatusValue(row) {
  return String(row?.Status || "").toUpperCase();
}

function isRecordEnabled(row) {
  return recordStatusValue(row) !== "DISABLE";
}

function recordFieldsChanged(row) {
  if (!row) {
    return true;
  }
  const currentPriority = form.type === "MX" ? form.priority ?? null : null;
  const originalPriority = row.Type === "MX" ? row.Priority ?? null : null;
  return (
    form.rr !== (row.RR || "") ||
    form.type !== (row.Type || "A") ||
    form.value !== (row.Value || "") ||
    Number(form.ttl || 600) !== Number(row.TTL || 600) ||
    (form.line || "") !== (row.Line || "") ||
    currentPriority !== originalPriority
  );
}

async function saveRecord(keepOpen = false) {
  if (!form.rr || !form.type || !form.value) {
    ElMessage.warning("请填写主机记录、类型和记录值");
    return;
  }
  saving.value = true;
  try {
    const fullPayload = {
      config_id: selectedConfigId.value,
      domain: selectedDomain.value,
      rr: form.rr,
      type: form.type,
      value: form.value,
      ttl: form.ttl,
      line: form.line,
      priority: form.type === "MX" ? form.priority : undefined,
    };
    if (editingRecordId.value) {
      const statusChanged = form.enabled !== isRecordEnabled(editingOriginal.value);
      const fieldsChanged = recordFieldsChanged(editingOriginal.value);
      if (!fieldsChanged && !statusChanged) {
        ElMessage.info("没有变更");
        dialogVisible.value = false;
        return;
      }
      const payload = !fieldsChanged && statusChanged
        ? {
            config_id: selectedConfigId.value,
            domain: selectedDomain.value,
            status: form.enabled ? "Enable" : "Disable",
          }
        : fullPayload;
      if (fieldsChanged && statusChanged) {
        payload.status = form.enabled ? "Enable" : "Disable";
      }
      await updateAliyunDnsRecord(editingRecordId.value, payload);
      ElMessage.success("解析已修改");
    } else {
      await createAliyunDnsRecord(fullPayload);
      ElMessage.success("解析已新增");
    }
    if (!keepOpen) {
      dialogVisible.value = false;
    }
    await loadRecords();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "保存解析失败");
  } finally {
    saving.value = false;
  }
}

async function removeRecord(row) {
  try {
    await ElMessageBox.confirm(`确认删除 ${row.RR}.${selectedDomain.value} 的 ${row.Type} 记录吗？`, "提示", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });
    const recordName = `${row.RR}.${selectedDomain.value}`;
    await ElMessageBox.prompt(`请再次输入解析记录 ${recordName} 确认删除`, "二次确认", {
      type: "warning",
      confirmButtonText: "确认删除",
      cancelButtonText: "取消",
      inputValidator: (value) => value === recordName || "输入内容与解析记录不一致",
    });
    await deleteAliyunDnsRecord(row.RecordId, { config_id: selectedConfigId.value, domain: selectedDomain.value });
    ElMessage.success("解析已删除");
    await loadRecords();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.message || "删除解析失败");
    }
  }
}

onMounted(async () => {
  await loadConfigs();
  if (selectedConfigId.value && selectedDomain.value) {
    await loadRecords();
  }
});
</script>

<style scoped>
.page { padding: 20px; }
.header-row { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
.header-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; justify-content: flex-end; }
.pager-wrap { margin-top: 16px; display: flex; justify-content: flex-end; }
</style>
