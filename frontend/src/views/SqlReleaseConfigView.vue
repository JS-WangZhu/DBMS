<template>
  <div class="page">
    <div class="page-header">
      <div>
        <h1>数据发布配置</h1>
        <p>配置 SQL 上线工单的全局审核策略</p>
      </div>
      <el-button :loading="loading" @click="loadConfig">刷新</el-button>
    </div>

    <el-alert
      title="关闭 AI 预审后，新提交或尚未开始调用模型的工单将不执行 AI 审核并直接进入待执行。"
      type="warning"
      show-icon
      :closable="false"
      class="config-alert"
    />

    <el-card shadow="never" v-loading="loading">
      <div class="config-row">
        <div>
          <strong>全局 AI 预审</strong>
          <p>开启时，新工单提交后必须完成逐条 AI 预审；模型异常时，申请人可在异常弹窗中确认跳过。</p>
        </div>
        <el-switch
          v-model="config.ai_review_enabled"
          :loading="saving"
          inline-prompt
          active-text="开启"
          inactive-text="关闭"
          style="--el-switch-on-color: #13ce66; --el-switch-off-color: #909399"
          @change="saveConfig"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { getSqlReleaseConfig, updateSqlReleaseConfig } from "../api/modules/sql_release_config";
import { useTabActivationRefresh } from "../composables/useTabActivationRefresh";

const loading = ref(false);
const saving = ref(false);
const config = reactive({ ai_review_enabled: true });

async function loadConfig() {
  loading.value = true;
  try {
    const { data } = await getSqlReleaseConfig();
    config.ai_review_enabled = data.data?.ai_review_enabled !== false;
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载数据发布配置失败");
  } finally {
    loading.value = false;
  }
}

async function saveConfig(value) {
  if (!value) {
    try {
      await ElMessageBox.confirm(
        "关闭后，新工单将跳过 AI 预审并直接进入待执行。确认关闭全局 AI 预审？",
        "关闭 AI 预审确认",
        { type: "warning", confirmButtonText: "确认关闭" },
      );
    } catch {
      config.ai_review_enabled = true;
      return;
    }
  }
  saving.value = true;
  try {
    const { data } = await updateSqlReleaseConfig({ ai_review_enabled: !!value });
    config.ai_review_enabled = data.data?.ai_review_enabled !== false;
    ElMessage.success(data.message || "数据发布配置已更新");
  } catch (error) {
    config.ai_review_enabled = !value;
    ElMessage.error(error.response?.data?.message || "保存数据发布配置失败");
  } finally {
    saving.value = false;
  }
}

onMounted(loadConfig);
useTabActivationRefresh(loadConfig);
</script>

<style scoped>
.page { padding: 18px 22px 28px; }
.page-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 14px; }
.page-header h1 { margin: 0; color: #172033; font-size: 22px; }
.page-header p, .config-row p { margin: 6px 0 0; color: #7b879a; font-size: 13px; }
.config-alert { margin-bottom: 14px; }
.config-row { display: flex; align-items: center; justify-content: space-between; gap: 32px; min-height: 92px; padding: 8px 6px; }
.config-row strong { color: #25324b; font-size: 16px; }
.config-row :deep(.el-switch) { flex: none; }
</style>
