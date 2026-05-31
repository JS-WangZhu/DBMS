<template>
  <el-card>
    <template #header>
      <div class="header-row">
        <span>{{ dbLabel }} 实例管理</span>
        <div class="actions">
          <el-select v-model="selectedBusinessLine" clearable placeholder="选择项目" class="namespace-select" size="small" @change="onBusinessLineChange">
            <el-option v-for="line in businessLines" :key="line" :label="line" :value="line" />
          </el-select>
          <el-select v-model="selectedEnvironment" clearable placeholder="选择环境" class="cluster-select" size="small" @change="onEnvironmentChange">
            <el-option v-for="env in environments" :key="env" :label="env" :value="env" />
          </el-select>
          <el-select v-model="selectedClusterId" clearable placeholder="选择集群" class="cluster-select" size="small" @change="onClusterSelectChange">
            <el-option v-for="c in filteredClusters" :key="c.id" :label="clusterOptionLabel(c)" :value="c.id" />
          </el-select>
          <el-button v-if="selectedClusterId" type="warning" size="small" :loading="healthChecking" @click="runClusterHealthCheck">
            集群检活
          </el-button>
          <el-input v-model="keyword" clearable placeholder="关键字搜索" class="keyword-input" size="small" />
          <el-button v-if="isAdmin" type="primary" size="small" @click="openCreateDialog">新增{{ dbLabel }}实例</el-button>
          <el-button size="small" @click="reloadAll(true)">刷新</el-button>
        </div>
      </div>
    </template>

    <div class="table-wrap">
      <el-table
        class="instance-table"
        :data="displayRows"
        v-loading="loading"
        stripe
        border
        size="small"
        table-layout="fixed"
        :row-class-name="tableRowClassName"
        @row-click="onRowClick"
        @row-mouse-enter="onRowMouseEnter"
        @row-mouse-leave="onRowMouseLeave"
      >
        <el-table-column prop="id" label="ID" min-width="50" />
        <el-table-column prop="name" label="实例名" min-width="120" class-name="name-col" />
        <el-table-column
          label="所属集群"
          class-name="cluster-col"
          min-width="100"
          show-overflow-tooltip
          :filters="clusterFilters"
          :filter-method="filterByCluster"
          :filter-multiple="false"
        >
          <template #default="scope">
            <div class="cluster-cell">
              <template v-for="(part, index) in resolveClusterParts(scope.row.cluster_id)" :key="`${scope.row.id}-cluster-${index}`">
                <div class="cluster-part">
                  <span class="cluster-label">{{ part.label }}：</span>
                  <span class="cluster-value">{{ part.value }}</span>
                </div>
              </template>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="地址" min-width="120" class-name="address-col" show-overflow-tooltip>
          <template #default="scope">
            <div class="address-cell">
              <div class="address-domain">{{ rowDomain(scope.row) }}</div>
              <div class="address-ip">{{ rowAddress(scope.row) }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column
          prop="port"
          label="端口"
          min-width="70"
          :filters="portFilters"
          :filter-method="filterByPort"
          :filter-multiple="false"
        />
        <el-table-column
          label="运行情况"
          min-width="78"
          :filters="runningFilters"
          :filter-method="filterByRunning"
          :filter-multiple="false"
        >
          <template #default="scope">
            <el-tag :type="runningTagType(rowRunningStatus(scope.row))">
              {{ runningText(rowRunningStatus(scope.row)) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="dbType === 'mysql'" label="应用连接" min-width="78">
          <template #default="scope">
            <el-tag v-if="appConnText(scope.row) !== '-'" :type="appConnTagType(scope.row)">{{ appConnText(scope.row) }}</el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column v-if="dbType === 'mongodb'" label="主从角色" min-width="78">
          <template #default="scope">
            <el-tag :type="mongoRoleTagType(mongoRole(scope.row))">{{ mongoRoleText(mongoRole(scope.row)) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="dbType === 'redis'" label="主从角色" min-width="78">
          <template #default="scope">
            <el-tag :type="redisRoleTagType(redisRole(scope.row))">{{ redisRoleText(redisRole(scope.row)) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="dbType === 'redis'" label="高可用模式" min-width="92">
          <template #default="scope">
            <el-tag :type="redisHaModeTagType(redisHaMode(scope.row))">{{ redisHaModeText(redisHaMode(scope.row)) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column
          v-if="dbType === 'redis'"
          label="复制源信息"
          width="156"
          class-name="redis-repl-source-col"
          show-overflow-tooltip
        >
          <template #default="scope">
            {{ redisReplicationSource(scope.row) }}
          </template>
        </el-table-column>
        <el-table-column v-if="dbType === 'mongodb'" label="版本" min-width="70">
          <template #default="scope">
            {{ rowVersion(scope.row) }}
          </template>
        </el-table-column>
        <el-table-column v-if="dbType === 'redis'" label="版本" min-width="70">
          <template #default="scope">
            {{ rowVersion(scope.row) }}
          </template>
        </el-table-column>
        <el-table-column v-if="dbType === 'redis'" label="实例内存使用率" min-width="132" show-overflow-tooltip>
          <template #default="scope">
            <div v-if="redisContainerMemoryText(scope.row) !== '-'" class="redis-memory-cell">
              <el-tag size="small" :class="usageTagClass(redisContainerMemoryValue(scope.row))">
                {{ redisContainerMemoryText(scope.row) }}
              </el-tag>
              <el-tag size="small" class="redis-memory-subtag">
                {{ redisContainerMemoryPercentText(scope.row) }}
              </el-tag>
            </div>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="CPU" min-width="50">
          <template #default="scope">
            <el-tag v-if="hostCpuText(scope.row) !== '-'" size="small" :class="usageTagClass(hostCpuValue(scope.row))">
              {{ hostCpuText(scope.row) }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="内存" min-width="50">
          <template #default="scope">
            <el-tag v-if="hostMemoryText(scope.row) !== '-'" size="small" :class="usageTagClass(hostMemoryValue(scope.row))">
              {{ hostMemoryText(scope.row) }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="数据盘" min-width="50">
          <template #default="scope">
            <el-tag v-if="hostDiskText(scope.row) !== '-'" size="small" :class="usageTagClass(hostDiskValue(scope.row))">
              {{ hostDiskText(scope.row) }}
            </el-tag>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column
          label="物理机地址"
          width="100"
          class-name="physical-col"
          show-overflow-tooltip
          :filters="physicalAddressFilters"
          :filter-method="filterByPhysicalAddress"
          :filter-multiple="false"
        >
          <template #default="scope">
            {{ rowPhysicalAddress(scope.row) }}
          </template>
        </el-table-column>
        <template v-if="dbType === 'mysql'">
          <el-table-column
            label="版本"
            min-width="50"
            :filters="mysqlVersionFilters"
            :filter-method="filterByMysqlVersion"
            :filter-multiple="false"
          >
            <template #default="scope">
              {{ rowVersion(scope.row) }}
            </template>
          </el-table-column>
          <el-table-column
            label="只读状态"
            min-width="78"
            :filters="readonlyFilters"
            :filter-method="filterByReadonly"
            :filter-multiple="false"
          >
            <template #default="scope">
              <el-tag :type="readonlyTagType(mysqlStatus(scope.row).effective_read_only)">
                {{ readonlyText(mysqlStatus(scope.row).effective_read_only) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column
            label="主从角色"
            min-width="78"
            :filters="roleFilters"
            :filter-method="filterByRole"
            :filter-multiple="false"
          >
            <template #default="scope">
              <el-tag :type="roleTagType(mysqlRole(scope.row))">
                {{ roleText(mysqlRole(scope.row)) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="复制延迟" min-width="86">
            <template #default="scope">
              {{ shouldHideReplicationDetails(scope.row) ? "-" : (mysqlStatus(scope.row).seconds_behind_master ?? "-") }}
            </template>
          </el-table-column>
          <el-table-column label="复制线程" min-width="110">
            <template #default="scope">
              <div v-if="!shouldHideReplicationDetails(scope.row)" class="io-sql-tags">
                <el-tag size="small" :type="threadTagType(mysqlStatus(scope.row).replica_io_running)">
                  {{ threadLabel(mysqlStatus(scope.row).replica_io_running, "I/O") }}
                </el-tag>
                <el-tag size="small" :type="threadTagType(mysqlStatus(scope.row).replica_sql_running)">
                  {{ threadLabel(mysqlStatus(scope.row).replica_sql_running, "SQL") }}
                </el-tag>
              </div>
              <span v-else>-</span>
            </template>
          </el-table-column>
        </template>

        <el-table-column label="扩展" min-width="72" class-name="ext-col">
          <template #default="scope">
            <div class="ext-actions">
              <button
                v-if="showReplicationInfo(scope.row)"
                type="button"
                class="table-link table-link--primary"
                @click.stop="viewDetails(scope.row)"
              >
                {{ actionLabel }}
              </button>
              <button
                v-if="showInstanceDetail(scope.row)"
                type="button"
                class="table-link table-link--primary"
                @click.stop="viewInstanceDetail(scope.row)"
              >
                详情
              </button>
              <span v-if="!showReplicationInfo(scope.row) && !showInstanceDetail(scope.row)" class="muted-text">-</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90" fixed="right" class-name="op-col">
          <template #default="scope">
            <div class="op-actions">
              <button v-if="isAdmin" type="button" class="table-link table-link--primary" @click.stop="openEditDialog(scope.row)">编辑</button>
              <button v-if="isAdmin" type="button" class="table-link table-link--danger" @click.stop="removeInstance(scope.row)">删除</button>
              <span v-if="!isAdmin" class="no-perm-hint">无权限</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="心跳时间" width="160" fixed="right" show-overflow-tooltip>
          <template #default="scope">
            {{ lastCheckText(scope.row) }}
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div v-if="showPagination" class="pagination-wrap">
      <el-pagination
        background
        layout="total, sizes, prev, pager, next, jumper"
        :total="pager.total"
        :current-page="pager.page"
        :page-size="pager.page_size"
        :page-sizes="[20, 50, 100, 200]"
        @current-change="onPageChange"
        @size-change="onPageSizeChange"
      />
    </div>

    <el-dialog v-model="infoDialogVisible" :title="infoDialogTitle" width="700px">
        <el-table :data="infoRows" size="small" border stripe>
          <el-table-column prop="label" label="项目" width="180" />
          <el-table-column label="值">
            <template #default="scope">
              <ul v-if="Array.isArray(scope.row.value)" class="info-list">
                <li v-for="(item, idx) in scope.row.value" :key="idx">{{ item }}</li>
              </ul>
              <span v-else class="info-value">{{ scope.row.value }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-dialog>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="620px">
      <el-form :model="form" label-width="110px">
        <el-form-item label="实例名"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="所属集群">
          <el-select v-model="form.cluster_id" clearable style="width: 100%" placeholder="可选：选择已录入集群">
            <el-option v-for="item in clusters" :key="item.id" :label="clusterOptionLabel(item)" :value="item.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="域名"><el-input v-model.trim="form.host_domain" placeholder="可选，如 db.example.com" /></el-form-item>
        <el-form-item label="地址"><el-input v-model="form.host_input" placeholder="IP或主机地址" /></el-form-item>
        <el-form-item label="物理机地址">
          <el-input v-model.trim="form.physical_address" placeholder="可选，宿主机/物理机IP或域名" />
        </el-form-item>
        <el-form-item label="端口"><el-input-number v-model="form.port" :min="1" :max="65535" style="width: 100%" /></el-form-item>
        <el-form-item label="Node Exporter">
          <el-radio-group v-model="form.node_exporter_mode">
            <el-radio-button label="same_host">同主机:9100</el-radio-button>
            <el-radio-button label="custom">自定义地址</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.node_exporter_mode === 'custom'" label="Exporter地址">
          <el-input
            v-model.trim="form.node_exporter_address"
            placeholder="示例: 10.0.0.1:9100 或 http://10.0.0.1:9100/metrics"
          />
        </el-form-item>
        <el-form-item v-if="showUsername" label="用户名"><el-input v-model="form.username" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="form.password" type="password" show-password /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSubmit">{{ editingInstanceId ? "更新" : "保存" }}</el-button>
      </template>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, reactive, ref, watch } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useRoute } from "vue-router";
import { Coin, Files, Lightning, DataAnalysis } from "@element-plus/icons-vue";

import { collectClusterHealth, listClusters } from "../api/modules/clusters";
  import { createDorisInstance, dorisFeStatus, listDorisInstances } from "../api/modules/doris";
  import { deleteInstance, getInstanceStatusConfig, updateInstance as updateInstanceById } from "../api/modules/instances";
  import { createMongoInstance, listMongoInstances, mongoReplicaStatus } from "../api/modules/mongodb";
  import { getInstanceHealth } from "../api/modules/monitoring";
  import { createMysqlInstance, listMysqlInstances, mysqlInstanceDetail, mysqlReplication } from "../api/modules/mysql";
  import { createRedisInstance, listRedisInstances, redisClusterHealth } from "../api/modules/redis";
  import { formatBeijingTime, parseBeijingTimeMs } from "../utils/time";

const route = useRoute();

const CONFIG = {
  mysql: {
    defaultPort: 3306,
    actionLabel: "复制",
    icon: Coin,
    listFn: listMysqlInstances,
    createFn: createMysqlInstance,
    detailFn: (instanceId) => mysqlReplication(instanceId, false),
    instanceDetailFn: (instanceId) => mysqlInstanceDetail(instanceId, false),
    showUsername: true,
  },
    mongodb: {
      defaultPort: 27017,
      actionLabel: "副本",
      icon: Files,
      listFn: listMongoInstances,
      createFn: createMongoInstance,
      detailFn: mongoReplicaStatus,
      instanceDetailFn: (instanceId) => getInstanceHealth(instanceId),
      showUsername: true,
    },
  redis: {
    defaultPort: 6379,
    actionLabel: "复制",
    icon: Lightning,
    listFn: listRedisInstances,
    createFn: createRedisInstance,
    detailFn: redisClusterHealth,
    instanceDetailFn: (instanceId) => getInstanceHealth(instanceId),
    showUsername: false,
  },
  doris: {
    defaultPort: 9030,
    actionLabel: "FE",
    icon: DataAnalysis,
    listFn: listDorisInstances,
    createFn: createDorisInstance,
    detailFn: dorisFeStatus,
    instanceDetailFn: null,
    showUsername: true,
  },
};

const dbType = computed(() => route.meta.dbType || "mysql");
const dbLabel = computed(() => route.meta.dbLabel || "DB");
const pageCfg = computed(() => CONFIG[dbType.value] || CONFIG.mysql);
const dbIcon = computed(() => pageCfg.value.icon);
const actionLabel = computed(() => pageCfg.value.actionLabel);
const showUsername = computed(() => pageCfg.value.showUsername);

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
const healthChecking = ref(false);
const healthBatchRunning = ref(false);
const dialogVisible = ref(false);
const editingInstanceId = ref(null);
const rows = ref([]);
const clusters = ref([]);
const keyword = ref("");
const healthIntervalSec = ref(0);
const statusProbePollIntervalSec = ref(30);
const selectedBusinessLine = ref(null);
const selectedEnvironment = ref(null);
const selectedClusterId = ref(null);
const hoveredClusterId = ref(null);
const hoveredRowId = ref(null);
const nowTickMs = ref(Date.now());
const infoDialogVisible = ref(false);
const infoDialogTitle = ref("");
const infoRows = ref([]);
const lastHealthFetchAt = ref(0);

let healthTimer = null;
let relativeTimer = null;
let refreshTimer = null;
let searchTimer = null;

const mysqlStatusMap = reactive({});
const commonHealthMap = reactive({});
const lastCheckAtMap = reactive({});
const pager = reactive({
  page: 1,
  page_size: 20,
  total: 0,
});
const pagerSnapshotBeforeCluster = reactive({
  page: 1,
  page_size: 20,
});
const isClusterSnapshotActive = ref(false);
const editingExtraBase = ref({});

const form = reactive({
  name: "",
  cluster_id: null,
  host_domain: "",
  host_input: "",
  physical_address: "",
  port: 3306,
  node_exporter_mode: "same_host",
  node_exporter_address: "",
  username: "",
  password: "",
});

// 从集群数据中提取命名空间列表
const businessLines = computed(() => {
  const set = new Set(clusters.value.map(c => c.business_line || c.namespace).filter(Boolean));
  return Array.from(set).sort();
});

const environments = computed(() => {
  const source = selectedBusinessLine.value
    ? clusters.value.filter(c => (c.business_line || c.namespace) === selectedBusinessLine.value)
    : clusters.value;
  const set = new Set(source.map(c => c.environment).filter(Boolean));
  return Array.from(set).sort();
});

// 根据选中的命名空间过滤集群列表
const filteredClusters = computed(() => {
  let list = clusters.value;
  if (selectedBusinessLine.value) {
    list = list.filter(c => (c.business_line || c.namespace) === selectedBusinessLine.value);
  }
  if (selectedEnvironment.value) {
    list = list.filter(c => c.environment === selectedEnvironment.value);
  }
  return list;
});

const dialogTitle = computed(() => (editingInstanceId.value ? `编辑${dbLabel.value}实例` : `新增${dbLabel.value}实例`));

const displayRows = computed(() => {
  let result = rows.value;

  if (selectedBusinessLine.value) {
    const allowed = new Set(
      clusters.value
        .filter((c) => (c.business_line || c.namespace) === selectedBusinessLine.value)
        .map((c) => c.id),
    );
    result = result.filter((row) => row.cluster_id && allowed.has(row.cluster_id));
  }

  if (selectedEnvironment.value) {
    const allowed = new Set(
      clusters.value
        .filter((c) => c.environment === selectedEnvironment.value)
        .map((c) => c.id),
    );
    result = result.filter((row) => row.cluster_id && allowed.has(row.cluster_id));
  }

  if (selectedClusterId.value) {
    result = result.filter((row) => row.cluster_id === selectedClusterId.value);
  }

  return result;
});

const showPagination = computed(() => !selectedClusterId.value);

function isEmptyValue(value) {
  return value === null || value === undefined || value === "";
}

function buildFilterOptions(list, getter, textGetter, emptyLabel) {
  const output = [];
  const seen = new Set();
  let hasEmpty = false;
  list.forEach((row) => {
    const value = getter(row);
    if (isEmptyValue(value)) {
      hasEmpty = true;
      return;
    }
    const key = typeof value === "string" || typeof value === "number" || typeof value === "boolean" ? value : JSON.stringify(value);
    if (seen.has(key)) {
      return;
    }
    seen.add(key);
    output.push({
      text: textGetter ? textGetter(value, row) : String(value),
      value,
    });
  });
  if (hasEmpty) {
    output.unshift({ text: emptyLabel, value: "__empty__" });
  }
  return output;
}

const clusterFilters = computed(() =>
  buildFilterOptions(rows.value, (row) => row.cluster_id, (value) => resolveClusterName(value), "未归属"),
);

const runningFilters = computed(() =>
  buildFilterOptions(rows.value, (row) => rowRunningStatus(row), (value) => runningText(value), "未知"),
);

const portFilters = computed(() =>
  buildFilterOptions(rows.value, (row) => row.port, (value) => String(value), "未设置"),
);

const physicalAddressFilters = computed(() =>
  buildFilterOptions(rows.value, (row) => rawPhysicalAddress(row), (value) => value, "未设置"),
);

const mysqlVersionFilters = computed(() => {
  if (dbType.value !== "mysql") {
    return [];
  }
  return buildFilterOptions(rows.value, (row) => mysqlStatus(row).version, (value) => value, "未知");
});

const readonlyFilters = computed(() => {
  if (dbType.value !== "mysql") {
    return [];
  }
  return buildFilterOptions(rows.value, (row) => mysqlStatus(row).effective_read_only, (value) => readonlyText(value), "未知");
});

const roleFilters = computed(() => {
  if (dbType.value !== "mysql") {
    return [];
  }
  return buildFilterOptions(rows.value, (row) => mysqlRole(row), (value) => roleText(value), "未知");
});

function filterByCluster(value, row) {
  if (value === "__empty__") {
    return isEmptyValue(row.cluster_id);
  }
  return Number(row.cluster_id) === Number(value);
}

function filterByRunning(value, row) {
  return rowRunningStatus(row) === value;
}

function filterByPort(value, row) {
  if (value === "__empty__") {
    return isEmptyValue(row.port);
  }
  return Number(row.port) === Number(value);
}

function filterByPhysicalAddress(value, row) {
  const current = rawPhysicalAddress(row);
  if (value === "__empty__") {
    return isEmptyValue(current);
  }
  return current === value;
}

function filterByMysqlVersion(value, row) {
  const current = mysqlStatus(row).version || "";
  if (value === "__empty__") {
    return isEmptyValue(current);
  }
  return current === value;
}

function filterByReadonly(value, row) {
  const flag = mysqlStatus(row).effective_read_only;
  if (value === "__empty__") {
    return isEmptyValue(flag);
  }
  return flag === value;
}

function filterByRole(value, row) {
  return mysqlRole(row) === value;
}

function resetForm() {
  editingInstanceId.value = null;
  editingExtraBase.value = {};
  form.name = "";
  form.cluster_id = null;
  form.host_domain = "";
  form.host_input = "";
  form.physical_address = "";
  form.port = pageCfg.value.defaultPort;
  form.node_exporter_mode = "same_host";
  form.node_exporter_address = "";
  form.username = "";
  form.password = "";
}

function openCreateDialog() {
  resetForm();
  dialogVisible.value = true;
}

function openEditDialog(row) {
  editingInstanceId.value = row.id;
  const rawExtra = row?.extra_json && typeof row.extra_json === "object" ? row.extra_json : {};
  editingExtraBase.value = JSON.parse(JSON.stringify(rawExtra));
  const exporter = rawExtra?.node_exporter && typeof rawExtra.node_exporter === "object" ? rawExtra.node_exporter : {};
  const mode = exporter.mode === "custom" ? "custom" : "same_host";
  form.name = row.name || "";
  form.cluster_id = row.cluster_id ?? null;
  form.host_domain = row.host_domain || (rawExtra.domain || "");
  form.host_input = row.host_input || "";
  form.physical_address = rawExtra.physical_address || "";
  form.port = row.port || pageCfg.value.defaultPort;
  form.node_exporter_mode = mode;
  form.node_exporter_address = mode === "custom" ? (exporter.address || exporter.endpoint || "") : "";
  form.username = row.username || "";
  form.password = "";
  dialogVisible.value = true;
}

function buildNodeExporterPayload() {
  const mode = form.node_exporter_mode === "custom" ? "custom" : "same_host";
  if (mode === "custom") {
    return {
      enabled: true,
      mode: "custom",
      address: (form.node_exporter_address || "").trim(),
    };
  }
  return {
    enabled: true,
    mode: "same_host",
    port: 9100,
  };
}

function buildExtraJsonPayload() {
  const base = editingExtraBase.value && typeof editingExtraBase.value === "object" ? JSON.parse(JSON.stringify(editingExtraBase.value)) : {};
  const domain = (form.host_domain || "").trim();
  if (domain) {
    base.domain = domain;
  } else {
    delete base.domain;
  }
  const physicalAddress = (form.physical_address || "").trim();
  if (physicalAddress) {
    base.physical_address = physicalAddress;
  } else {
    delete base.physical_address;
  }
  base.node_exporter = buildNodeExporterPayload();
  return base;
}

function clusterOptionLabel(item) {
  const line = item.business_line || item.namespace || "";
  const env = item.environment || "";
  const parts = [line, env, item.name].filter(Boolean);
  return parts.length ? parts.join("/") : item.name;
}

function resolveClusterName(clusterId) {
  if (!clusterId) {
    return "-";
  }
  const row = clusters.value.find((item) => item.id === clusterId);
  return row ? clusterOptionLabel(row) : `#${clusterId}`;
}

function resolveClusterParts(clusterId) {
  if (!clusterId) {
    return [{ label: "集群", value: "-" }];
  }
  const row = clusters.value.find((item) => item.id === clusterId);
  if (!row) {
    return [{ label: "集群", value: `#${clusterId}` }];
  }
  const line = row.business_line || row.namespace || "";
  const env = row.environment || "";
  return [
    { label: "项目", value: line || "-" },
    { label: "环境", value: env || "-" },
    { label: "集群", value: row.name || "-" },
  ];
}

function rowDomain(row) {
  return row.host_domain || "-";
}

function rowAddress(row) {
  return row.resolved_ip || row.host_input || "-";
}

function rowPhysicalAddress(row) {
  const raw = rawPhysicalAddress(row);
  return raw ? String(raw) : "-";
}

function rawPhysicalAddress(row) {
  const raw = row?.extra_json && typeof row.extra_json === "object" ? row.extra_json.physical_address : "";
  return raw ? String(raw).trim() : "";
}

function appConnStatus(row) {
  if (dbType.value !== "mysql" || !row.cluster_id) {
    return "na";
  }
  const cluster = clusters.value.find((item) => item.id === row.cluster_id);
  if (!cluster || !cluster.ha_domain) {
    return "na";
  }
  const ha = cluster.ha_status_json || {};
  if (!ha.checked_at) {
    return "unknown";
  }
  if (ha.matched_instance_id === row.id && ha.ok) {
    return "ok";
  }
  if (ha.matched_instance_id === row.id && !ha.ok) {
    return "error";
  }
  if (ha.resolved_ip) {
    return "miss";
  }
  return "error";
}

function appConnTagType(row) {
  const s = appConnStatus(row);
  if (s === "ok") return "success";
  if (s === "error") return "danger";
  if (s === "miss") return "warning";
  return "info";
}

function appConnText(row) {
  const s = appConnStatus(row);
  if (s === "ok") return "正常";
  if (s === "error") return "异常";
  if (s === "miss") return "-";
  if (s === "unknown") return "未检查";
  return "-";
}

function hostMetricPayload(row) {
  if (dbType.value === "mysql") {
    return mysqlStatus(row);
  }
  return commonHealthMap[row.id]?.payload_json || {};
}

  function mongoRole(row) {
    const payload = commonHealthMap[row.id]?.payload_json || {};
    const explicit = payload.mongo_role;
    if (explicit) {
      return explicit;
    }
    const state = payload.repl?.myState;
    if (state === 1) return "primary";
    if (state === 2) return "secondary";
    if (state === 7) return "arbiter";
    if (state === 0 || state === undefined || state === null) return "unknown";
    return "unknown";
  }

  function mongoRoleText(role) {
    if (role === "primary") return "主库";
    if (role === "secondary") return "从库";
    if (role === "arbiter") return "仲裁";
    if (role === "mongos") return "Mongos";
    if (role === "configsvr") return "配置节点";
    if (role === "shard") return "分片节点";
    return "未知";
  }

  function mongoRoleTagType(role) {
    if (role === "primary") return roleTagType("master");
    if (role === "secondary") return roleTagType("slave");
    if (role === "arbiter") return roleTagType("read_only");
    if (role === "mongos") return "info";
    if (role === "configsvr") return "warning";
    if (role === "shard") return "info";
    return roleTagType("unknown");
  }

  function redisRole(row) {
    const payload = commonHealthMap[row.id]?.payload_json || {};
    const role = String(payload.role || "").toLowerCase();
    if (role === "master") return "master";
    if (role === "slave" || role === "replica") return "slave";
    return "unknown";
  }

  function redisRoleText(role) {
    if (role === "master") return "主库";
    if (role === "slave") return "从库";
    return "未知";
  }

  function redisRoleTagType(role) {
    if (role === "master") return roleTagType("master");
    if (role === "slave") return roleTagType("slave");
    return roleTagType("unknown");
  }

  function redisHaMode(row) {
    const payload = row?.payload_json && typeof row.payload_json === "object"
      ? row.payload_json
      : commonHealthMap[row?.id]?.payload_json || {};
    const clusterEnabled = payload.cluster_enabled;
    const clusterState = String(payload.cluster_state || "").toLowerCase();
    const redisMode = String(payload.redis_mode || payload.mode || "").toLowerCase();
    
    // 集群模式判定：INFO server 中的 redis_mode 或 INFO cluster 中的 cluster_enabled
    if (redisMode === "cluster" || clusterEnabled === 1 || clusterEnabled === true || clusterState) {
      return "cluster";
    }
    
    const sentinelMasters = payload.sentinel_masters;
    const isSentinel = redisMode === "sentinel" || Number(sentinelMasters) > 0 || payload.sentinel_enabled === true;
    if (isSentinel) {
      return "sentinel";
    }
    if (redisRole(row) !== "unknown") {
      return "replication";
    }
    return "standalone";
  }

  function redisHaModeText(mode) {
    if (mode === "cluster") return "集群模式";
    if (mode === "sentinel") return "哨兵模式";
    if (mode === "replication") return "主从模式";
    return "单机模式";
  }

  function redisHaModeTagType(mode) {
    if (mode === "cluster") return "success";
    if (mode === "sentinel") return "warning";
    if (mode === "replication") return "info";
    return "";
  }

  function redisPayload(row) {
    return commonHealthMap[row.id]?.payload_json || {};
  }

  function redisReplicationSourceFromPayload(payload) {
    const source = String(payload.replication_source || "").trim();
    if (source) {
      return source;
    }
    const host = String(payload.master_host || "").trim();
    const port = payload.master_port;
    if (!host) {
      return "-";
    }
    if (port === null || port === undefined || port === "") {
      return host;
    }
    return `${host}:${port}`;
  }

  function redisReplicationSource(row) {
    return redisReplicationSourceFromPayload(redisPayload(row));
  }

  function redisReplicationLagFromPayload(payload) {
    const lag = payload.replication_lag_seconds;
    if (lag === null || lag === undefined || lag === "") {
      return "-";
    }
    const num = Number(lag);
    if (!Number.isFinite(num) || num < 0) {
      return "-";
    }
    return String(Math.round(num));
  }

  function redisReplicationLag(row) {
    return redisReplicationLagFromPayload(redisPayload(row));
  }

  function redisKeyCountFromPayload(payload) {
    const value = payload.keyspace_total_keys;
    if (value === null || value === undefined || value === "") {
      return "-";
    }
    const num = Number(value);
    if (!Number.isFinite(num)) {
      return "-";
    }
    return new Intl.NumberFormat("zh-CN").format(Math.round(num));
  }

  function redisKeyCount(row) {
    return redisKeyCountFromPayload(redisPayload(row));
  }

  function redisContainerMemorySummary(payload) {
    const usedText = formatBytes(payload.used_memory);
    const maxText = formatBytes(payload.maxmemory);
    if (usedText === "-" && maxText === "-") {
      return "-";
    }
    if (maxText === "-") {
      return `${usedText}/∞`;
    }
    return `${usedText}/${maxText}`;
  }

  function redisContainerMemoryText(row) {
    return redisContainerMemorySummary(redisPayload(row));
  }

  function redisContainerMemoryPercentFromPayload(payload) {
    const maxmemory = Number(payload.maxmemory);
    if (!Number.isFinite(maxmemory) || maxmemory <= 0) {
      return "∞";
    }
    return asPercentText(payload.memory_usage_pct);
  }

  function redisContainerMemoryPercentText(row) {
    return redisContainerMemoryPercentFromPayload(redisPayload(row));
  }

  function redisContainerMemoryValue(row) {
    return asPercent(redisPayload(row).memory_usage_pct);
  }

function asPercent(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) {
    return null;
  }
  return Math.max(0, Math.min(100, num));
}

function asPercentText(value) {
  const pct = asPercent(value);
  if (pct === null) {
    return "-";
  }
  return `${pct.toFixed(1)}%`;
}

function formatCount(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) {
    return "-";
  }
  return new Intl.NumberFormat("zh-CN").format(Math.round(num));
}

function formatBytes(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) {
    return "-";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  let idx = 0;
  let val = num;
  while (val >= 1024 && idx < units.length - 1) {
    val /= 1024;
    idx += 1;
  }
  const digits = val >= 100 ? 0 : val >= 10 ? 1 : 2;
  return `${val.toFixed(digits)} ${units[idx]}`;
}

function formatRate(value) {
  if (value === null || value === undefined) {
    return "-";
  }
  const text = formatBytes(value);
  return text === "-" ? "-" : `${text}/s`;
}

function usageTagClass(value) {
  const pct = asPercent(value);
  if (pct === null) {
    return "metric-tag metric-tag--normal";
  }
  if (pct >= 70) {
    return "metric-tag metric-tag--hot";
  }
  if (pct >= 50) {
    return "metric-tag metric-tag--warn";
  }
  return "metric-tag metric-tag--normal";
}

function hostCpuValue(row) {
  return asPercent(hostMetricPayload(row).host_cpu_usage_pct);
}

function hostMemoryValue(row) {
  return asPercent(hostMetricPayload(row).host_memory_usage_pct);
}

function hostDiskValue(row) {
  const payload = hostMetricPayload(row);
  const entry = pickMaxUsedDisk(payload);
  if (entry) {
    return asPercent(entry.usage_pct);
  }
  return asPercent(payload.host_data_disk_usage_pct);
}

function hostCpuText(row) {
  return asPercentText(hostMetricPayload(row).host_cpu_usage_pct);
}

function hostMemoryText(row) {
  return asPercentText(hostMetricPayload(row).host_memory_usage_pct);
}

function hostDiskText(row) {
  const payload = hostMetricPayload(row);
  const entry = pickMaxUsedDisk(payload);
  const usageText = asPercentText(entry ? entry.usage_pct : payload.host_data_disk_usage_pct);
  if (usageText === "-") {
    return "-";
  }
  const mount = entry?.mountpoint || entry?.device || payload.host_data_disk_mountpoint || "";
  return mount ? `${usageText} (${mount})` : usageText;
}

function pickMaxUsedDisk(payload) {
  const entries = Array.isArray(payload?.host_disk_entries) ? payload.host_disk_entries : [];
  if (!entries.length) {
    return null;
  }
  let best = null;
  let bestUsed = -1;
  entries.forEach((item) => {
    const used = Number(item?.used_bytes);
    if (!Number.isFinite(used)) {
      return;
    }
    if (used > bestUsed) {
      bestUsed = used;
      best = item;
    }
  });
  return best;
}

function onRowMouseEnter(row) {
  hoveredClusterId.value = row.cluster_id || null;
  hoveredRowId.value = row.id || null;
}

function onRowMouseLeave() {
  hoveredClusterId.value = null;
  hoveredRowId.value = null;
}

// 点击行选中整个集群
async function onRowClick(row) {
  if (row.cluster_id) {
    if (selectedClusterId.value === row.cluster_id) {
      selectedClusterId.value = null;
    } else {
      selectedClusterId.value = row.cluster_id;
    }
    pager.page = 1;
    await loadInstances();
    await runHealthCheck(true);
  }
}

// 下拉框选择集群
async function onClusterSelectChange() {
  pager.page = 1;
  await loadInstances();
  await runHealthCheck(true);
}

// 下拉框选择命名空间
async function onBusinessLineChange() {
  selectedEnvironment.value = null;
  selectedClusterId.value = null;
  pager.page = 1;
  await loadInstances();
  await runHealthCheck(true);
}

async function onEnvironmentChange() {
  selectedClusterId.value = null;
  pager.page = 1;
  await loadInstances();
  await runHealthCheck(true);
}

function tableRowClassName({ row }) {
  // 优先处理选中的集群
  if (selectedClusterId.value && row.cluster_id === selectedClusterId.value) {
    return "cluster-selected-row";
  }
  // 鼠标悬停效果
  if (!hoveredClusterId.value || !row.cluster_id) {
    return "";
  }
  if (row.cluster_id !== hoveredClusterId.value) {
    return "";
  }
  return row.id !== hoveredRowId.value ? "cluster-related-row" : "";
}

function normalizeHost(value) {
  return String(value || "").trim().toLowerCase();
}

function instanceHostPortKey(row) {
  const host = normalizeHost(row.resolved_ip || row.host_input);
  const port = Number(row.port);
  if (!host || !port) {
    return "";
  }
  return `${host}:${port}`;
}

function replicaSourceKey(status) {
  const host = normalizeHost(status.replica_source_resolved_ip || status.replica_source_host);
  const port = Number(status.replica_source_port);
  if (!host || !port) {
    return "";
  }
  return `${host}:${port}`;
}

function mysqlStatus(row) {
  return mysqlStatusMap[row.id] || {};
}

function rowRunningStatus(row) {
  if (dbType.value === "mysql") {
    return mysqlStatus(row).running_status || "unknown";
  }
  return commonHealthMap[row.id]?.running_status || "unknown";
}

  function rowLastCheckAt(row) {
    return lastCheckAtMap[row.id] || null;
  }

  function rowVersion(row) {
    if (dbType.value === "mysql") {
      return mysqlStatus(row).version || "-";
    }
    const payload = commonHealthMap[row.id]?.payload_json || {};
    if (dbType.value === "redis") {
      return payload.version || payload.redis_version || "-";
    }
    return payload.version || "-";
  }

function lastCheckText(row) {
  const raw = rowLastCheckAt(row);
  if (!raw) {
    return "-";
  }
  const ts = parseBeijingTimeMs(raw);
  if (Number.isNaN(ts)) {
    return "-";
  }
  const seconds = Math.max(0, Math.floor((nowTickMs.value - ts) / 1000));
  return `${seconds}秒之前`;
}

function isMutualMasterSlave(row) {
  if (!row.cluster_id) {
    return false;
  }

  const selfStatus = mysqlStatus(row);
  const selfSource = replicaSourceKey(selfStatus);
  const selfKey = instanceHostPortKey(row);
  if (!selfSource || !selfKey) {
    return false;
  }

  const peers = rows.value.filter((item) => item.cluster_id === row.cluster_id && item.id !== row.id);
  const upstreamPeer = peers.find((item) => instanceHostPortKey(item) === selfSource);
  if (!upstreamPeer) {
    return false;
  }

  const peerStatus = mysqlStatus(upstreamPeer);
  const peerSource = replicaSourceKey(peerStatus);
  return peerSource === selfKey;
}

function mysqlRole(row) {
  if (isMutualMasterSlave(row)) {
    return "dual";
  }
  return mysqlStatus(row).replication_role;
}

function shouldHideReplicationDetails(row) {
  return dbType.value === "mysql" && mysqlRole(row) === "master";
}

function clearStatusMaps() {
  Object.keys(mysqlStatusMap).forEach((key) => delete mysqlStatusMap[key]);
  Object.keys(commonHealthMap).forEach((key) => delete commonHealthMap[key]);
  Object.keys(lastCheckAtMap).forEach((key) => delete lastCheckAtMap[key]);
}

function runningTagType(status) {
  if (status === "running") {
    return "success";
  }
  if (status === "error") {
    return "danger";
  }
  return "info";
}

function runningText(status) {
  if (status === "running") {
    return "正常";
  }
  if (status === "error") {
    return "异常";
  }
  return "未知";
}

function readonlyText(effectiveReadOnly) {
  if (effectiveReadOnly === true) {
    return "是";
  }
  if (effectiveReadOnly === false) {
    return "否";
  }
  return "-";
}

function readonlyTagType(effectiveReadOnly) {
  if (effectiveReadOnly === true) {
    return "warning";
  }
  if (effectiveReadOnly === false) {
    return "success";
  }
  return "info";
}

function roleTagType(role) {
  if (role === "dual") {
    return "warning";
  }
  if (role === "master") {
    return "success";
  }
  if (role === "slave") {
    return "warning";
  }
  if (role === "read_only") {
    return "info";
  }
  return "danger";
}

function roleText(role) {
  if (role === "dual") {
    return "主库/从库";
  }
  if (role === "master") {
    return "主库";
  }
  if (role === "slave") {
    return "从库";
  }
  if (role === "read_only") {
    return "只读";
  }
  return "未知";
}

function threadTagType(flag) {
  if (flag === true) {
    return "success";
  }
  return "danger";
}

function threadLabel(flag, prefix) {
  if (flag === true) {
    return `${prefix}正常`;
  }
  return `${prefix}异常`;
}

function isIdFieldLabel(label) {
  const text = String(label || "")
    .trim()
    .toLowerCase();
  if (!text) {
    return false;
  }
  if (text === "id") {
    return true;
  }
  if (text.endsWith("_id")) {
    return true;
  }
  return ["instance id", "cluster id", "policy id", "user id", "node id", "实例id", "节点id", "策略id"].includes(text);
}

function showReplicationInfo(row) {
  if (typeof pageCfg.value.detailFn !== "function") {
    return false;
  }
  if (dbType.value === "mysql" && shouldHideReplicationDetails(row)) {
    return false;
  }
  return true;
}

  function showInstanceDetail(_row) {
    return (dbType.value === "mysql" || dbType.value === "mongodb" || dbType.value === "redis") && typeof pageCfg.value.instanceDetailFn === "function";
  }

  function safeJsonStringify(value) {
    try {
      return JSON.stringify(
        value,
        (_key, val) => {
          if (typeof val === "bigint") {
            return val.toString();
          }
          return val;
        },
        2,
      );
    } catch (error) {
      return String(value);
    }
  }

  function normalizeInfoValue(value) {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "boolean") {
    return value ? "是" : "否";
  }
  if (typeof value === "number") {
    return Number.isFinite(value) ? String(value) : "-";
  }
    if (typeof value === "object") {
      return safeJsonStringify(value);
    }
    return String(value);
  }

  function formatDateTime(isoValue) {
    return formatBeijingTime(isoValue);
  }

function openInfoDialog(title, rowsData) {
  infoDialogTitle.value = title;
  const sourceRows = rowsData?.length ? rowsData : [{ label: "结果", value: "-" }];
  const filtered = sourceRows.filter((row) => !isIdFieldLabel(row.label));
  infoRows.value = filtered.length ? filtered : [{ label: "结果", value: "-" }];
  infoDialogVisible.value = true;
}

  function buildGenericInfoRows(payload) {
  const obj = payload && typeof payload === "object" ? payload : {};
  const keys = Object.keys(obj);
  if (!keys.length) {
    return [{ label: "结果", value: "-" }];
  }

  function toFlatList(value) {
    if (!value || typeof value !== "object") {
      return [];
    }
    if (Array.isArray(value)) {
      return value.map((item, idx) => `${idx + 1}. ${normalizeInfoValue(item)}`);
    }
    return Object.keys(value).map((key) => `${key}: ${normalizeInfoValue(value[key])}`);
  }

  function mongoStateText(state) {
    if (state === 1) return "主库";
    if (state === 2) return "从库";
    if (state === 7) return "仲裁";
    return "未知";
  }

  function buildMongoReplicationRows(payload) {
    const repl = payload?.repl || {};
    const rows = [
      { label: "副本集", value: normalizeInfoValue(repl.set) },
      { label: "主从角色", value: mongoStateText(repl.myState) },
      { label: "成员数", value: normalizeInfoValue(repl.members) },
    ];
    const statusList = toFlatList(repl.rs_status);
    if (statusList.length) {
      rows.push({ label: "rs.status()", value: statusList });
    }
    const confList = toFlatList(repl.rs_conf);
    if (confList.length) {
      rows.push({ label: "rs.conf()", value: confList });
    }
    if (rows.length === 3 && !statusList.length && !confList.length) {
      rows.push({ label: "结果", value: "-" });
    }
    return rows;
  }
  return keys.map((key) => ({
    label: key,
    value: normalizeInfoValue(obj[key]),
  }));
}

function buildMysqlReplicationRows(payload) {
  return [
    { label: "数据来源", value: normalizeInfoValue(payload.source) },
    { label: "运行情况", value: runningText(payload.running_status) },
    { label: "心跳时间", value: formatDateTime(payload.collected_at) },
    { label: "Node Exporter状态", value: normalizeInfoValue(payload.node_exporter_status) },
    { label: "主从角色", value: roleText(payload.replication_role) },
    { label: "只读(read_only)", value: normalizeInfoValue(payload.read_only) },
    { label: "只读(super_read_only)", value: normalizeInfoValue(payload.super_read_only) },
    { label: "综合只读", value: normalizeInfoValue(payload.effective_read_only) },
    { label: "复制源主机", value: normalizeInfoValue(payload.replica_source_host) },
    { label: "复制源IP", value: normalizeInfoValue(payload.replica_source_resolved_ip) },
    { label: "复制源端口", value: normalizeInfoValue(payload.replica_source_port) },
    { label: "复制延迟(s)", value: normalizeInfoValue(payload.seconds_behind_master) },
    { label: "IO线程", value: threadLabel(payload.replica_io_running, "") },
    { label: "SQL线程", value: threadLabel(payload.replica_sql_running, "") },
    { label: "CPU使用率", value: asPercentText(payload.host_cpu_usage_pct) },
    { label: "内存使用率", value: asPercentText(payload.host_memory_usage_pct) },
    {
      label: "数据盘使用率",
      value: payload.host_data_disk_mountpoint
        ? `${asPercentText(payload.host_data_disk_usage_pct)} (${payload.host_data_disk_mountpoint})`
        : asPercentText(payload.host_data_disk_usage_pct),
    },
    { label: "错误信息", value: normalizeInfoValue(payload.collect_error) },
    { label: "Exporter错误", value: normalizeInfoValue(payload.node_exporter_error) },
  ];
}

function buildRedisReplicationRows(payload, row) {
  const mergedPayload = {
    ...redisPayload(row),
    ...(payload && typeof payload === "object" ? payload : {}),
  };
  const mergedForMode = { id: "__replication__", payload_json: mergedPayload };
  const clusterInfo = mergedPayload.cluster_info && typeof mergedPayload.cluster_info === "object" ? mergedPayload.cluster_info : {};
  const clusterInfoList = Object.keys(clusterInfo).map((key) => `${key}: ${normalizeInfoValue(clusterInfo[key])}`);
  const collectedAt = commonHealthMap[row.id]?.collected_at || mergedPayload.collected_at;
  const runningStatus = commonHealthMap[row.id]?.running_status || mergedPayload.running_status;

  const rows = [
    { label: "运行情况", value: runningText(runningStatus) },
    { label: "心跳时间", value: formatDateTime(collectedAt) },
    { label: "主从角色", value: redisRoleText(String(mergedPayload.role || "").toLowerCase()) },
    { label: "高可用模式", value: redisHaModeText(redisHaMode(mergedForMode)) },
    { label: "复制源信息", value: redisReplicationSourceFromPayload(mergedPayload) },
    { label: "复制延迟(s)", value: redisReplicationLagFromPayload(mergedPayload) },
    { label: "Key数量", value: redisKeyCountFromPayload(mergedPayload) },
    { label: "实例内存使用率", value: redisContainerMemorySummary(mergedPayload) },
    { label: "主从链路状态", value: normalizeInfoValue(mergedPayload.master_link_status) },
    { label: "从库数量", value: normalizeInfoValue(mergedPayload.connected_slaves) },
  ];
  if (clusterInfoList.length) {
    rows.push({ label: "CLUSTER INFO", value: clusterInfoList });
  }
  return rows;
}

  function buildMysqlDetailRows(payload) {
  const rowsData = [
    { label: "数据来源", value: normalizeInfoValue(payload.source) },
    { label: "运行情况", value: runningText(payload.running_status) },
    { label: "心跳时间", value: formatDateTime(payload.collected_at) },
    { label: "Node Exporter状态", value: normalizeInfoValue(payload.node_exporter_status) },
      { label: "实例启动时间", value: formatDateTime(payload.started_at) },
      { label: "运行时长(s)", value: normalizeInfoValue(payload.uptime) },
      { label: "版本", value: normalizeInfoValue(payload.version) },
      { label: "CPU核数", value: normalizeInfoValue(payload.host_cpu_cores) },
      { label: "内存总大小", value: formatBytes(payload.host_memory_total_bytes) },
      { label: "当前连接数", value: normalizeInfoValue(payload.threads_connected) },
    { label: "活动连接数", value: normalizeInfoValue(payload.threads_running) },
    { label: "最大连接数", value: normalizeInfoValue(payload.max_connections) },
    { label: "锁等待数量", value: normalizeInfoValue(payload.lock_waits) },
    { label: "QPS", value: normalizeInfoValue(payload.qps) },
    { label: "TPS", value: normalizeInfoValue(payload.tps) },
    { label: "CPU使用率", value: asPercentText(payload.host_cpu_usage_pct) },
    { label: "内存使用率", value: asPercentText(payload.host_memory_usage_pct) },
    {
      label: "数据盘使用率",
      value: buildDataDiskSummary(payload),
    },
    { label: "错误信息", value: normalizeInfoValue(payload.collect_error) },
    { label: "Exporter错误", value: normalizeInfoValue(payload.node_exporter_error) },
  ];
  rowsData.push(...buildDiskRows(payload));
  rowsData.push(...buildNetworkRows(payload));
  return rowsData;
}

function buildDataDiskSummary(payload) {
  const pctText = asPercentText(payload.host_data_disk_usage_pct);
  const mount = payload.host_data_disk_mountpoint;
  const sizeText = formatBytes(payload.host_data_disk_size_bytes);
  if (!mount && pctText === "-" && sizeText === "-") {
    return "-";
  }
  const parts = [];
  if (pctText !== "-") {
    parts.push(`使用率 ${pctText}`);
  }
  if (sizeText !== "-") {
    parts.push(`总量 ${sizeText}`);
  }
  if (mount) {
    parts.push(`挂载 ${mount}`);
  }
  return parts.length ? parts.join("，") : "-";
}

function buildDiskRows(payload) {
  const disks = Array.isArray(payload.host_disk_entries) ? payload.host_disk_entries : [];
  if (!disks.length) {
    return [];
  }
  const rows = [];
  disks.forEach((disk) => {
    const mount = disk.mountpoint || disk.device || "-";
    const sizeText = formatBytes(disk.size_bytes);
    const usedText = formatBytes(disk.used_bytes);
    const pctText = asPercentText(disk.usage_pct);
    const parts = [];
    if (sizeText !== "-") {
      parts.push(`总量 ${sizeText}`);
    }
    if (usedText !== "-") {
      parts.push(`已用 ${usedText}`);
    }
    if (pctText !== "-") {
      parts.push(`使用率 ${pctText}`);
    }
    rows.push({
      label: `磁盘(${mount})`,
      value: parts.length ? parts.join("，") : "-",
    });

    const inodePct = asPercentText(disk.inode_usage_pct);
    const inodeUsed = formatCount(disk.inode_used);
    const inodeTotal = formatCount(disk.inode_total);
    const inodeParts = [];
    if (inodePct !== "-") {
      inodeParts.push(`使用率 ${inodePct}`);
    }
    if (inodeUsed !== "-" && inodeTotal !== "-") {
      inodeParts.push(`已用 ${inodeUsed}/${inodeTotal}`);
    }
    rows.push({
      label: `inode(${mount})`,
      value: inodeParts.length ? inodeParts.join("，") : "-",
    });
  });
  return rows;
}

function buildNetworkRows(payload) {
  const nets = Array.isArray(payload.host_net_rates) ? payload.host_net_rates : [];
  if (!nets.length) {
    return [];
  }
  return nets.map((item) => {
    const device = item.device || "-";
    const rxText = formatRate(item.rx_bps);
    const txText = formatRate(item.tx_bps);
    const parts = [];
    if (rxText !== "-") {
      parts.push(`下行 ${rxText}`);
    }
    if (txText !== "-") {
      parts.push(`上行 ${txText}`);
    }
    return {
      label: `网络(${device})`,
      value: parts.length ? parts.join("，") : "-",
    };
  });
}

async function loadClusters() {
  try {
    const { data } = await listClusters(dbType.value);
    clusters.value = data.data || [];
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载集群失败");
  }
}

async function loadInstances() {
  loading.value = true;
  try {
    const baseParams = {
      keyword: selectedClusterId.value ? undefined : keyword.value.trim() || undefined,
      cluster_id: selectedClusterId.value || undefined,
    };

    if (selectedClusterId.value) {
      if (!isClusterSnapshotActive.value) {
        pagerSnapshotBeforeCluster.page = pager.page;
        pagerSnapshotBeforeCluster.page_size = pager.page_size;
        isClusterSnapshotActive.value = true;
      }
      const merged = [];
      let page = 1;
      let total = 0;
      const pageSize = 200;
      const maxPages = 200;
      while (page <= maxPages) {
        const { data } = await pageCfg.value.listFn({
          ...baseParams,
          page,
          page_size: pageSize,
        });
        const payload = data?.data;
        if (Array.isArray(payload)) {
          rows.value = payload;
          pager.total = payload.length;
          pager.page = 1;
          return;
        }
        const items = payload?.items || [];
        total = Number(payload?.total || 0);
        merged.push(...items);
        if (!items.length || merged.length >= total) {
          break;
        }
        page += 1;
      }
      rows.value = merged;
      pager.total = merged.length;
      pager.page = 1;
      return;
    }

    if (isClusterSnapshotActive.value) {
      pager.page = pagerSnapshotBeforeCluster.page;
      pager.page_size = pagerSnapshotBeforeCluster.page_size;
      isClusterSnapshotActive.value = false;
    }

    const { data } = await pageCfg.value.listFn({
      ...baseParams,
      page: pager.page,
      page_size: pager.page_size,
    });
    const payload = data?.data;
    if (Array.isArray(payload)) {
      rows.value = payload;
      pager.total = payload.length;
      return;
    }
    rows.value = payload?.items || [];
    pager.total = Number(payload?.total || 0);
    pager.page = Number(payload?.page || pager.page);
    pager.page_size = Number(payload?.page_size || pager.page_size);
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载实例失败");
  } finally {
    loading.value = false;
  }
}

function resetPager() {
  pager.page = 1;
  pager.page_size = 20;
  pager.total = 0;
}

async function onPageChange(page) {
  pager.page = Number(page) || 1;
  await loadInstances();
  await runHealthCheck(true);
}

async function onPageSizeChange(size) {
  pager.page_size = Number(size) || 20;
  pager.page = 1;
  await loadInstances();
  await runHealthCheck(true);
}

async function executeHealthCheckBatch(force = false) {
  await loadHealthStatusFromDb(force);
}

async function loadInstanceStatusConfig() {
  try {
    const { data } = await getInstanceStatusConfig();
    const interval = Number(data?.data?.probe_poll_interval_seconds || 30);
    statusProbePollIntervalSec.value = interval > 0 ? interval : 30;
    healthIntervalSec.value = statusProbePollIntervalSec.value;
  } catch (error) {
    statusProbePollIntervalSec.value = 30;
    healthIntervalSec.value = 30;
    console.warn("Load instance status config failed:", error);
  }
}

// 刷新所有实例健康状态（从数据库读取）
async function runHealthCheck(force = false) {
  if (healthBatchRunning.value || !rows.value.length) {
    return;
  }
  healthBatchRunning.value = true;
  healthChecking.value = true;
  try {
    await executeHealthCheckBatch(force);
  } finally {
    healthChecking.value = false;
    healthBatchRunning.value = false;
  }
}

function healthRefreshTtlMs() {
  return statusProbePollIntervalSec.value * 1000;
}

function shouldRefreshHealth(force = false) {
  if (force) {
    return true;
  }
  const ttl = healthRefreshTtlMs();
  return Date.now() - lastHealthFetchAt.value > ttl;
}

async function loadHealthStatusFromDb(force = false) {
  if (!shouldRefreshHealth(force)) {
    return;
  }
  lastHealthFetchAt.value = Date.now();
  const tasks = rows.value.map(row => getInstanceHealth(row.id));
  const results = await Promise.allSettled(tasks);
  results.forEach((result, index) => {
    const row = rows.value[index];
    if (!row) return;
    if (result.status === "fulfilled") {
      const payload = result.value?.data?.data || {};
      if (dbType.value === "mysql") {
        mysqlStatusMap[row.id] = {
          ...(payload.payload_json || {}),
          running_status: payload.running_status || "unknown",
          collected_at: payload.collected_at || null,
        };
      } else {
        const incomingPayload = payload?.payload_json && typeof payload.payload_json === "object" ? payload.payload_json : {};
        const previousPayload = commonHealthMap[row.id]?.payload_json && typeof commonHealthMap[row.id]?.payload_json === "object"
          ? commonHealthMap[row.id].payload_json
          : {};
        const mergedPayload = {
          ...previousPayload,
          ...incomingPayload,
        };
        const usePayload = dbType.value === "redis" ? mergedPayload : incomingPayload;
        commonHealthMap[row.id] = {
          running_status: payload.running_status || "unknown",
          collected_at: payload.collected_at,
          payload_json: usePayload,
        };
      }
      lastCheckAtMap[row.id] = payload.collected_at;
    }
  });
}

// 单个实例健康检测
async function runInstanceHealthCheck(row) {
  await runHealthCheck();
}

// 集群健康检测
async function runClusterHealthCheck() {
  if (!selectedClusterId.value) return;

  healthChecking.value = true;
  try {
    await collectClusterHealth(selectedClusterId.value);
    await reloadAll(true);
    ElMessage.success("集群检活完成");
  } catch (error) {
    console.error("Cluster health check failed:", error);
    ElMessage.error(error.response?.data?.message || "集群检活失败");
  } finally {
    healthChecking.value = false;
  }
}

function triggerAutoHealthCheck() {
  if (healthBatchRunning.value || !rows.value.length) {
    return;
  }

  healthBatchRunning.value = true;
  executeHealthCheckBatch().finally(() => {
    healthBatchRunning.value = false;
  });
}

function clearHealthTimer() {
  if (healthTimer) {
    clearInterval(healthTimer);
    healthTimer = null;
  }
}

function setupHealthTimer() {
  clearHealthTimer();
  const sec = Number(healthIntervalSec.value);
  if (!sec || sec <= 0) {
    return;
  }
  healthTimer = setInterval(() => {
    triggerAutoHealthCheck();
  }, sec * 1000);
}

function clearRelativeTimer() {
  if (relativeTimer) {
    clearInterval(relativeTimer);
    relativeTimer = null;
  }
}

function setupRelativeTimer() {
  clearRelativeTimer();
  relativeTimer = setInterval(() => {
    nowTickMs.value = Date.now();
  }, 1000);
}

// 刷新实例列表定时器（30秒）
function clearRefreshTimer() {
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
}

function setupRefreshTimer() {
  clearRefreshTimer();
  refreshTimer = setInterval(() => {
    reloadAll();
  }, statusProbePollIntervalSec.value * 1000);
}

async function reloadAll(forceHealth = false) {
  await Promise.all([loadClusters(), loadInstances()]);
  // 刷新页面时从数据库读取健康状态
  await loadHealthStatusFromDb(forceHealth);
}

function clearSearchTimer() {
  if (searchTimer) {
    clearTimeout(searchTimer);
    searchTimer = null;
  }
}

async function onSubmit() {
  if (!form.name || !form.host_input || !form.port) {
    ElMessage.warning("请填写实例名、地址和端口");
    return;
  }
  if (form.node_exporter_mode === "custom" && !(form.node_exporter_address || "").trim()) {
    ElMessage.warning("请选择自定义地址时，请填写 node_exporter 地址");
    return;
  }

  saving.value = true;
  try {
    const extraJson = buildExtraJsonPayload();
    if (editingInstanceId.value) {
      const payload = {
        name: form.name,
        host_input: form.host_input,
        port: form.port,
        cluster_id: form.cluster_id,
        extra_json: extraJson,
      };
      if (showUsername.value) {
        payload.username = form.username || null;
      }
      if (form.password) {
        payload.password = form.password;
      }
      await updateInstanceById(editingInstanceId.value, payload);
      ElMessage.success("实例更新成功");
    } else {
      const payload = {
        name: form.name,
        host_input: form.host_input,
        port: form.port,
        password: form.password,
        cluster_id: form.cluster_id,
        extra_json: extraJson,
      };

      if (showUsername.value) {
        payload.username = form.username;
      }
      if (!payload.cluster_id) {
        delete payload.cluster_id;
      }
      if (!payload.password) {
        delete payload.password;
      }
      if (!payload.username) {
        delete payload.username;
      }

      await pageCfg.value.createFn(payload);
      pager.page = 1;
      ElMessage.success("实例创建成功");
    }
    dialogVisible.value = false;
    editingInstanceId.value = null;
    await reloadAll();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || (editingInstanceId.value ? "更新实例失败" : "创建实例失败"));
  } finally {
    saving.value = false;
  }
}

async function removeInstance(row) {
  try {
    await ElMessageBox.confirm(`确认删除实例 ${row.name} (${row.host_input}:${row.port}) 吗？`, "提示", {
      type: "warning",
      confirmButtonText: "删除",
      cancelButtonText: "取消",
    });

    const willTurnEmpty = rows.value.length === 1 && pager.page > 1;
    await deleteInstance(row.id);
    delete mysqlStatusMap[row.id];
    delete commonHealthMap[row.id];
    delete lastCheckAtMap[row.id];

    if (willTurnEmpty) {
      pager.page = Math.max(1, pager.page - 1);
    }

    ElMessage.success("实例已删除");
    await reloadAll();
  } catch (error) {
    if (error !== "cancel" && error !== "close") {
      ElMessage.error(error.response?.data?.message || "删除实例失败");
    }
  }
}

  async function viewDetails(row) {
    if (!showReplicationInfo(row)) {
      return;
    }

    let latestPayload = null;
    try {
      const { data } = await pageCfg.value.detailFn(row.id);
      const payload = data?.data || {};
      latestPayload = payload;
      if (dbType.value === "mysql") {
        mysqlStatusMap[row.id] = {
          ...(mysqlStatusMap[row.id] || {}),
          ...payload,
        };
        if (payload.collected_at) {
          lastCheckAtMap[row.id] = payload.collected_at;
        }
    }

      let rowsData = [];
      try {
        rowsData =
          dbType.value === "mysql"
            ? buildMysqlReplicationRows(payload)
            : dbType.value === "mongodb"
              ? buildMongoReplicationRows(payload)
              : dbType.value === "redis"
                ? buildRedisReplicationRows(payload, row)
              : buildGenericInfoRows(payload);
      } catch (err) {
        rowsData = buildGenericInfoRows(payload);
      }
      openInfoDialog(`${row.name} - ${actionLabel.value}`, rowsData);
    } catch (error) {
      const fallbackPayload = latestPayload || error?.response?.data?.data;
      if (fallbackPayload) {
        const rowsData = dbType.value === "redis" ? buildRedisReplicationRows(fallbackPayload, row) : buildGenericInfoRows(fallbackPayload);
        openInfoDialog(`${row.name} - ${actionLabel.value}`, rowsData);
        ElMessage.warning(`${actionLabel.value}详情解析异常，已展示原始数据`);
        return;
      }
      // eslint-disable-next-line no-console
      console.error("viewDetails failed", error);
      ElMessage.error(error.response?.data?.message || "获取详情失败");
    }
  }

  function buildMongoDetailRows(payload) {
    const opSummary = [
      payload.op_insert ?? "-",
      payload.op_query ?? "-",
      payload.op_update ?? "-",
      payload.op_delete ?? "-",
    ].join(" / ");

    let readWriteRatio = "-";
    if (payload.op_read_pct !== undefined && payload.op_write_pct !== undefined) {
      readWriteRatio = `${payload.op_read_pct}% / ${payload.op_write_pct}%`;
    }

    const rows = [
      { label: "运行情况", value: runningText(payload.running_status) },
      { label: "心跳时间", value: formatDateTime(payload.collected_at) },
      { label: "实例启动时间", value: formatDateTime(payload.started_at) },
      { label: "版本", value: normalizeInfoValue(payload.version) },
      { label: "CPU核数", value: normalizeInfoValue(payload.host_cpu_cores) },
      { label: "内存总大小", value: formatBytes(payload.host_memory_total_bytes) },
      { label: "当前连接数", value: normalizeInfoValue(payload.connections_current) },
      { label: "最大连接数", value: normalizeInfoValue(payload.connections_max) },
      { label: "锁监控", value: normalizeInfoValue(payload.lock_waits) },
      { label: "复制延迟(s)", value: normalizeInfoValue(payload.repl_lag_seconds) },
      { label: "操作统计(插入/查询/更新/删除)", value: opSummary },
      { label: "内存缓存使用率", value: asPercentText(payload.cache_used_pct) },
      { label: "读写比例(读/写)", value: readWriteRatio },
      { label: "CPU使用率", value: asPercentText(payload.host_cpu_usage_pct) },
      { label: "内存使用率", value: asPercentText(payload.host_memory_usage_pct) },
      { label: "数据盘使用率", value: buildDataDiskSummary(payload) },
      { label: "错误信息", value: normalizeInfoValue(payload.collect_error) },
      { label: "Exporter错误", value: normalizeInfoValue(payload.node_exporter_error) },
    ];
    rows.push(...buildDiskRows(payload));
    rows.push(...buildNetworkRows(payload));
    return rows;
  }

  function buildRedisDetailRows(payload) {
    const mergedForMode = { id: "__detail__", payload_json: payload };
    const rows = [
      { label: "运行情况", value: runningText(payload.running_status) },
      { label: "心跳时间", value: formatDateTime(payload.collected_at) },
      { label: "主从角色", value: redisRoleText(String(payload.role || "").toLowerCase()) },
      { label: "高可用模式", value: redisHaModeText(redisHaMode(mergedForMode)) },
      { label: "版本", value: normalizeInfoValue(payload.version || payload.redis_version) },
      { label: "当前连接数", value: normalizeInfoValue(payload.connected_clients) },
      { label: "最大连接数", value: normalizeInfoValue(payload.maxclients) },
      { label: "实例内存使用率", value: redisContainerMemorySummary(payload) },
      { label: "配置最大内存", value: formatBytes(payload.maxmemory) },
      { label: "当前使用内存", value: formatBytes(payload.used_memory) },
      { label: "当前内存使用率", value: asPercentText(payload.memory_usage_pct) },
      { label: "内存峰值", value: formatBytes(payload.used_memory_peak) },
      { label: "复制源信息", value: normalizeInfoValue(payload.replication_source || (payload.master_host && payload.master_port ? `${payload.master_host}:${payload.master_port}` : payload.master_host)) },
      { label: "复制延迟(s)", value: normalizeInfoValue(payload.replication_lag_seconds) },
      { label: "Key数量", value: normalizeInfoValue(payload.keyspace_total_keys) },
      { label: "活跃DB数量", value: normalizeInfoValue(payload.keyspace_db_count) },
      { label: "命中数", value: normalizeInfoValue(payload.keyspace_hits) },
      { label: "未命中数", value: normalizeInfoValue(payload.keyspace_misses) },
      { label: "Node Exporter状态", value: normalizeInfoValue(payload.node_exporter_status) },
      { label: "Node Exporter模式", value: normalizeInfoValue(payload.node_exporter_mode) },
      { label: "Node Exporter地址", value: normalizeInfoValue(payload.node_exporter_endpoint) },
      { label: "CPU核数", value: normalizeInfoValue(payload.host_cpu_cores) },
      { label: "主机CPU使用率", value: asPercentText(payload.host_cpu_usage_pct) },
      { label: "主机内存使用率", value: asPercentText(payload.host_memory_usage_pct) },
      { label: "主机内存总大小", value: formatBytes(payload.host_memory_total_bytes) },
      { label: "数据盘使用率", value: buildDataDiskSummary(payload) },
      { label: "错误信息", value: normalizeInfoValue(payload.collect_error) },
      { label: "Exporter错误", value: normalizeInfoValue(payload.node_exporter_error) },
    ];
    rows.push(...buildDiskRows(payload));
    rows.push(...buildNetworkRows(payload));
    return rows;
  }

  async function viewInstanceDetail(row) {
    if (!showInstanceDetail(row)) {
      return;
    }

    try {
      const { data } = await pageCfg.value.instanceDetailFn(row.id);
      const payload = data?.data || {};
      if (dbType.value === "mysql") {
        mysqlStatusMap[row.id] = {
          ...(mysqlStatusMap[row.id] || {}),
          running_status: payload.running_status,
          version: payload.version,
          threads_connected: payload.threads_connected,
          threads_running: payload.threads_running,
        };
        if (payload.collected_at) {
          lastCheckAtMap[row.id] = payload.collected_at;
        }
        openInfoDialog(`${row.name} - 实例详情`, buildMysqlDetailRows(payload));
        return;
      }
      if (dbType.value === "mongodb") {
        const merged = {
          ...(payload.payload_json || {}),
          running_status: payload.running_status,
          collected_at: payload.collected_at,
        };
        openInfoDialog(`${row.name} - 实例详情`, buildMongoDetailRows(merged));
        return;
      }
      if (dbType.value === "redis") {
        const merged = {
          ...(payload.payload_json || {}),
          running_status: payload.running_status,
          collected_at: payload.collected_at,
        };
        openInfoDialog(`${row.name} - 实例详情`, buildRedisDetailRows(merged));
        return;
      }
    } catch (error) {
      const fallback = mysqlStatus(row);
      if (fallback && Object.keys(fallback).length) {
        openInfoDialog(
        `${row.name} - 实例详情`,
        buildMysqlDetailRows({
          source: fallback.source || "snapshot",
          running_status: fallback.running_status || rowRunningStatus(row),
          collected_at: fallback.collected_at || rowLastCheckAt(row),
          started_at: fallback.started_at,
          uptime: fallback.uptime,
          version: fallback.version,
          threads_connected: fallback.threads_connected,
          threads_running: fallback.threads_running,
          max_connections: fallback.max_connections,
          lock_waits: fallback.lock_waits,
          qps: fallback.qps,
          tps: fallback.tps,
          node_exporter_status: fallback.node_exporter_status,
          node_exporter_error: fallback.node_exporter_error,
          host_cpu_usage_pct: fallback.host_cpu_usage_pct,
          host_memory_usage_pct: fallback.host_memory_usage_pct,
          host_data_disk_usage_pct: fallback.host_data_disk_usage_pct,
          host_data_disk_mountpoint: fallback.host_data_disk_mountpoint,
          host_data_disk_size_bytes: fallback.host_data_disk_size_bytes,
          host_disk_entries: fallback.host_disk_entries,
          host_net_rates: fallback.host_net_rates,
          collect_error: error.response?.data?.message || error.message || "collect failed",
        }),
      );
      ElMessage.warning("实时详情采集失败，已展示最近一次心跳数据");
      return;
    }
    ElMessage.error(error.response?.data?.message || "获取实例详情失败");
  }
}

onMounted(async () => {
  resetForm();
  resetPager();
  await loadInstanceStatusConfig();
  await reloadAll();
  setupHealthTimer();
});

onActivated(async () => {
  // 页面激活时启动定时器（keep-alive 缓存后重新激活）
  await loadInstanceStatusConfig();
  setupHealthTimer();
  setupRelativeTimer();
  setupRefreshTimer();
});

onDeactivated(() => {
  // 页面缓存时停止定时器
  clearHealthTimer();
  clearRelativeTimer();
  clearRefreshTimer();
  clearSearchTimer();
});

onBeforeUnmount(() => {
  // 组件真正销毁时清理
  clearHealthTimer();
  clearRelativeTimer();
  clearRefreshTimer();
  clearSearchTimer();
});

watch(
  () => dbType.value,
  async () => {
    clearStatusMaps();
    hoveredClusterId.value = null;
    hoveredRowId.value = null;
    selectedBusinessLine.value = null;
    selectedEnvironment.value = null;
    selectedClusterId.value = null;
    keyword.value = "";
    resetPager();
    resetForm();
    lastHealthFetchAt.value = 0;
    await reloadAll();
    setupHealthTimer();
  },
);

watch(
  () => keyword.value,
  () => {
    clearSearchTimer();
    searchTimer = setTimeout(async () => {
      pager.page = 1;
      await loadInstances();
      await runHealthCheck(true);
    }, 300);
  },
);
</script>

<style scoped>
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.actions { gap: 6px;
  flex-wrap: wrap;
}

.actions {
  display: inline-flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}

.keyword-input {
  width: 180px;
}

.interval-select {
  width: 108px;
}

.table-wrap {
  width: 100%;
  overflow-x: auto;
  overflow-y: hidden;
}

.address-cell {
  display: inline-flex;
  flex-direction: column;
  gap: 2px;
  line-height: 1.2;
}

.cluster-cell {
  display: inline-flex;
  flex-direction: column;
  gap: 2px;
  line-height: 1.2;
  width: 100%;
  min-width: 0;
}

.cluster-part {
  display: flex;
  align-items: flex-start;
  width: 100%;
  min-width: 0;
}

.cluster-label {
  flex: 0 0 auto;
  color: #64748b;
}

.cluster-value {
  flex: 1 1 auto;
  width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.address-domain {
  color: #334155;
  font-weight: 500;
}

.address-ip {
  color: #64748b;
  font-size: 12px;
}

.io-sql-tags {
  display: inline-flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}

.ext-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  line-height: 1.2;
  white-space: normal;
  min-width: 48px;
}

.op-actions {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  line-height: 1.2;
  white-space: normal;
  min-width: 40px;
}

.op-actions .no-perm-hint {
  color: #94a3b8;
  font-size: 12px;
}

.table-link {
  padding: 0;
  margin: 0;
  border: 0;
  background: transparent;
  font-size: 12px;
  line-height: 16px;
  cursor: pointer;
  text-align: left;
}

.table-link--primary {
  color: #409eff;
}

.table-link--danger {
  color: #f56c6c;
}

.table-link:hover {
  opacity: 0.85;
}

.muted-text {
  color: #8b98aa;
}

.pagination-wrap {
  margin-top: 8px;
  display: flex;
  justify-content: flex-end;
}

  .info-value {
    white-space: pre-wrap;
    word-break: break-word;
    color: #374151;
  }

  .info-list {
    margin: 0;
    padding-left: 16px;
    white-space: pre-wrap;
    word-break: break-word;
    color: #374151;
  }

.metric-tag {
  border-color: #b7eb8f;
  background-color: #f6ffed;
  color: #389e0d;
}

.metric-tag--warn {
  border-color: #ffe58f;
  background-color: #fffbe6;
  color: #d48806;
}

.metric-tag--hot {
  border-color: #ffb3b3;
  background-color: #fff1f0;
  color: #cf1322;
}

:deep(.el-card__header) {
  padding: 10px 14px;
}

:deep(.el-card__body) {
  padding: 12px 14px;
}

:deep(.instance-table .el-table__cell) {
  padding-top: 4px;
  padding-bottom: 4px;
}

:deep(.instance-table .cell) {
  padding-left: 4px;
  padding-right: 4px;
  display: flex;
  align-items: center;
  min-height: 24px;
}

:deep(.instance-table) {
  font-size: 12px;
}

.instance-table {
  width: 100%;
}

:deep(.instance-table .el-tag) {
  height: 18px;
  line-height: 18px;
  padding: 0 6px;
  font-size: 11px;
}

:deep(.instance-table .cluster-col .cell),
:deep(.instance-table .name-col .cell),
:deep(.instance-table .address-col .cell) {
  padding-left: 5px;
  padding-right: 5px;
  min-width: 0;
}

:deep(.instance-table .name-col .cell),
:deep(.instance-table .cluster-col .cell) {
  overflow: hidden;
}

:deep(.instance-table .name-col .cell) {
  white-space: normal;
  word-break: break-all;
  line-height: 1.4;
}

:deep(.instance-table .name-col .cell > span) {
  display: block;
  width: 100%;
  white-space: normal;
  word-break: break-all;
  line-height: 1.4;
}

:deep(.instance-table .address-col .cell) {
  overflow: hidden;
}

.address-cell {
  width: 100%;
  min-width: 0;
}

.address-domain,
.address-ip {
  width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

:deep(.instance-table .ext-col .cell),
:deep(.instance-table .op-col .cell) {
  display: block;
  line-height: 1.2;
}

:deep(.instance-table .physical-col .cell) {
  max-width: 17ch;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

:deep(.instance-table .redis-repl-source-col .cell) {
  max-width: 20ch;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.redis-memory-cell {
  display: inline-flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  line-height: 1.15;
}

.redis-memory-subtag {
  color: #64748b;
  background: #f4f6f8;
  border-color: #d8e0e8;
  white-space: nowrap;
}

:deep(.instance-table th.el-table__cell) {
  background: #fafbfd;
}

:deep(.el-table .cluster-related-row > td) {
  background-color: #eaf4ff !important;
}

:deep(.el-table .cluster-selected-row > td) {
  background-color: #ffe58e !important;
}

:deep(.el-table .cluster-selected-row:hover > td) {
  background-color: #ffd966 !important;
}

.namespace-select,
.cluster-select {
  width: 150px;
}

@media (max-width: 1360px) {
  .actions {
    justify-content: flex-start;
  }

  .keyword-input {
    width: 160px;
  }
}

@media (max-width: 1120px) {
  .keyword-input {
    width: 140px;
  }

  .interval-select {
    width: 96px;
  }

  :deep(.instance-table .el-table__cell) {
    padding-top: 6px;
    padding-bottom: 6px;
  }
}
</style>
