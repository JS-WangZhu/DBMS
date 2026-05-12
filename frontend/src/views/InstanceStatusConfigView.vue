<template>
  <div class="page">
    <div class="page-header">
      <div>
        <div class="page-title">实例状态检测管理</div>
        <div class="page-subtitle">配置实例运行状态采集的超时与轮询频率</div>
      </div>
      <div class="page-actions">
        <el-button :icon="Refresh" @click="loadConfig">刷新</el-button>
        <el-button type="primary" :icon="Check" :loading="saving" @click="saveConfig">保存</el-button>
      </div>
    </div>

    <el-card class="section-card" shadow="never">
      <template #header>
        <div class="section-header">
          <el-icon><Timer /></el-icon>
          <span>检测参数</span>
        </div>
      </template>
      <el-form :model="form" label-width="180px" label-position="right">
        <el-row :gutter="24">
          <el-col :xs="24" :sm="12">
            <el-form-item label="刷新指标超时时间（秒）">
              <el-input-number
                v-model="form.metric_refresh_timeout_seconds"
                :min="1"
                :step="1"
                controls-position="right"
                style="width: 180px"
              />
              <span class="hint-text">单轮实例指标采集最长等待时间</span>
            </el-form-item>
          </el-col>
          <el-col :xs="24" :sm="12">
            <el-form-item label="探测轮询时间（秒）">
              <el-input-number
                v-model="form.probe_poll_interval_seconds"
                :min="10"
                :step="5"
                controls-position="right"
                style="width: 180px"
              />
              <span class="hint-text">后台探测与实例页自动刷新间隔</span>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { Check, Refresh, Timer } from "@element-plus/icons-vue";
import { getInstanceStatusConfig, updateInstanceStatusConfig } from "../api/modules/instances";

const saving = ref(false);
const form = reactive({
  metric_refresh_timeout_seconds: 8,
  probe_poll_interval_seconds: 30,
});

function applyConfig(data = {}) {
  form.metric_refresh_timeout_seconds = data.metric_refresh_timeout_seconds || 8;
  form.probe_poll_interval_seconds = data.probe_poll_interval_seconds || 30;
}

async function loadConfig() {
  try {
    const { data } = await getInstanceStatusConfig();
    applyConfig(data?.data || {});
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载实例状态检测配置失败");
  }
}

async function saveConfig() {
  saving.value = true;
  try {
    const { data } = await updateInstanceStatusConfig({
      metric_refresh_timeout_seconds: form.metric_refresh_timeout_seconds,
      probe_poll_interval_seconds: form.probe_poll_interval_seconds,
    });
    applyConfig(data?.data || {});
    ElMessage.success("保存成功");
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "保存实例状态检测配置失败");
  } finally {
    saving.value = false;
  }
}

onMounted(loadConfig);
</script>

<style scoped>
.page {
  padding: 16px 20px 24px;
}

.page-header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
  padding: 12px 16px;
  background: linear-gradient(135deg, #eef4ff 0%, #f0f9ff 100%);
  border: 1px solid #dbeafe;
  border-radius: 8px;
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

.page-actions {
  display: flex;
  gap: 10px;
}

.section-card {
  border: 1px solid #e5e7eb;
  border-radius: 8px;
}

.section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14.5px;
  font-weight: 600;
  color: #0f172a;
}

.section-header .el-icon {
  color: #2563eb;
}

.hint-text {
  margin-left: 10px;
  color: #94a3b8;
  font-size: 12px;
}
</style>
