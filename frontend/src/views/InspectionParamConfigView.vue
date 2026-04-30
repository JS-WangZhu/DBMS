<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>巡检参数管理</span>
          <div class="header-actions">
            <el-button @click="loadData">刷新</el-button>
            <el-button type="primary" :loading="saving" @click="saveConfig">保存</el-button>
          </div>
        </div>
      </template>

      <el-form :model="form" label-width="180px">
        <el-form-item label="启用周期巡检">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item label="巡检周期（秒）">
          <el-input-number v-model="form.interval_seconds" :min="10" :step="10" />
        </el-form-item>
        <el-form-item label="采集超时（秒）">
          <el-input-number v-model="form.collect_timeout_seconds" :min="3" :step="1" />
        </el-form-item>
        <el-form-item label="启用异常通知">
          <el-switch v-model="form.notify_enabled" />
        </el-form-item>
        <el-form-item label="启用恢复通知">
          <el-switch v-model="form.notify_recovery" />
        </el-form-item>
        <el-form-item label="通知地址">
          <el-select v-model="form.notify_target_ids" multiple filterable clearable style="width: 100%">
            <el-option
              v-for="item in notifyTargets"
              :key="item.id"
              :label="`${item.name} (${item.channel})`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="通知静默集群">
          <el-select v-model="form.muted_cluster_ids" multiple filterable clearable style="width: 100%">
            <el-option
              v-for="item in clusters"
              :key="item.id"
              :label="`${item.business_line || '-'} / ${item.environment || '-'} / ${item.name}`"
              :value="item.id"
            />
          </el-select>
        </el-form-item>

        <el-divider>异常阈值</el-divider>
        <el-form-item label="MySQL复制延迟阈值（秒）">
          <el-input-number v-model="form.thresholds.mysql_replication_lag_seconds" :min="1" />
        </el-form-item>
        <el-form-item label="MySQL连接使用率阈值（%）">
          <el-input-number v-model="form.thresholds.mysql_connection_usage_pct" :min="1" :max="100" />
        </el-form-item>
        <el-form-item label="MongoDB复制延迟阈值（秒）">
          <el-input-number v-model="form.thresholds.mongodb_repl_lag_seconds" :min="1" />
        </el-form-item>
        <el-form-item label="MongoDB缓存使用率阈值（%）">
          <el-input-number v-model="form.thresholds.mongodb_cache_used_pct" :min="1" :max="100" />
        </el-form-item>
        <el-form-item label="Redis内存使用率阈值（%）">
          <el-input-number v-model="form.thresholds.redis_memory_usage_pct" :min="1" :max="100" />
        </el-form-item>
        <el-form-item label="主机CPU使用率阈值（%）">
          <el-input-number v-model="form.thresholds.host_cpu_usage_pct" :min="1" :max="100" />
        </el-form-item>
        <el-form-item label="主机内存使用率阈值（%）">
          <el-input-number v-model="form.thresholds.host_memory_usage_pct" :min="1" :max="100" />
        </el-form-item>
        <el-form-item label="主机磁盘使用率阈值（%）">
          <el-input-number v-model="form.thresholds.host_data_disk_usage_pct" :min="1" :max="100" />
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { getInspectionConfig, getInspectionConfigOptions, updateInspectionConfig } from "../api/modules/inspection";

const saving = ref(false);
const notifyTargets = ref([]);
const clusters = ref([]);
const form = reactive({
  enabled: true,
  interval_seconds: 60,
  collect_timeout_seconds: 8,
  notify_enabled: true,
  notify_recovery: true,
  notify_target_ids: [],
  muted_cluster_ids: [],
  thresholds: {
    mysql_replication_lag_seconds: 60,
    mysql_connection_usage_pct: 90,
    mongodb_repl_lag_seconds: 60,
    mongodb_cache_used_pct: 90,
    redis_memory_usage_pct: 90,
    host_cpu_usage_pct: 90,
    host_memory_usage_pct: 90,
    host_data_disk_usage_pct: 90,
  },
});

function applyConfig(data) {
  form.enabled = !!data.enabled;
  form.interval_seconds = data.interval_seconds || 60;
  form.collect_timeout_seconds = data.collect_timeout_seconds || 8;
  form.notify_enabled = !!data.notify_enabled;
  form.notify_recovery = !!data.notify_recovery;
  form.notify_target_ids = Array.isArray(data.notify_target_ids) ? [...data.notify_target_ids] : [];
  form.muted_cluster_ids = Array.isArray(data.muted_cluster_ids) ? [...data.muted_cluster_ids] : [];
  form.thresholds = {
    ...form.thresholds,
    ...(data.extra_json?.thresholds || {}),
  };
}

async function loadData() {
  try {
    const [{ data: configResp }, { data: optionResp }] = await Promise.all([
      getInspectionConfig(),
      getInspectionConfigOptions(),
    ]);
    applyConfig(configResp?.data || {});
    notifyTargets.value = optionResp?.data?.notify_targets || [];
    clusters.value = optionResp?.data?.clusters || [];
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载巡检配置失败");
  }
}

async function saveConfig() {
  saving.value = true;
  try {
    await updateInspectionConfig({
      enabled: form.enabled,
      interval_seconds: form.interval_seconds,
      collect_timeout_seconds: form.collect_timeout_seconds,
      notify_enabled: form.notify_enabled,
      notify_recovery: form.notify_recovery,
      notify_target_ids: form.notify_target_ids,
      muted_cluster_ids: form.muted_cluster_ids,
      thresholds: form.thresholds,
    });
    ElMessage.success("保存成功");
    await loadData();
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "保存巡检配置失败");
  } finally {
    saving.value = false;
  }
}

onMounted(loadData);
</script>

<style scoped>
.page { padding: 20px; }
.header-row { display: flex; justify-content: space-between; align-items: center; }
.header-actions { display: flex; gap: 10px; }
</style>
