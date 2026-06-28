<template>
  <div class="page">
    <el-card>
      <template #header>
        <span>备份记录筛选</span>
      </template>

      <el-form :inline="true" class="filter-form" size="small">
        <el-form-item label="数据库类型">
          <el-select v-model="filters.db_type" clearable placeholder="全部" style="width: 140px">
            <el-option label="MySQL" value="mysql" />
            <el-option label="MongoDB" value="mongodb" />
          </el-select>
        </el-form-item>

        <el-form-item label="状态">
          <el-select v-model="filters.status" clearable placeholder="全部" style="width: 120px">
            <el-option label="成功" value="success" />
            <el-option label="失败" value="failed" />
            <el-option label="运行中" value="running" />
          </el-select>
        </el-form-item>

        <el-form-item label="策略ID">
          <el-input-number v-model="filters.policy_id" :min="1" controls-position="right" placeholder="全部" style="width: 140px" />
        </el-form-item>

        <el-form-item label="策略关键字">
          <el-input v-model="filters.keyword" clearable placeholder="策略名称" style="width: 180px" />
        </el-form-item>

        <el-form-item label="时间范围">
          <el-date-picker
            v-model="filters.range"
            type="datetimerange"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            value-format="YYYY-MM-DD HH:mm:ss"
            style="width: 360px"
          />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" @click="onSearch">查询</el-button>
          <el-button @click="onReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card>
      <template #header>
        <div class="header-row">
          <span>全部备份情况</span>
          <span>共 {{ total }} 条</span>
        </div>
      </template>

      <el-table :data="rows" v-loading="loading" stripe size="small">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="policy_name" label="策略" min-width="160" />
        <el-table-column prop="agent_name" label="执行地址" width="130" />
        <el-table-column
          prop="db_type"
          label="库类型"
          width="110"
          :filters="dbTypeFilters"
          :filter-method="filterByDbType"
          :filter-multiple="false"
        />
        <el-table-column
          prop="status"
          label="状态"
          width="110"
          :filters="statusFilters"
          :filter-method="filterByStatus"
          :filter-multiple="false"
        >
          <template #default="scope">
            <el-tag v-if="scope.row.status === 'success'" type="success">成功</el-tag>
            <el-tag v-else-if="scope.row.status === 'failed'" type="danger">失败</el-tag>
            <el-tag v-else type="warning">运行中</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="started_at" label="开始时间" min-width="170">
          <template #default="scope">
            {{ formatBeijingTime(scope.row.started_at) }}
          </template>
        </el-table-column>
        <el-table-column prop="finished_at" label="结束时间" min-width="170">
          <template #default="scope">
            {{ formatBeijingTime(scope.row.finished_at) }}
          </template>
        </el-table-column>
        <el-table-column prop="size_bytes" label="大小" width="140">
          <template #default="scope">
            {{ formatBytes(scope.row.size_bytes) }}
          </template>
        </el-table-column>
        <el-table-column prop="compress" label="压缩" width="80">
          <template #default="scope">
            <el-tag v-if="scope.row.compress_method && scope.row.compress_method !== 'none'" size="small" type="info">{{ scope.row.compress_method }}</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column prop="file_path" label="文件路径" min-width="220" show-overflow-tooltip />
        <el-table-column prop="error_message" label="错误信息" min-width="220" show-overflow-tooltip />
        <el-table-column label="操作" width="240" fixed="right">
          <template #default="scope">
            <div class="op-actions">
              <el-button link type="primary" @click="openDownloadDialog(scope.row)">下载</el-button>
              <el-button v-if="scope.row.encrypt?.enabled" link type="warning" @click="showDecryptHelp(scope.row)">解密方法</el-button>
              <el-button link type="danger" @click="removeRecord(scope.row, false)">删除记录</el-button>
              <el-button link type="danger" @click="removeRecord(scope.row, true)">删除记录+文件</el-button>
            </div>
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
          size="small"
          @size-change="onPageSizeChange"
          @current-change="onPageChange"
        />
      </div>
    </el-card>

    <el-dialog v-model="decryptDialogVisible" title="解密方法" width="640px">
      <el-form label-width="100px" size="small">
        <el-form-item label="备份文件">
          <el-input :model-value="decryptInfo.file_path" readonly />
        </el-form-item>
        <el-form-item label="加密状态">
          <el-tag type="warning">已加密</el-tag>
        </el-form-item>
        <el-form-item label="解密命令">
          <el-input
            :model-value="decryptInfo.commands"
            type="textarea"
            :rows="8"
            readonly
            style="font-family: monospace"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="decryptDialogVisible = false">关闭</el-button>
        <el-button type="primary" @click="copyDecryptCommands">复制命令</el-button>
      </template>
    </el-dialog>
    <el-dialog v-model="downloadDialogVisible" title="备份下载" width="680px">
      <el-form label-width="120px" size="small">
        <el-form-item label="日志ID">
          <el-input :model-value="downloadInfo.log_id" readonly />
        </el-form-item>
        <el-form-item label="文件名">
          <el-input :model-value="downloadInfo.filename" readonly />
        </el-form-item>
        <el-form-item label="服务器文件下载" v-if="downloadInfo.local.available">
          <div class="row-actions">
            <el-button type="primary" @click="triggerLocalDownload">下载</el-button>
          </div>
        </el-form-item>
        <el-form-item label="S3 文件下载" v-if="downloadInfo.s3.available">
          <div class="row-actions">
            <el-button type="primary" @click="triggerS3Download">下载</el-button>
            <el-button @click="copyText(downloadInfo.s3.url)">复制链接</el-button>
          </div>
          <div class="hint-text" v-if="downloadInfo.s3.available_until">
            链接有效期至：{{ downloadInfo.s3.available_until }}
          </div>
        </el-form-item>
        <div v-if="!downloadInfo.local.available && !downloadInfo.s3.available" class="hint-text">
          {{ downloadInfo.unavailable_message || "暂无可用下载来源" }}
        </div>
      </el-form>
      <template #footer>
        <el-button @click="downloadDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { deleteBackupLog, downloadBackupFile, downloadBackupFileFromAgent, getBackupDownloadUrl, listBackupLogs } from "../api/modules/backups";
import { formatBeijingTime } from "../utils/time";

const loading = ref(false);
const rows = ref([]);
const total = ref(0);
const page = ref(1);
const pageSize = ref(10);

const filters = reactive({
  db_type: "",
  status: "",
  policy_id: null,
  keyword: "",
  range: [],
});

const decryptDialogVisible = ref(false);
const decryptInfo = reactive({
  file_path: "",
  commands: "",
});
const downloadDialogVisible = ref(false);
const downloadInfo = reactive({
  log_id: null,
  filename: "",
  unavailable_message: "",
  local: { available: false, url: "", mode: "local" },
  s3: { available: false, url: "", available_until: "" },
});

function showDecryptHelp(row) {
  const filePath = row.file_path || "backup.tar.gz";
  const encFile = filePath.includes(".enc") ? filePath : filePath + ".enc";
  const baseName = filePath.replace(/\.enc$/, "");
  const fallbackDecryptCmd = `python -c "import base64;from pathlib import Path;d=Path(r'${encFile}').read_bytes();m=b'\\n-----BEGIN ENCRYPTED KEY-----\\n';e=b'\\n-----END ENCRYPTED KEY-----\\n';i=d.rfind(m);j=d.rfind(e);assert i>8 and j>i,'invalid encrypted file format';Path('encrypted_payload.bin').write_bytes(d[8:i]);Path('encrypted_key.bin').write_bytes(base64.b64decode(d[i+len(m):j]))" && openssl pkeyutl -decrypt -inkey private_key.pem -in encrypted_key.bin -out key_iv.txt && key=$(cut -d: -f1 key_iv.txt) && iv=$(cut -d: -f2 key_iv.txt) && openssl enc -aes-256-cbc -d -nosalt -K $key -iv $iv -in encrypted_payload.bin -out '${baseName}' && rm -f key_iv.txt encrypted_key.bin encrypted_payload.bin`;
  const decryptCmd = row.encrypt?.decrypt_cmd;

  decryptInfo.file_path = filePath;
  decryptInfo.commands = decryptCmd && !decryptCmd.includes("head -c 8") ? decryptCmd : fallbackDecryptCmd;
  decryptDialogVisible.value = true;
}

function copyDecryptCommands() {
  navigator.clipboard.writeText(decryptInfo.commands);
  ElMessage.success("已复制到剪贴板");
}

const dbTypeFilters = computed(() => {
  const options = [];
  const seen = new Set();
  let hasEmpty = false;
  rows.value.forEach((row) => {
    const value = row.db_type;
    if (value === null || value === undefined || value === "") {
      hasEmpty = true;
      return;
    }
    if (seen.has(value)) {
      return;
    }
    seen.add(value);
    const label = value === "mysql" ? "MySQL" : value === "mongodb" ? "MongoDB" : String(value);
    options.push({ text: label, value });
  });
  if (hasEmpty) {
    options.unshift({ text: "未设置", value: "__empty__" });
  }
  return options;
});

const statusFilters = computed(() => {
  const options = [];
  const seen = new Set();
  let hasEmpty = false;
  rows.value.forEach((row) => {
    const value = row.status;
    if (value === null || value === undefined || value === "") {
      hasEmpty = true;
      return;
    }
    if (seen.has(value)) {
      return;
    }
    seen.add(value);
    const label = value === "success" ? "成功" : value === "failed" ? "失败" : "运行中";
    options.push({ text: label, value });
  });
  if (hasEmpty) {
    options.unshift({ text: "未知", value: "__empty__" });
  }
  return options;
});

function filterByDbType(value, row) {
  if (value === "__empty__") {
    return row.db_type === null || row.db_type === undefined || row.db_type === "";
  }
  return row.db_type === value;
}

function filterByStatus(value, row) {
  if (value === "__empty__") {
    return row.status === null || row.status === undefined || row.status === "";
  }
  return row.status === value;
}

function formatBytes(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes < 0) {
    return String(value);
  }
  if (bytes === 0) {
    return "0 B";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  const unitIndex = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const size = bytes / Math.pow(1024, unitIndex);
  const precision = unitIndex === 0 ? 0 : size >= 100 ? 0 : size >= 10 ? 1 : 2;
  return `${size.toFixed(precision)} ${units[unitIndex]}`;
}

function buildParams() {
  const params = {
    page: page.value,
    page_size: pageSize.value,
  };

  if (filters.db_type) params.db_type = filters.db_type;
  if (filters.status) params.status = filters.status;
  if (filters.policy_id) params.policy_id = filters.policy_id;
  if (filters.keyword) params.keyword = filters.keyword;
  if (filters.range?.length === 2) {
    params.start_at = filters.range[0];
    params.end_at = filters.range[1];
  }

  return params;
}

async function loadRecords() {
  loading.value = true;
  try {
    const { data } = await listBackupLogs(buildParams());
    rows.value = data.data.items || [];
    total.value = data.data.total || 0;
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载备份记录失败");
  } finally {
    loading.value = false;
  }
}

function onSearch() {
  page.value = 1;
  loadRecords();
}

function onReset() {
  filters.db_type = "";
  filters.status = "";
  filters.policy_id = null;
  filters.keyword = "";
  filters.range = [];
  page.value = 1;
  pageSize.value = 10;
  loadRecords();
}

function onPageChange(newPage) {
  page.value = newPage;
  loadRecords();
}

function onPageSizeChange(newSize) {
  pageSize.value = newSize;
  page.value = 1;
  loadRecords();
}

async function openDownloadDialog(row) {
  try {
    const { data } = await getBackupDownloadUrl(row.id);
    const payload = data?.data || {};
    downloadInfo.log_id = row.id;
    downloadInfo.filename = (row.file_path || "backup").split(/[\\/]/).pop();
    downloadInfo.unavailable_message = payload?.message || "";
    const localAvailable = !!payload?.local?.available;
    const agentAvailable = !!payload?.agent?.available;
    downloadInfo.local.available = localAvailable || agentAvailable;
    downloadInfo.local.mode = localAvailable ? "local" : agentAvailable ? "agent" : "local";
    if (downloadInfo.local.mode === "agent") {
      downloadInfo.local.url = `${window.location.origin}/api/v1/backups/logs/${row.id}/download-agent`;
    } else {
      downloadInfo.local.url = downloadInfo.local.available ? `${window.location.origin}/api/v1/backups/logs/${row.id}/download` : "";
    }
    downloadInfo.s3.available = !!payload?.s3?.available && !!payload?.s3?.url;
    downloadInfo.s3.url = payload?.s3?.url || "";
    downloadInfo.s3.available_until = payload?.s3?.available_until ? formatBeijingTime(payload.s3.available_until) : "";
    downloadDialogVisible.value = true;
  } catch (error) {
    downloadInfo.log_id = row.id;
    downloadInfo.filename = (row.file_path || "backup").split(/[\\/]/).pop();
    downloadInfo.unavailable_message = error.response?.data?.message || "暂无可用下载来源";
    downloadInfo.local.available = false;
    downloadInfo.local.url = "";
    downloadInfo.local.mode = "local";
    downloadInfo.s3.available = false;
    downloadInfo.s3.url = "";
    downloadInfo.s3.available_until = "";
    downloadDialogVisible.value = true;
    ElMessage.warning(downloadInfo.unavailable_message);
  }
}

async function downloadRecordFromLocal(logId, filePath) {
  const response = downloadInfo.local.mode === "agent" ? await downloadBackupFileFromAgent(logId) : await downloadBackupFile(logId);
  const blob = new Blob([response.data]);
  const filename = (filePath || "backup").split(/[\\/]/).pop();
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename || "backup";
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(link.href);
}

async function triggerLocalDownload() {
  if (!downloadInfo.local.available) {
    ElMessage.warning("本地文件不可下载");
    return;
  }
  try {
    await downloadRecordFromLocal(downloadInfo.log_id, downloadInfo.filename);
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "本地下载失败");
  }
}

function triggerS3Download() {
  if (!downloadInfo.s3.available || !downloadInfo.s3.url) {
    ElMessage.warning("S3 下载不可用");
    return;
  }
  window.open(downloadInfo.s3.url, "_blank");
}

function copyText(text) {
  if (!text) {
    ElMessage.warning("无可复制内容");
    return;
  }
  navigator.clipboard.writeText(text);
  ElMessage.success("已复制到剪贴板");
}

async function removeRecord(row, deleteFile) {
  const actionName = deleteFile ? "删除记录并删除文件" : "仅删除记录";
  try {
    await ElMessageBox.confirm(`确认${actionName}（日志ID: ${row.id}）吗？`, "提示", {
      type: "warning",
      confirmButtonText: "确认",
      cancelButtonText: "取消",
    });

    await deleteBackupLog(row.id, deleteFile);
    ElMessage.success(deleteFile ? "记录和文件已删除" : "记录已删除");

    if (rows.value.length === 1 && page.value > 1) {
      page.value -= 1;
    }
    await loadRecords();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.message || "删除失败");
    }
  }
}

onMounted(loadRecords);
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.filter-form {
  margin-bottom: -4px;
}

.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.op-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}

.row-actions {
  display: flex;
  align-items: center;
  width: 100%;
  gap: 8px;
}

.hint-text {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.pager-wrap {
  margin-top: 10px;
  display: flex;
  justify-content: flex-end;
}

:deep(.el-card__header) {
  padding: 10px 14px;
}

:deep(.el-card__body) {
  padding: 12px 14px;
}

:deep(.el-table .el-table__cell) {
  padding-top: 4px;
  padding-bottom: 4px;
}

:deep(.el-table .cell) {
  padding-left: 4px;
  padding-right: 4px;
  min-height: 24px;
}

:deep(.el-tag) {
  height: 18px;
  line-height: 18px;
  font-size: 11px;
  padding: 0 6px;
}

:deep(.el-form-item) {
  margin-bottom: 8px;
}
</style>
