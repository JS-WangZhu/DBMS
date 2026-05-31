<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>MCP开放平台</span>
          <el-button type="primary" :icon="Plus" @click="openCreateDialog">新建 API Key</el-button>
        </div>
      </template>

      <div class="endpoint-grid">
        <div class="endpoint-block">
          <div class="endpoint-title">Streamable HTTP MCP入口</div>
          <el-input :model-value="remoteMcpEndpoint" readonly>
            <template #append>
              <el-button :icon="CopyDocument" @click="copyText(remoteMcpEndpoint)" />
            </template>
          </el-input>
        </div>
        <div class="endpoint-block">
          <div class="endpoint-title">实例状态查询接口</div>
          <el-input :model-value="statusEndpoint" readonly>
            <template #append>
              <el-button :icon="CopyDocument" @click="copyText(statusEndpoint)" />
            </template>
          </el-input>
        </div>
        <div class="endpoint-block">
          <div class="endpoint-title">MCP工具式接口</div>
          <el-input :model-value="toolEndpoint" readonly>
            <template #append>
              <el-button :icon="CopyDocument" @click="copyText(toolEndpoint)" />
            </template>
          </el-input>
        </div>
      </div>

      <el-descriptions class="capabilities" :column="2" border>
        <el-descriptions-item label="认证方式">Header: X-API-Key</el-descriptions-item>
        <el-descriptions-item label="能力范围">instance_status:read</el-descriptions-item>
        <el-descriptions-item label="覆盖数据库">MySQL / MongoDB / Redis / Doris</el-descriptions-item>
        <el-descriptions-item label="返回内容">集群、实例、角色、连通性、版本、指标、告警、最新采集时间</el-descriptions-item>
      </el-descriptions>

      <el-tabs class="access-tabs" model-value="stdio">
        <el-tab-pane label="标准 MCP Client" name="stdio">
          <el-alert
            class="tips"
            type="success"
            show-icon
            :closable="false"
            title="Claude Code、Cursor、Cherry Studio 优先使用远程 Streamable HTTP 接入；需要本地进程模式时再使用 stdio 适配器。"
          />
          <div class="snippet-grid">
            <div>
              <div class="endpoint-title">远程 Streamable HTTP 配置示例</div>
              <pre class="snippet">{{ remoteHttpConfigSnippet }}</pre>
            </div>
            <div>
              <div class="endpoint-title">本地 stdio 配置示例</div>
              <pre class="snippet">{{ stdioConfigSnippet }}</pre>
            </div>
            <div>
              <div class="endpoint-title">可用工具</div>
              <pre class="snippet">{{ toolSchemaSnippet }}</pre>
            </div>
          </div>
        </el-tab-pane>
        <el-tab-pane label="HTTP API" name="http">
          <el-alert
            class="tips"
            type="info"
            show-icon
            :closable="false"
            title="不支持标准 MCP 协议的平台，可直接把 GET 或 POST 接口配置成 HTTP Tool。"
          />
          <pre class="snippet">{{ httpSnippet }}</pre>
        </el-tab-pane>
      </el-tabs>

      <el-table :data="apiKeys" border stripe v-loading="loading" class="key-table">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="名称" min-width="160" />
        <el-table-column prop="username" label="归属用户" min-width="120" />
        <el-table-column label="API Key" min-width="320">
          <template #default="{ row }">
            <div class="token-cell">
              <el-input :model-value="row.token" readonly show-password />
              <el-button :icon="CopyDocument" @click="copyText(row.token)" />
            </div>
          </template>
        </el-table-column>
        <el-table-column label="权限" min-width="160">
          <template #default="{ row }">
            <el-tag v-for="scope in row.scopes || []" :key="scope" size="small">{{ scope }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.status === 'active' ? 'success' : 'info'">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="last_used_at" label="最近使用" min-width="170" />
        <el-table-column prop="created_at" label="创建时间" min-width="170" />
        <el-table-column label="操作" width="110" fixed="right">
          <template #default="{ row }">
            <el-button type="danger" link :icon="Delete" @click="removeKey(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" title="新建 MCP API Key" width="420px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="名称">
          <el-input v-model="form.name" maxlength="128" placeholder="例如：大模型实例状态查询" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveKey">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { CopyDocument, Delete, Plus } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";

import { createMcpApiKey, deleteMcpApiKey, listMcpApiKeys } from "../api/modules/mcp_platform";

const loading = ref(false);
const saving = ref(false);
const dialogVisible = ref(false);
const apiKeys = ref([]);
const form = reactive({ name: "" });

const remoteMcpEndpoint = computed(() => `${window.location.origin}/api/v1/mcp`);
const statusEndpoint = computed(() => `${window.location.origin}/api/v1/mcp/instance-status`);
const toolEndpoint = computed(() => `${window.location.origin}/api/v1/mcp/tools/dbms_get_latest_instance_status`);
const serverScript = "D:\\\\个人项目空间\\\\DBMS\\\\backend\\\\mcp_server.py";
const remoteHttpConfigSnippet = computed(() => `Claude Code:
claude mcp add --transport http --scope user dbms ${remoteMcpEndpoint.value} --header "X-API-Key: mcp_xxx"

JSON:
${JSON.stringify({
  mcpServers: {
    dbms: {
      type: "http",
      url: remoteMcpEndpoint.value,
      headers: {
        "X-API-Key": "替换为页面生成的 mcp_xxx",
      },
    },
  },
}, null, 2)}`);
const stdioConfigSnippet = computed(() => JSON.stringify({
  mcpServers: {
    dbms: {
      command: "python",
      args: [serverScript],
      env: {
        DBMS_BASE_URL: window.location.origin,
        DBMS_MCP_API_KEY: "替换为页面生成的 mcp_xxx",
      },
    },
  },
}, null, 2));
const toolSchemaSnippet = computed(() => JSON.stringify({
  name: "dbms_get_latest_instance_status",
  description: "查询 DBMS 内所有数据库实例的最新状态明细",
  arguments: {
    db_type: "mysql | mongodb | redis | doris，可选",
    business_line: "业务线，可选",
    environment: "环境，可选",
    cluster_id: "集群ID，可选",
    cluster_name: "集群名称，可选",
    unhealthy_only: "仅返回异常实例，可选",
    include_raw_payload: "返回原始采集数据，可选",
  },
}, null, 2));
const httpSnippet = computed(() => `curl -H "X-API-Key: mcp_xxx" "${statusEndpoint.value}"

curl -X POST -H "Content-Type: application/json" -H "X-API-Key: mcp_xxx" -d '{"db_type":"mysql","unhealthy_only":true}' "${toolEndpoint.value}"`);

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    ElMessage.success("已复制");
  } catch {
    ElMessage.warning("复制失败，请手动复制");
  }
}

async function loadKeys() {
  loading.value = true;
  try {
    const { data } = await listMcpApiKeys();
    apiKeys.value = data?.data || [];
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载 API Key 失败");
  } finally {
    loading.value = false;
  }
}

function openCreateDialog() {
  form.name = "";
  dialogVisible.value = true;
}

async function saveKey() {
  saving.value = true;
  try {
    const { data } = await createMcpApiKey({ name: form.name });
    if (data?.data) {
      apiKeys.value.unshift(data.data);
    }
    dialogVisible.value = false;
    ElMessage.success("创建成功");
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "创建 API Key 失败");
  } finally {
    saving.value = false;
  }
}

async function removeKey(row) {
  try {
    await ElMessageBox.confirm(`确认删除 ${row.name || row.id}？`, "删除确认", { type: "warning" });
    await deleteMcpApiKey(row.id);
    apiKeys.value = apiKeys.value.filter((item) => item.id !== row.id);
    ElMessage.success("已删除");
  } catch (error) {
    if (error === "cancel" || error === "close") return;
    ElMessage.error(error.response?.data?.message || "删除失败");
  }
}

onMounted(loadKeys);
</script>

<style scoped>
.page {
  padding: 20px;
}
.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.endpoint-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 16px;
}
.endpoint-title {
  margin-bottom: 8px;
  font-weight: 600;
}
.capabilities {
  margin-bottom: 16px;
}
.access-tabs {
  margin-bottom: 16px;
}
.tips {
  margin-bottom: 12px;
}
.snippet-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 0.9fr);
  gap: 16px;
}
.snippet {
  margin: 0;
  padding: 12px;
  max-height: 360px;
  overflow: auto;
  border: 1px solid var(--el-border-color);
  border-radius: 6px;
  background: #0f172a;
  color: #e5e7eb;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}
.key-table {
  width: 100%;
}
.token-cell {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 36px;
  gap: 8px;
  align-items: center;
}
@media (max-width: 860px) {
  .endpoint-grid {
    grid-template-columns: 1fr;
  }
  .snippet-grid {
    grid-template-columns: 1fr;
  }
}
</style>
