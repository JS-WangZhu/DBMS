<template>
  <div class="page">
    <div class="page-header">
      <div class="page-header-left">
        <div class="page-title">巡检参数管理</div>
        <div class="page-subtitle">配置巡检周期、告警阈值与通知策略</div>
      </div>
      <div class="page-header-actions">
        <el-button :icon="Refresh" @click="loadData">刷新</el-button>
        <el-button type="primary" :loading="saving" :icon="Check" @click="saveConfig">保存</el-button>
      </div>
    </div>

    <!-- 基础设置 -->
    <el-card class="section-card" shadow="never">
      <template #header>
        <div class="section-header section-header--blue">
          <el-icon><Setting /></el-icon>
          <span class="section-title">基础设置</span>
          <span class="section-desc">控制巡检任务的调度与采集行为</span>
        </div>
      </template>
      <el-form :model="form" label-width="140px" label-position="right">
        <el-row :gutter="24">
          <el-col :xs="24" :sm="12">
            <el-form-item label="启用周期巡检">
              <el-switch v-model="form.enabled" active-text="开" inactive-text="关" inline-prompt />
              <span class="hint-text">关闭后定时巡检任务停止</span>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="巡检周期（秒）">
              <el-input-number v-model="form.interval_seconds" :min="10" :step="10" controls-position="right" style="width: 180px" />
              <span class="hint-text">最小 10 秒，建议 30~120 秒</span>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="采集超时（秒）">
              <el-input-number v-model="form.collect_timeout_seconds" :min="3" :step="1" controls-position="right" style="width: 180px" />
              <span class="hint-text">单实例采集最长等待时间</span>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <!-- 通知设置 -->
    <el-card class="section-card" shadow="never">
      <template #header>
        <div class="section-header section-header--amber">
          <el-icon><Bell /></el-icon>
          <span class="section-title">通知设置</span>
          <span class="section-desc">告警触发及恢复后的通知推送</span>
        </div>
      </template>
      <el-form :model="form" label-width="140px" label-position="right">
        <el-row :gutter="24">
          <el-col :xs="24" :sm="12">
            <el-form-item label="启用异常通知">
              <el-switch v-model="form.notify_enabled" active-text="开" inactive-text="关" inline-prompt />
              <span class="hint-text">异常产生时推送到通知地址</span>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="启用恢复通知">
              <el-switch v-model="form.notify_recovery" active-text="开" inactive-text="关" inline-prompt />
              <span class="hint-text">告警恢复后推送提示</span>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="持续告警间隔">
              <el-input-number v-model="form.notify_repeat_minutes" :min="1" :max="10080" controls-position="right" style="width: 180px" />
              <span class="unit-text">分钟</span>
              <span class="hint-text">异常未恢复时按此间隔继续通知，默认60分钟</span>
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="通知地址">
              <el-select
                v-model="form.notify_target_ids"
                multiple
                filterable
                clearable
                placeholder="选择通知地址（企业微信/钉钉/邮件等）"
                style="width: 100%"
              >
                <el-option
                  v-for="item in notifyTargets"
                  :key="item.id"
                  :label="`${item.name} (${item.channel})`"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item label="通知静默集群">
              <el-select
                v-model="form.muted_cluster_ids"
                multiple
                filterable
                clearable
                placeholder="选择免告警集群（不触发通知）"
                style="width: 100%"
              >
                <el-option
                  v-for="item in clusters"
                  :key="item.id"
                  :label="`${item.business_line || '-'} / ${item.environment || '-'} / ${item.name}`"
                  :value="item.id"
                />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>

    <!-- 异常阈值 -->
    <el-card class="section-card" shadow="never">
      <template #header>
        <div class="section-header section-header--rose">
          <el-icon><Warning /></el-icon>
          <span class="section-title">异常阈值</span>
          <span class="section-desc">超过阈值后触发告警</span>
        </div>
      </template>
      <el-form :model="form" label-width="160px" label-position="right">
        <!-- MySQL -->
        <div class="threshold-group">
          <div class="threshold-group-title">
            <span class="group-badge group-badge--mysql">MySQL</span>
          </div>
          <el-row :gutter="24">
            <el-col :xs="24" :sm="12">
              <el-form-item label="复制延迟阈值（秒）">
                <el-input-number v-model="form.thresholds.mysql_replication_lag_seconds" :min="1" controls-position="right" style="width: 180px" />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12">
              <el-form-item label="连接使用率（%）">
                <el-input-number v-model="form.thresholds.mysql_connection_usage_pct" :min="1" :max="100" controls-position="right" style="width: 180px" />
              </el-form-item>
            </el-col>
          </el-row>
        </div>

        <!-- MongoDB -->
        <div class="threshold-group">
          <div class="threshold-group-title">
            <span class="group-badge group-badge--mongodb">MongoDB</span>
          </div>
          <el-row :gutter="24">
            <el-col :xs="24" :sm="12">
              <el-form-item label="复制延迟阈值（秒）">
                <el-input-number v-model="form.thresholds.mongodb_repl_lag_seconds" :min="1" controls-position="right" style="width: 180px" />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12">
              <el-form-item label="缓存使用率（%）">
                <el-input-number v-model="form.thresholds.mongodb_cache_used_pct" :min="1" :max="100" controls-position="right" style="width: 180px" />
              </el-form-item>
            </el-col>
          </el-row>
        </div>

        <!-- Redis -->
        <div class="threshold-group">
          <div class="threshold-group-title">
            <span class="group-badge group-badge--redis">Redis</span>
          </div>
          <el-row :gutter="24">
            <el-col :xs="24" :sm="12">
              <el-form-item label="内存使用率（%）">
                <el-input-number v-model="form.thresholds.redis_memory_usage_pct" :min="1" :max="100" controls-position="right" style="width: 180px" />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12">
              <el-form-item label="连接数使用率（%）">
                <el-input-number v-model="form.thresholds.redis_connection_usage_pct" :min="1" :max="100" controls-position="right" style="width: 180px" />
              </el-form-item>
            </el-col>
          </el-row>
        </div>

        <!-- PostgreSQL -->
        <div class="threshold-group">
          <div class="threshold-group-title">
            <span class="group-badge group-badge--postgresql">PostgreSQL</span>
          </div>
          <el-row :gutter="24">
            <el-col :xs="24" :sm="12">
              <el-form-item :label="'\u590d\u5236\u5ef6\u8fdf\u9608\u503c\uff08\u79d2\uff09'">
                <el-input-number v-model="form.thresholds.postgresql_replication_lag_seconds" :min="1" controls-position="right" style="width: 180px" />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12">
              <el-form-item :label="'\u8fde\u63a5\u4f7f\u7528\u7387\uff08%\uff09'">
                <el-input-number v-model="form.thresholds.postgresql_connection_usage_pct" :min="1" :max="100" controls-position="right" style="width: 180px" />
              </el-form-item>
            </el-col>
          </el-row>
        </div>

        <!-- 主机 -->
        <div class="threshold-group">
          <div class="threshold-group-title">
            <span class="group-badge group-badge--host">主机</span>
          </div>
          <el-row :gutter="24">
            <el-col :xs="24" :sm="12">
              <el-form-item label="CPU 使用率（%）">
                <el-input-number v-model="form.thresholds.host_cpu_usage_pct" :min="1" :max="100" controls-position="right" style="width: 180px" />
                <el-tag size="small" type="info" effect="plain" class="hint-tag">按近 10 分钟均值告警</el-tag>
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12">
              <el-form-item label="内存使用率（%）">
                <el-input-number v-model="form.thresholds.host_memory_usage_pct" :min="1" :max="100" controls-position="right" style="width: 180px" />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :sm="12">
              <el-form-item label="磁盘使用率（%）">
                <el-input-number v-model="form.thresholds.host_data_disk_usage_pct" :min="1" :max="100" controls-position="right" style="width: 180px" />
              </el-form-item>
            </el-col>
          </el-row>
        </div>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { Bell, Check, Refresh, Setting, Warning } from "@element-plus/icons-vue";
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
  notify_repeat_minutes: 60,
  notify_target_ids: [],
  muted_cluster_ids: [],
  thresholds: {
    mysql_replication_lag_seconds: 60,
    mysql_connection_usage_pct: 90,
    mongodb_repl_lag_seconds: 60,
    mongodb_cache_used_pct: 90,
    redis_memory_usage_pct: 90,
    redis_connection_usage_pct: 90,
    host_cpu_usage_pct: 90,
    postgresql_replication_lag_seconds: 60,
    postgresql_connection_usage_pct: 90,
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
  form.notify_repeat_minutes = Math.max(1, Math.round(Number(data.notify_repeat_seconds || 3600) / 60));
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
      notify_repeat_seconds: Math.max(60, Number(form.notify_repeat_minutes || 60) * 60),
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
.page {
  padding: 16px 20px 24px;
}

/* ---------- 页头 ---------- */
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 14px;
  padding: 12px 16px;
  background: linear-gradient(135deg, #eef4ff 0%, #f0f9ff 100%);
  border: 1px solid #dbeafe;
  border-radius: 10px;
}
.page-title {
  font-size: 18px;
  font-weight: 600;
  color: #0f172a;
}
.page-subtitle {
  margin-top: 4px;
  font-size: 12.5px;
  color: #64748b;
}
.page-header-actions {
  display: flex;
  gap: 10px;
}

/* ---------- 分组卡片 ---------- */
.section-card {
  margin-bottom: 14px;
  border-radius: 10px;
  border: 1px solid #e5e7eb;
}
.section-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafbfc;
  border-bottom: 1px solid #eef0f3;
}
.section-card :deep(.el-card__body) {
  padding: 20px 16px 4px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.section-header .el-icon {
  font-size: 16px;
}
.section-title {
  font-size: 14.5px;
  font-weight: 600;
  color: #0f172a;
}
.section-desc {
  margin-left: 6px;
  color: #94a3b8;
  font-size: 12.5px;
}
.section-header--blue .el-icon { color: #2563eb; }
.section-header--amber .el-icon { color: #f59e0b; }
.section-header--rose .el-icon { color: #e11d48; }

/* ---------- 阈值分组 ---------- */
.threshold-group {
  padding: 6px 0 0;
  margin-bottom: 4px;
  border-top: 1px dashed #eef0f3;
}
.threshold-group:first-child {
  border-top: none;
}
.threshold-group-title {
  margin: 0 0 6px 4px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.group-badge {
  display: inline-block;
  padding: 2px 10px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 4px;
  letter-spacing: 0.3px;
}
.group-badge--mysql {
  color: #1565c0;
  background: #e3f2fd;
  border: 1px solid #bbdefb;
}
.group-badge--mongodb {
  color: #2e7d32;
  background: #e8f5e9;
  border: 1px solid #c8e6c9;
}
.group-badge--postgresql {
  color: #336791;
  background: #e8f1f8;
  border: 1px solid #b7d3e8;
}
.group-badge--redis {
  color: #c62828;
  background: #ffebee;
  border: 1px solid #ffcdd2;
}
.group-badge--host {
  color: #6d28d9;
  background: #f5f3ff;
  border: 1px solid #ddd6fe;
}

/* ---------- 提示 ---------- */
.hint-text {
  margin-left: 10px;
  color: #94a3b8;
  font-size: 12px;
}
.hint-tag {
  margin-left: 10px;
}
</style>
