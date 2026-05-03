<template>
  <el-card>
    <template #header>
      <div class="header-row">
        <span>MongoDB 连接管理</span>
        <div class="actions">
          <el-select v-model="selectedBusinessLine" clearable placeholder="选择项目" class="filter-select">
            <el-option v-for="line in businessLineOptions" :key="line" :label="line" :value="line" />
          </el-select>
          <el-select v-model="selectedEnvironment" clearable placeholder="选择环境" class="filter-select">
            <el-option v-for="env in environmentOptions" :key="env" :label="env" :value="env" />
          </el-select>
          <el-select v-model="selectedClusterId" clearable placeholder="选择集群" class="filter-select">
            <el-option v-for="cluster in clusterOptions" :key="cluster.id" :label="cluster.name" :value="cluster.id" />
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
      <el-table-column label="副本集" min-width="140">
        <template #default="scope">{{ scope.row.latest?.summary?.set_name || "-" }}</template>
      </el-table-column>
      <el-table-column label="总节点" width="90">
        <template #default="scope">{{ scope.row.latest?.summary?.total ?? "-" }}</template>
      </el-table-column>
      <el-table-column label="PRIMARY" width="100">
        <template #default="scope">
          <el-tag :type="(scope.row.latest?.summary?.primary_count || 0) > 0 ? 'danger' : 'info'">
            {{ scope.row.latest?.summary?.primary_count ?? "-" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="SECONDARY" width="110">
        <template #default="scope">
          <el-tag type="success">{{ scope.row.latest?.summary?.secondary_count ?? "-" }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="ARBITER" width="100">
        <template #default="scope">
          <el-tag type="warning">{{ scope.row.latest?.summary?.arbiter_count ?? "-" }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="可达 / 不可达" width="130">
        <template #default="scope">
          <el-tag :type="(scope.row.latest?.summary?.unreachable_count || 0) === 0 ? 'success' : 'danger'">
            {{ scope.row.latest?.summary?.reachable_count ?? "-" }} / {{ scope.row.latest?.summary?.unreachable_count ?? "-" }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="最近采集" min-width="170">
        <template #default="scope">{{ formatBeijingTime(scope.row.latest?.collected_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="260" fixed="right">
        <template #default="scope">
          <el-button link type="primary" @click="openProbe(scope.row)">连接性探测</el-button>
          <el-button link type="success" @click="openHistory(scope.row)">拓扑变更历史</el-button>
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

    <el-dialog v-model="probeDialogVisible" title="MongoDB 副本集连接性探测" width="1080px" top="5vh">
      <div v-loading="probing">
        <el-descriptions :column="4" border>
          <el-descriptions-item label="集群">{{ probeCluster?.name || "-" }}</el-descriptions-item>
          <el-descriptions-item label="副本集">{{ probeResult?.summary?.set_name || "-" }}</el-descriptions-item>
          <el-descriptions-item label="探测时间">{{ formatBeijingTime(probeResult?.probed_at) }}</el-descriptions-item>
          <el-descriptions-item label="总节点">{{ probeResult?.summary?.total ?? "-" }}</el-descriptions-item>
          <el-descriptions-item label="PRIMARY">
            <el-tag :type="(probeResult?.summary?.primary_count || 0) > 0 ? 'danger' : 'info'">{{ probeResult?.summary?.primary_count ?? "-" }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="SECONDARY">
            <el-tag type="success">{{ probeResult?.summary?.secondary_count ?? "-" }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="ARBITER">
            <el-tag type="warning">{{ probeResult?.summary?.arbiter_count ?? "-" }}</el-tag>
          </el-descriptions-item>
          <el-descriptions-item label="可达 / 不可达">
            <el-tag :type="(probeResult?.summary?.unreachable_count || 0) === 0 ? 'success' : 'danger'">
              {{ probeResult?.summary?.reachable_count ?? "-" }} / {{ probeResult?.summary?.unreachable_count ?? "-" }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>

        <el-table :data="probeResult?.nodes || []" stripe class="mt-16">
          <el-table-column prop="instance_name" label="实例" min-width="150" />
          <el-table-column label="地址" min-width="200">
            <template #default="scope">{{ scope.row.host }}:{{ scope.row.port }}</template>
          </el-table-column>
          <el-table-column label="可达" width="90">
            <template #default="scope">
              <el-tag :type="scope.row.reachable ? 'success' : 'danger'">{{ scope.row.reachable ? "是" : "否" }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="角色" width="120">
            <template #default="scope">
              <el-tag :type="roleTagType(scope.row.role)">{{ scope.row.role || "-" }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="副本集" min-width="140" show-overflow-tooltip>
            <template #default="scope">{{ scope.row.set_name || "-" }}</template>
          </el-table-column>
          <el-table-column label="仲裁" width="80">
            <template #default="scope">
              <el-tag v-if="scope.row.is_arbiter" type="warning">是</el-tag>
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column label="异常原因" min-width="240" show-overflow-tooltip>
            <template #default="scope">{{ scope.row.error || "-" }}</template>
          </el-table-column>
        </el-table>
      </div>
      <template #footer>
        <el-button @click="probeDialogVisible = false">关闭</el-button>
        <el-button type="primary" :loading="probing" @click="runProbe">重新探测</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="historyDialogVisible" title="MongoDB 拓扑变更历史" width="1080px" top="5vh">
      <div v-loading="historyLoading">
        <el-table :data="historyData.items" stripe>
          <el-table-column label="变更时间" min-width="180">
            <template #default="scope">{{ formatBeijingTime(scope.row.changed_at) }}</template>
          </el-table-column>
          <el-table-column label="副本集" min-width="140">
            <template #default="scope">{{ scope.row.topology?.set_name || "-" }}</template>
          </el-table-column>
          <el-table-column label="总节点" width="90">
            <template #default="scope">{{ scope.row.topology?.total_members ?? "-" }}</template>
          </el-table-column>
          <el-table-column label="P / S / A" width="120">
            <template #default="scope">
              {{ scope.row.topology?.primary_count ?? 0 }} / {{ scope.row.topology?.secondary_count ?? 0 }} / {{ scope.row.topology?.arbiter_count ?? 0 }}
            </template>
          </el-table-column>
          <el-table-column label="成员" min-width="320">
            <template #default="scope">
              <el-tag
                v-for="m in scope.row.topology?.members || []"
                :key="m.host"
                :type="roleTagType(m.role)"
                class="member-tag"
              >
                {{ m.host }} [{{ m.role }}]
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
            :total="historyData.total"
            :current-page="historyData.page"
            :page-size="historyData.page_size"
            @current-change="onHistoryPageChange"
          />
        </div>
      </div>
    </el-dialog>
  </el-card>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from "vue";
import { ElMessage } from "element-plus";
import {
  listClusters,
  probeClusterConnectivity,
  clusterConnectivityLatest,
  listClusterTopologyHistory,
} from "../api/modules/clusters";
import { formatBeijingTime } from "../utils/time";

const loading = ref(false);
const rows = ref([]);
const keyword = ref("");
const selectedBusinessLine = ref("");
const selectedEnvironment = ref("");
const selectedClusterId = ref(null);

const pager = reactive({ page: 1, page_size: 20 });

const probeDialogVisible = ref(false);
const probing = ref(false);
const probeCluster = ref(null);
const probeResult = ref(null);

const historyDialogVisible = ref(false);
const historyLoading = ref(false);
const historyCluster = ref(null);
const historyData = reactive({ items: [], total: 0, page: 1, page_size: 10 });

function matchesFilters(row, excludeKey = "") {
  if (!row) return false;
  if (excludeKey !== "business_line" && selectedBusinessLine.value && (row.business_line || row.namespace) !== selectedBusinessLine.value) return false;
  if (excludeKey !== "environment" && selectedEnvironment.value && row.environment !== selectedEnvironment.value) return false;
  if (excludeKey !== "cluster_id" && selectedClusterId.value && row.id !== selectedClusterId.value) return false;
  return true;
}

const businessLineOptions = computed(() => {
  const values = new Set(rows.value.filter((row) => matchesFilters(row, "business_line")).map((row) => row.business_line || row.namespace).filter(Boolean));
  return Array.from(values).sort();
});

const environmentOptions = computed(() => {
  const values = new Set(rows.value.filter((row) => matchesFilters(row, "environment")).map((row) => row.environment).filter(Boolean));
  return Array.from(values).sort();
});

const clusterOptions = computed(() => rows.value.filter((row) => matchesFilters(row, "cluster_id")));

const displayRows = computed(() => {
  const kw = keyword.value.trim().toLowerCase();
  return rows.value.filter((row) => {
    if (!matchesFilters(row)) return false;
    if (!kw) return true;
    const text = `${row.business_line || row.namespace || ""} ${row.environment || ""} ${row.name || ""} ${row.latest?.summary?.set_name || ""}`.toLowerCase();
    return text.includes(kw);
  });
});

const pagedRows = computed(() => {
  const start = (pager.page - 1) * pager.page_size;
  return displayRows.value.slice(start, start + pager.page_size);
});

function onPageChange(page) {
  pager.page = page;
}

function onPageSizeChange(size) {
  pager.page_size = size;
  pager.page = 1;
}

function roleTagType(role) {
  const text = String(role || "").toUpperCase();
  if (text === "PRIMARY") return "danger";
  if (text === "SECONDARY") return "success";
  if (text === "ARBITER") return "warning";
  return "info";
}

async function loadData() {
  loading.value = true;
  try {
    const { data } = await listClusters("mongodb");
    const items = data.data?.items || data.data || [];
    rows.value = items.map((item) => ({ ...item, latest: null }));
    await Promise.all(
      rows.value.map(async (row) => {
        try {
          const { data: latestResp } = await clusterConnectivityLatest(row.id);
          row.latest = latestResp.data || null;
        } catch {
          row.latest = null;
        }
      }),
    );
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载集群失败");
  } finally {
    loading.value = false;
  }
}

async function openProbe(row) {
  probeCluster.value = row;
  probeDialogVisible.value = true;
  probeResult.value = null;
  await runProbe();
}

async function runProbe() {
  if (!probeCluster.value) return;
  probing.value = true;
  try {
    const { data } = await probeClusterConnectivity(probeCluster.value.id);
    probeResult.value = data.data || null;
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "连接性探测失败");
  } finally {
    probing.value = false;
  }
}

async function openHistory(row) {
  historyCluster.value = row;
  historyDialogVisible.value = true;
  historyData.page = 1;
  await loadHistory(1);
}

async function loadHistory(page) {
  if (!historyCluster.value) return;
  historyLoading.value = true;
  try {
    const { data } = await listClusterTopologyHistory(historyCluster.value.id, page, historyData.page_size);
    const payload = data.data || {};
    historyData.items = payload.items || [];
    historyData.total = payload.total || 0;
    historyData.page = payload.page || page;
    historyData.page_size = payload.page_size || historyData.page_size;
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载拓扑历史失败");
  } finally {
    historyLoading.value = false;
  }
}

function onHistoryPageChange(page) {
  loadHistory(page);
}

watch(
  () => [keyword.value, selectedBusinessLine.value, selectedEnvironment.value, selectedClusterId.value],
  () => {
    pager.page = 1;
  },
);

onMounted(loadData);
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

.mt-16 {
  margin-top: 16px;
}

.member-tag {
  margin-right: 6px;
  margin-bottom: 4px;
}
</style>
