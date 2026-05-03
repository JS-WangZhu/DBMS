<template>
  <el-card>
    <template #header>
      <div class="header-row">
        <span>MySQL 连接管理</span>
        <div class="actions">
          <el-select v-model="selectedBusinessLine" clearable placeholder="选择项目" class="filter-select">
            <el-option v-for="line in businessLineOptions" :key="line" :label="line" :value="line" />
          </el-select>
          <el-select v-model="selectedEnvironment" clearable placeholder="选择环境" class="filter-select">
            <el-option v-for="env in environmentOptions" :key="env" :label="env" :value="env" />
          </el-select>
          <el-select v-model="selectedStatus" clearable placeholder="连接状态" class="filter-select">
            <el-option label="正常" value="ok" />
            <el-option label="异常" value="error" />
          </el-select>
          <el-select v-model="selectedClusterId" clearable placeholder="选择集群" class="filter-select">
            <el-option v-for="cluster in clusterOptions" :key="cluster.id" :label="clusterOptionLabel(cluster)" :value="cluster.id" />
          </el-select>
          <el-input v-model.trim="keyword" placeholder="关键字" clearable style="width: 200px" />
          <el-button @click="loadData">刷新</el-button>
        </div>
      </div>
    </template>

    <el-table :data="pagedRows" v-loading="loading" stripe>
      <el-table-column prop="business_line" label="项目" min-width="120" />
      <el-table-column prop="environment" label="环境" min-width="120" />
      <el-table-column prop="name" label="集群" min-width="140" />
      <el-table-column prop="ha_domain" label="高可用域名" min-width="180" show-overflow-tooltip />
      <el-table-column label="解析IP" min-width="130">
        <template #default="scope">{{ scope.row.ha_status_json?.resolved_ip || "-" }}</template>
      </el-table-column>
      <el-table-column label="连接状态" width="100">
        <template #default="scope">
          <el-tag :type="scope.row.ha_status_json?.ok ? 'success' : 'danger'">{{ scope.row.ha_status_json?.ok ? "正常" : "异常" }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="命中实例" min-width="150">
        <template #default="scope">{{ scope.row.ha_status_json?.matched_instance_name || "-" }}</template>
      </el-table-column>
      <el-table-column label="主库可写" width="100">
        <template #default="scope">
          <el-tag :type="scope.row.ha_status_json?.matched_writable ? 'success' : 'info'">{{ scope.row.ha_status_json?.matched_writable ? "是" : "否" }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="最近检查" min-width="170">
        <template #default="scope">{{ formatRelativeTime(scope.row.ha_status_json?.checked_at) }}</template>
      </el-table-column>
      <el-table-column label="原因" min-width="220" show-overflow-tooltip>
        <template #default="scope">{{ scope.row.ha_status_json?.reason || "-" }}</template>
      </el-table-column>
      <el-table-column label="操作" width="320" fixed="right">
        <template #default="scope">
          <el-button link type="primary" @click="openEdit(scope.row)">编辑</el-button>
          <el-button link type="success" :disabled="!scope.row.ha_switch_enabled" @click="openSwitchDialog(scope.row)">高可用切换</el-button>
          <el-button link type="warning" @click="doCheck(scope.row)">校验</el-button>
          <el-button link type="success" @click="openTopologyHistoryDialog(scope.row)">拓扑变更历史</el-button>
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

    <el-dialog v-model="dialogVisible" title="编辑高可用域名" width="520px">
      <el-form :model="form" label-width="100px">
        <el-form-item label="项目"><el-input :model-value="currentCluster?.business_line || currentCluster?.namespace || '-'" disabled /></el-form-item>
        <el-form-item label="环境"><el-input :model-value="currentCluster?.environment || '-'" disabled /></el-form-item>
        <el-form-item label="集群"><el-input :model-value="currentCluster?.name || '-'" disabled /></el-form-item>
        <el-form-item label="高可用域名"><el-input v-model.trim="form.ha_domain" placeholder="可填域名或IP" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="switchDialogVisible" title="高可用主从切换" width="1600px" top="2vh">
      <div v-loading="topologyLoading" class="switch-dialog-body">
        <el-descriptions :column="3" border>
          <el-descriptions-item label="项目">{{ topologyCluster?.business_line || topologyCluster?.namespace || "-" }}</el-descriptions-item>
          <el-descriptions-item label="环境">{{ topologyCluster?.environment || "-" }}</el-descriptions-item>
          <el-descriptions-item label="集群">{{ topologyCluster?.name || "-" }}</el-descriptions-item>
          <el-descriptions-item label="高可用域名">{{ topologyData.ha_domain || "-" }}</el-descriptions-item>
          <el-descriptions-item label="HA切换">
            <el-tag :type="topologyCluster?.ha_switch_enabled ? 'success' : 'info'">
              {{ topologyCluster?.ha_switch_enabled ? "已启用" : "未启用" }}
            </el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="当前主库">{{ topologyData.current_master_instance_name || "-" }}</el-descriptions-item>
          <el-descriptions-item label="脚本配置">
            <el-tag :type="topologyData.switch_script_configured ? 'success' : 'danger'">
              {{ topologyData.switch_script_configured ? "已配置" : "未配置" }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <div class="switch-toolbar">
          <el-radio-group v-model="switchForm.switch_type">
            <el-radio-button label="normal">在线切换</el-radio-button>
            <el-radio-button label="failure" :disabled="!!failureSwitchBlockedReason">故障切换</el-radio-button>
            <el-radio-button label="repair" :disabled="repairableNodes.length === 0">集群修复</el-radio-button>
          </el-radio-group>
          <el-select
            v-model="currentTargetValue"
            :multiple="switchForm.switch_type === 'repair'"
            :collapse-tags="switchForm.switch_type === 'repair'"
            :collapse-tags-tooltip="switchForm.switch_type === 'repair'"
            :placeholder="targetSelectPlaceholder"
            clearable
            class="target-select"
          >
            <el-option
              v-for="node in selectableTargetNodes"
              :key="node.instance_id"
              :label="targetOptionLabel(node)"
              :value="node.instance_id"
            />
          </el-select>
          <el-button @click="openHistoryDialog">切换历史</el-button>
          <el-button @click="refreshTopology">刷新拓扑</el-button>
        </div>

        <el-alert
          v-if="switchForm.switch_type === 'normal'"
          title="在线切换会先把原主库设置为只读，等待目标从库追平延迟后完成升主，并把原主库重挂到新主库。"
          type="info"
          show-icon
          :closable="false"
        />
        <el-alert
          v-else-if="switchForm.switch_type === 'failure'"
          title="故障切换只允许提升应用日志最新的从库，系统会自动锁定推荐节点。"
          type="warning"
          show-icon
          :closable="false"
        />
        <el-alert
          v-else
          title="集群修复会直接重建复制关系，使用 GTID AUTO_POSITION 并自动启动复制。"
          type="info"
          show-icon
          :closable="false"
        />
        <el-alert
          v-if="failureSwitchBlockedReason"
          :title="failureSwitchBlockedReason"
          type="warning"
          show-icon
          :closable="false"
        />
        <el-alert
          v-if="!topologyCluster?.ha_switch_enabled"
          title="当前集群未启用高可用切换，请先到集群管理中开启。"
          type="error"
          show-icon
          :closable="false"
        />

        <el-table :data="topologyData.nodes || []" stripe class="topology-table">
          <el-table-column prop="instance_name" label="实例" min-width="160" />
          <el-table-column label="地址" min-width="190">
            <template #default="scope">{{ formatNodeAddress(scope.row) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="scope">
              <el-tag :type="scope.row.ok ? 'success' : 'danger'">{{ scope.row.ok ? "可连接" : "异常" }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="角色" width="110">
            <template #default="scope">
              <el-tag v-if="scope.row.is_current_master" type="danger">当前主库</el-tag>
              <el-tag v-else-if="scope.row.replication_role === 'slave'" type="success">从库</el-tag>
              <el-tag v-else-if="scope.row.replication_role === 'master'" type="warning">主库</el-tag>
              <el-tag v-else>{{ scope.row.replication_role || "未知" }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="只读" width="90">
            <template #default="scope">
              <el-tag :type="scope.row.effective_read_only ? 'info' : 'success'">{{ scope.row.effective_read_only ? "是" : "否" }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="延迟(s)" width="90">
            <template #default="scope">{{ scope.row.seconds_behind_master ?? "-" }}</template>
          </el-table-column>
          <el-table-column label="复制源" min-width="170">
            <template #default="scope">{{ scope.row.replica_source_host ? `${scope.row.replica_source_host}:${scope.row.replica_source_port || ""}` : "-" }}</template>
          </el-table-column>
          <el-table-column label="GTID" width="90">
            <template #default="scope">{{ scope.row.gtid_mode || "-" }}</template>
          </el-table-column>
          <el-table-column label="DNS命中" width="90">
            <template #default="scope">
              <el-tag :type="scope.row.ha_domain_matched ? 'success' : 'info'">{{ scope.row.ha_domain_matched ? "是" : "否" }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="切换推荐" width="100">
            <template #default="scope">
              <el-tag v-if="scope.row.recommended_for_failure" type="warning">推荐</el-tag>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column label="推荐原因" min-width="280" show-overflow-tooltip>
            <template #default="scope">{{ scope.row.failure_reason || "-" }}</template>
          </el-table-column>
          <el-table-column label="异常原因" min-width="220" show-overflow-tooltip>
            <template #default="scope">{{ scope.row.error || "-" }}</template>
          </el-table-column>
        </el-table>

        <el-card v-if="switchLogs.length || switchResult" class="result-card" shadow="never">
          <template #header>{{ switchSubmitting ? "切换执行日志" : "最近一次切换日志" }}</template>
          <el-table :data="switchLogs" size="small" stripe max-height="360">
            <el-table-column prop="timestamp" label="时间" width="180">
              <template #default="scope">{{ formatLogTime(scope.row.timestamp) }}</template>
            </el-table-column>
            <el-table-column prop="step" label="步骤" width="180" />
            <el-table-column prop="message" label="结果" min-width="240" />
          </el-table>
        </el-card>
      </div>

      <template #footer>
        <el-button @click="switchDialogVisible = false">关闭</el-button>
        <el-button type="primary" :loading="switchSubmitting" :disabled="switchActionDisabled" @click="submitHaSwitch">
          {{ switchActionButtonText }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="historyDialogVisible" title="切换历史" width="1200px">
      <div class="history-toolbar">
        <el-input
          v-model.trim="historyKeyword"
          placeholder="关键字过滤"
          clearable
          style="width: 280px"
          @keyup.enter="loadSwitchHistory(1)"
        />
        <el-button @click="loadSwitchHistory(1)">查询</el-button>
      </div>
      <el-table :data="historyRows" v-loading="historyLoading" stripe>
        <el-table-column prop="created_at" label="时间" width="180">
          <template #default="scope">{{ formatLogTime(scope.row.created_at) }}</template>
        </el-table-column>
        <el-table-column label="结果" width="90">
          <template #default="scope">
            <el-tag :type="scope.row.success ? 'success' : 'danger'">{{ scope.row.success ? "成功" : "失败" }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="动作类型" width="110">
          <template #default="scope">{{ switchTypeLabel(scope.row.switch_type) }}</template>
        </el-table-column>
        <el-table-column label="目标实例" min-width="220" show-overflow-tooltip>
          <template #default="scope">{{ formatHistoryTargets(scope.row) }}</template>
        </el-table-column>
        <el-table-column prop="operator_username" label="操作人" width="120" />
        <el-table-column prop="switch_script_name" label="切换脚本" min-width="150" show-overflow-tooltip />
        <el-table-column label="执行命令" min-width="260" show-overflow-tooltip>
          <template #default="scope">{{ formatHistoryCommand(scope.row.switch_command) }}</template>
        </el-table-column>
        <el-table-column prop="error" label="错误信息" min-width="220" show-overflow-tooltip>
          <template #default="scope">{{ scope.row.error || "-" }}</template>
        </el-table-column>
      </el-table>
      <div class="pagination-wrap">
        <el-pagination
          background
          layout="total, prev, pager, next"
          :total="historyPager.total"
          :current-page="historyPager.page"
          :page-size="historyPager.page_size"
          @current-change="loadSwitchHistory"
        />
      </div>
      <template #footer>
        <el-button @click="historyDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="topoHistoryDialogVisible" title="MySQL 拓扑变更历史" width="1200px" top="5vh">
      <div v-loading="topoHistoryLoading">
        <el-table :data="topoHistoryData.items" stripe>
          <el-table-column label="变更时间" min-width="180">
            <template #default="scope">{{ formatBeijingTime(scope.row.changed_at) }}</template>
          </el-table-column>
          <el-table-column label="HA域名" min-width="180" show-overflow-tooltip>
            <template #default="scope">{{ scope.row.topology?.ha_domain || "-" }}</template>
          </el-table-column>
          <el-table-column label="总节点" width="90">
            <template #default="scope">{{ scope.row.topology?.total_members ?? "-" }}</template>
          </el-table-column>
          <el-table-column label="M / S / RO" width="130">
            <template #default="scope">
              {{ scope.row.topology?.master_count ?? 0 }} / {{ scope.row.topology?.slave_count ?? 0 }} / {{ scope.row.topology?.read_only_count ?? 0 }}
            </template>
          </el-table-column>
          <el-table-column label="成员" min-width="420">
            <template #default="scope">
              <el-tag
                v-for="m in scope.row.topology?.members || []"
                :key="m.host"
                :type="mysqlRoleTagType(m.role)"
                class="member-tag"
              >
                {{ m.host }} [{{ m.role }}]<span v-if="m.replica_source"> ← {{ m.replica_source }}</span>
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="指纹" width="110">
            <template #default="scope">{{ (scope.row.fingerprint || "").slice(0, 8) }}</template>
          </el-table-column>
        </el-table>
        <div class="pagination-wrap">
          <el-pagination
            background
            layout="total, prev, pager, next, jumper"
            :total="topoHistoryData.total"
            :current-page="topoHistoryData.page"
            :page-size="topoHistoryData.page_size"
            @current-change="onTopoHistoryPageChange"
          />
        </div>
      </div>
      <template #footer>
        <el-button @click="topoHistoryDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { computed, nextTick, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";

import {
  checkClusterHa,
  getClusterHaTopology,
  listClusterHaSwitchHistory,
  listClusterTopologyHistory,
  listClusters,
  updateCluster,
} from "../api/modules/clusters";
import { formatBeijingTime } from "../utils/time";

const loading = ref(false);
const saving = ref(false);
const rows = ref([]);
const keyword = ref("");
const selectedBusinessLine = ref("");
const selectedEnvironment = ref("");
const selectedStatus = ref("");
const selectedClusterId = ref(null);
const pager = reactive({
  page: 1,
  page_size: 20,
});

const dialogVisible = ref(false);
const currentCluster = ref(null);
const form = ref({ ha_domain: "" });

const switchDialogVisible = ref(false);
const topologyLoading = ref(false);
const switchSubmitting = ref(false);
const topologyCluster = ref(null);
const topologyData = reactive({
  ha_domain: "",
  current_master_instance_id: null,
  current_master_instance_name: "",
  ha_resolved_servers: [],
  switch_script_configured: false,
  nodes: [],
});
const switchForm = reactive({
  switch_type: "normal",
  target_instance_id: null,
  target_instance_ids: [],
});
const switchResult = ref(null);
const switchLogs = ref([]);
const historyDialogVisible = ref(false);
const historyLoading = ref(false);
const historyKeyword = ref("");
const historyRows = ref([]);
const historyPager = reactive({
  page: 1,
  page_size: 10,
  total: 0,
});

const topoHistoryDialogVisible = ref(false);
const topoHistoryLoading = ref(false);
const topoHistoryCluster = ref(null);
const topoHistoryData = reactive({
  items: [],
  total: 0,
  page: 1,
  page_size: 10,
});

function matchesStatus(row) {
  if (!selectedStatus.value) {
    return true;
  }
  const ok = !!row.ha_status_json?.ok;
  return selectedStatus.value === "ok" ? ok : !ok;
}

function matchesFilters(row, excludeKey = "") {
  if (!row) {
    return false;
  }
  if (excludeKey !== "business_line" && selectedBusinessLine.value && (row.business_line || row.namespace) !== selectedBusinessLine.value) {
    return false;
  }
  if (excludeKey !== "environment" && selectedEnvironment.value && row.environment !== selectedEnvironment.value) {
    return false;
  }
  if (excludeKey !== "status" && !matchesStatus(row)) {
    return false;
  }
  if (excludeKey !== "cluster_id" && selectedClusterId.value && row.id !== selectedClusterId.value) {
    return false;
  }
  return true;
}

const businessLineOptions = computed(() => {
  const values = new Set(
    rows.value
      .filter((row) => matchesFilters(row, "business_line"))
      .map((row) => row.business_line || row.namespace)
      .filter(Boolean),
  );
  return Array.from(values).sort();
});

const environmentOptions = computed(() => {
  const values = new Set(
    rows.value
      .filter((row) => matchesFilters(row, "environment"))
      .map((row) => row.environment)
      .filter(Boolean),
  );
  return Array.from(values).sort();
});

const clusterOptions = computed(() => rows.value.filter((row) => matchesFilters(row, "cluster_id")));

const displayRows = computed(() => {
  const kw = keyword.value.trim().toLowerCase();
  return rows.value.filter((row) => {
    if (!matchesFilters(row)) {
      return false;
    }
    if (!kw) {
      return true;
    }
    const text = `${row.business_line || row.namespace || ""} ${row.environment || ""} ${row.name || ""} ${row.ha_domain || ""} ${row.ha_status_json?.resolved_ip || ""}`.toLowerCase();
    return text.includes(kw);
  });
});

const pagedRows = computed(() => {
  const start = (pager.page - 1) * pager.page_size;
  return displayRows.value.slice(start, start + pager.page_size);
});

const repairableNodes = computed(() => {
  const nodes = topologyData.nodes || [];
  return nodes.filter((node) => !node.is_current_master && node.ok && !node.ha_domain_matched);
});

const selectableTargetNodes = computed(() => {
  const nodes = topologyData.nodes || [];
  if (switchForm.switch_type === "failure") {
    return nodes.filter((node) => !node.is_current_master && node.recommended_for_failure);
  }
  if (switchForm.switch_type === "repair") {
    return repairableNodes.value;
  }
  return nodes.filter((node) => !node.is_current_master && node.ok && node.replication_role === "slave");
});

const targetSelectPlaceholder = computed(() => {
  if (switchForm.switch_type === "repair") {
    return "选择需要修复的节点";
  }
  return "选择目标实例";
});

const currentTargetValue = computed({
  get() {
    return switchForm.switch_type === "repair" ? switchForm.target_instance_ids : switchForm.target_instance_id;
  },
  set(value) {
    if (switchForm.switch_type === "repair") {
      switchForm.target_instance_ids = Array.isArray(value) ? value : [];
    } else {
      switchForm.target_instance_id = value ?? null;
    }
  },
});

const failureSwitchBlockedReason = computed(() => getFailureSwitchBlockedReason(topologyData.nodes || [], topologyData.current_master_instance_id));

const switchActionDisabled = computed(() => {
  if (topologyLoading.value || switchSubmitting.value) {
    return true;
  }
  if (!topologyCluster.value?.ha_switch_enabled) {
    return true;
  }
  if (switchForm.switch_type === "repair") {
    return repairableNodes.value.length === 0 || !switchForm.target_instance_ids.length;
  }
  if (!topologyData.switch_script_configured) {
    return true;
  }
  if (switchForm.switch_type === "failure") {
    if (failureSwitchBlockedReason.value) {
      return true;
    }
    return selectableTargetNodes.value.length === 0 || !switchForm.target_instance_id;
  }
  return !switchForm.target_instance_id;
});

async function loadData() {
  loading.value = true;
  try {
    const { data } = await listClusters("mysql");
    rows.value = (data.data || []).map((row) => ({ ...row, ha_status_json: row.ha_status_json || {} }));
    if ((pager.page - 1) * pager.page_size >= displayRows.value.length) {
      pager.page = 1;
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载连接管理失败");
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

function clusterOptionLabel(row) {
  const parts = [row.business_line || row.namespace || "", row.environment || "", row.name || ""].filter(Boolean);
  return parts.length ? parts.join("/") : row.name || "-";
}

function targetOptionLabel(node) {
  const suffix = node.recommended_for_failure ? " [切换推荐]" : "";
  return `${node.instance_name} (${formatNodeAddress(node)})${suffix}`;
}

function switchTypeLabel(type) {
  return {
    normal: "在线切换",
    failure: "故障切换",
    promote: "推广",
    repair: "集群修复",
  }[type] || type || "-";
}

const switchActionButtonText = computed(() => {
  return switchForm.switch_type === "repair" ? "执行修复" : "执行切换";
});

function formatRelativeTime(value) {
  if (!value) {
    return "-";
  }
  const target = new Date(value);
  if (Number.isNaN(target.getTime())) {
    return value;
  }
  const diffSeconds = Math.max(0, Math.floor((Date.now() - target.getTime()) / 1000));
  if (diffSeconds < 60) {
    return `${diffSeconds}秒之前`;
  }
  const diffMinutes = Math.floor(diffSeconds / 60);
  if (diffMinutes < 60) {
    return `${diffMinutes}分钟之前`;
  }
  const diffHours = Math.floor(diffMinutes / 60);
  if (diffHours < 24) {
    return `${diffHours}小时之前`;
  }
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}天之前`;
}

function formatNodeAddress(node) {
  return `${node.host || "-"} / ${node.resolved_ip || "-"}:${node.port || "-"}`;
}

function formatLogTime(value) {
  if (!value) {
    return "-";
  }
  const target = new Date(value);
  if (Number.isNaN(target.getTime())) {
    return value;
  }
  return target.toLocaleString("zh-CN", {
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function formatHistoryCommand(command) {
  if (!Array.isArray(command) || !command.length) {
    return "-";
  }
  return command.join(" ");
}

function formatHistoryTargets(row) {
  if (Array.isArray(row?.target_instance_names) && row.target_instance_names.length) {
    return row.target_instance_names.join("、");
  }
  return row?.target_instance_name || row?.target_instance_id || "-";
}

function getFailureSwitchBlockedReason(nodes, currentMasterId) {
  if (!Array.isArray(nodes) || !nodes.length || !currentMasterId) {
    return "";
  }
  const currentMaster = nodes.find((node) => node.instance_id === currentMasterId);
  if (!currentMaster) {
    return "";
  }
  const masterHealthy = currentMaster.ok && currentMaster.replication_role === "master" && currentMaster.effective_read_only === false;
  if (!masterHealthy) {
    return "";
  }
  for (const node of nodes) {
    if (!node.ok) {
      return "";
    }
    if (node.instance_id === currentMasterId) {
      continue;
    }
    if (node.replication_role !== "slave") {
      return "";
    }
    if (node.replica_io_running === false || node.replica_sql_running === false) {
      return "";
    }
  }
  return "当前集群所有节点状态正常，请使用在线切换";
}

function appendSwitchLog(entry) {
  if (!entry) {
    return;
  }
  switchLogs.value.push({
    timestamp: entry.timestamp || new Date().toISOString(),
    step: entry.step || "-",
    message: entry.message || "-",
  });
  nextTick(() => {
    const body = document.querySelector(".result-card .el-table__body-wrapper");
    if (body) {
      body.scrollTop = body.scrollHeight;
    }
  });
}

function openEdit(row) {
  currentCluster.value = row;
  form.value = { ha_domain: row.ha_domain || "" };
  dialogVisible.value = true;
}

async function onSave() {
  if (!currentCluster.value) return;
  saving.value = true;
  try {
    await updateCluster(currentCluster.value.id, { ha_domain: form.value.ha_domain || "" });
    dialogVisible.value = false;
    await loadData();
    ElMessage.success("保存成功");
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "保存失败");
  } finally {
    saving.value = false;
  }
}

async function doCheck(row) {
  try {
    await checkClusterHa(row.id);
    await loadData();
    ElMessage.success("校验完成");
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "校验失败");
  }
}

function resetTopologyData() {
  topologyData.ha_domain = "";
  topologyData.current_master_instance_id = null;
  topologyData.current_master_instance_name = "";
  topologyData.ha_resolved_servers = [];
  topologyData.switch_script_configured = false;
  topologyData.nodes = [];
}

function syncDefaultTarget() {
  if (switchForm.switch_type === "failure" && failureSwitchBlockedReason.value) {
    switchForm.switch_type = "normal";
  }
  const candidates = selectableTargetNodes.value;
  if (!candidates.length) {
    switchForm.target_instance_id = null;
    switchForm.target_instance_ids = [];
    return;
  }
  if (switchForm.switch_type === "repair") {
    const candidateIds = candidates.map((node) => node.instance_id);
    const validSelected = switchForm.target_instance_ids.filter((id) => candidateIds.includes(id));
    switchForm.target_instance_ids = validSelected.length ? validSelected : candidateIds;
    switchForm.target_instance_id = null;
    return;
  }
  const exists = candidates.some((node) => node.instance_id === switchForm.target_instance_id);
  if (!exists) {
    switchForm.target_instance_id = candidates[0].instance_id;
  }
  switchForm.target_instance_ids = [];
}

async function fetchTopology(clusterId) {
  topologyLoading.value = true;
  try {
    const { data } = await getClusterHaTopology(clusterId);
    const payload = data.data || {};
    topologyData.ha_domain = payload.ha_domain || "";
    topologyData.current_master_instance_id = payload.current_master_instance_id || null;
    topologyData.current_master_instance_name = payload.current_master_instance_name || "";
    topologyData.ha_resolved_servers = payload.ha_resolved_servers || [];
    topologyData.switch_script_configured = !!payload.switch_script_configured;
    topologyData.nodes = payload.nodes || [];
    syncDefaultTarget();
  } catch (error) {
    resetTopologyData();
    throw error;
  } finally {
    topologyLoading.value = false;
  }
}

async function openSwitchDialog(row) {
  topologyCluster.value = row;
  switchDialogVisible.value = true;
  historyDialogVisible.value = false;
  historyKeyword.value = "";
  historyRows.value = [];
  historyPager.page = 1;
  historyPager.total = 0;
  switchResult.value = null;
  switchLogs.value = [];
  switchForm.switch_type = "normal";
  switchForm.target_instance_id = null;
  switchForm.target_instance_ids = [];
  resetTopologyData();
  try {
    await fetchTopology(row.id);
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载拓扑失败");
  }
}

async function refreshTopology() {
  if (!topologyCluster.value) {
    return;
  }
  try {
    await fetchTopology(topologyCluster.value.id);
    ElMessage.success("拓扑已刷新");
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "刷新拓扑失败");
  }
}

async function loadSwitchHistory(page = historyPager.page) {
  if (!topologyCluster.value?.id) {
    return;
  }
  historyLoading.value = true;
  try {
    const { data } = await listClusterHaSwitchHistory(
      topologyCluster.value.id,
      page,
      historyPager.page_size,
      { keyword: historyKeyword.value },
    );
    const payload = data?.data || {};
    historyRows.value = payload.items || [];
    historyPager.page = payload.page || page;
    historyPager.total = payload.total || 0;
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载切换历史失败");
  } finally {
    historyLoading.value = false;
  }
}

async function openHistoryDialog() {
  if (!topologyCluster.value?.id) {
    return;
  }
  historyDialogVisible.value = true;
  await loadSwitchHistory(1);
}

async function loadTopologyHistory(page = topoHistoryData.page) {
  if (!topoHistoryCluster.value?.id) {
    return;
  }
  topoHistoryLoading.value = true;
  try {
    const { data } = await listClusterTopologyHistory(
      topoHistoryCluster.value.id,
      page,
      topoHistoryData.page_size,
    );
    const payload = data?.data || {};
    topoHistoryData.items = payload.items || [];
    topoHistoryData.total = payload.total || 0;
    topoHistoryData.page = payload.page || page;
    topoHistoryData.page_size = payload.page_size || topoHistoryData.page_size;
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载拓扑变更历史失败");
  } finally {
    topoHistoryLoading.value = false;
  }
}

async function openTopologyHistoryDialog(row) {
  topoHistoryCluster.value = row;
  topoHistoryDialogVisible.value = true;
  topoHistoryData.items = [];
  topoHistoryData.total = 0;
  topoHistoryData.page = 1;
  await loadTopologyHistory(1);
}

function onTopoHistoryPageChange(page) {
  loadTopologyHistory(Number(page) || 1);
}

function mysqlRoleTagType(role) {
  const key = String(role || "").toLowerCase();
  if (key === "master") return "danger";
  if (key === "slave" || key === "replica") return "success";
  if (key === "read_only") return "warning";
  return "info";
}

async function submitHaSwitch() {
  if (!topologyCluster.value) {
    return;
  }
  if (switchForm.switch_type === "repair" && !switchForm.target_instance_ids.length) {
    ElMessage.warning("请选择需要修复的节点");
    return;
  }
  if (switchForm.switch_type !== "repair" && !switchForm.target_instance_id) {
    ElMessage.warning("请选择目标实例");
    return;
  }
  const targetNode = (topologyData.nodes || []).find((node) => node.instance_id === switchForm.target_instance_id);
  const repairTargetNodes = (topologyData.nodes || []).filter((node) => switchForm.target_instance_ids.includes(node.instance_id));
  const modeLabel = switchTypeLabel(switchForm.switch_type);
  const clusterLabel = [topologyCluster.value.business_line || topologyCluster.value.namespace, topologyCluster.value.environment, topologyCluster.value.name]
    .filter(Boolean)
    .join("/");
  const targetSummary = switchForm.switch_type === "repair"
    ? repairTargetNodes.map((node) => node.instance_name || node.instance_id).join("、")
    : targetNode?.instance_name || switchForm.target_instance_id;
  try {
    await ElMessageBox.confirm(
      `确认执行${modeLabel}吗？\n集群：${clusterLabel || "-"}\n目标实例：${targetSummary || "-"}`,
      "二次确认",
      {
        type: "warning",
        confirmButtonText: "确认执行",
        cancelButtonText: "取消",
      },
    );
  } catch (error) {
    if (error === "cancel" || error === "close") {
      return;
    }
    throw error;
  }
  switchSubmitting.value = true;
  switchResult.value = null;
  switchLogs.value = [];
  try {
    const payload = {
      switch_type: switchForm.switch_type,
      target_instance_id: switchForm.target_instance_id,
      target_instance_ids: switchForm.target_instance_ids,
    };
    const token = localStorage.getItem("dbms_token");
    const response = await fetch(`/api/v1/clusters/${topologyCluster.value.id}/ha/switch/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: token ? `Bearer ${token}` : "",
      },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      let errorMessage = "执行操作失败";
      try {
        const errorData = await response.json();
        errorMessage = errorData.message || errorMessage;
      } catch {
        // ignore json parse errors
      }
      throw new Error(errorMessage);
    }

    if (!response.body) {
      throw new Error("操作流返回为空");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let completedMessage = `${modeLabel}执行成功`;

    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        const trimmedLine = line.trim();
        if (!trimmedLine.startsWith("data: ")) {
          continue;
        }
        const event = JSON.parse(trimmedLine.slice(6));
        if (event.type === "started") {
          appendSwitchLog({
            timestamp: event.timestamp,
            step: "start",
            message: event.message || `开始执行${modeLabel}`,
          });
          continue;
        }
        if (event.type === "step") {
          appendSwitchLog(event.data);
          continue;
        }
        if (event.type === "completed") {
          completedMessage = event.message || completedMessage;
          switchResult.value = event.data || null;
          continue;
        }
        if (event.type === "error") {
          appendSwitchLog({
            timestamp: event.timestamp,
            step: "error",
            message: event.message || `执行${modeLabel}失败`,
          });
          throw new Error(event.message || `执行${modeLabel}失败`);
        }
      }
    }

    if (!switchResult.value) {
      throw new Error("操作未返回结果");
    }
    await fetchTopology(topologyCluster.value.id);
    if (historyDialogVisible.value) {
      await loadSwitchHistory(historyPager.page);
    }
    await loadData();
    ElMessage.success(completedMessage);
  } catch (error) {
    ElMessage.error(error.message || error.response?.data?.message || "执行操作失败");
  } finally {
    switchSubmitting.value = false;
  }
}

onMounted(loadData);

watch(
  () => [keyword.value, selectedBusinessLine.value, selectedEnvironment.value, selectedStatus.value, selectedClusterId.value],
  () => {
    pager.page = 1;
  },
);

watch(
  () => selectedBusinessLine.value,
  () => {
    const stillValid = !selectedEnvironment.value || environmentOptions.value.includes(selectedEnvironment.value);
    if (!stillValid) {
      selectedEnvironment.value = "";
    }
    const clusterValid = !selectedClusterId.value || clusterOptions.value.some((row) => row.id === selectedClusterId.value);
    if (!clusterValid) {
      selectedClusterId.value = null;
    }
  },
);

watch(
  () => selectedStatus.value,
  () => {
    const envValid = !selectedEnvironment.value || environmentOptions.value.includes(selectedEnvironment.value);
    if (!envValid) {
      selectedEnvironment.value = "";
    }
    const clusterValid = !selectedClusterId.value || clusterOptions.value.some((row) => row.id === selectedClusterId.value);
    if (!clusterValid) {
      selectedClusterId.value = null;
    }
  },
);

watch(
  () => selectedEnvironment.value,
  () => {
    const clusterValid = !selectedClusterId.value || clusterOptions.value.some((row) => row.id === selectedClusterId.value);
    if (!clusterValid) {
      selectedClusterId.value = null;
    }
  },
);

watch(
  () => switchForm.switch_type,
  () => {
    syncDefaultTarget();
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
  flex-wrap: wrap;
  gap: 8px;
}

.filter-select {
  width: 160px;
}

.pagination-wrap {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}

.switch-dialog-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.switch-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
}

.history-toolbar {
  margin-bottom: 12px;
  display: flex;
  gap: 8px;
  align-items: center;
}

.target-select {
  width: 360px;
}

.topology-table {
  width: 100%;
}

.result-card {
  margin-top: 8px;
}

.member-tag {
  margin-right: 6px;
  margin-bottom: 6px;
}
</style>
