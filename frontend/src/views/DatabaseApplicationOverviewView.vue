<template>
  <div class="page overview-page">
    <div class="page-heading">
      <div>
        <div class="eyebrow">RESOURCE DELIVERY</div>
        <h2>申请预览</h2>
        <p>确认申请信息无误后，可以在这里完成提交前确认。当前页面仅做预览和草稿确认。</p>
      </div>
      <el-steps :active="1" simple class="overview-steps">
        <el-step title="选择产品" />
        <el-step title="申请预览" />
        <el-step title="确认提交" />
      </el-steps>
    </div>

    <el-row :gutter="16" class="overview-grid">
      <el-col :xs="24" :lg="16">
        <el-card shadow="never" class="overview-card">
          <template #header>
            <div class="card-header">
              <span>申请信息</span>
              <el-tag type="info" effect="light">草稿预览</el-tag>
            </div>
          </template>

          <el-descriptions :column="2" border class="summary-descriptions">
            <el-descriptions-item label="数据库引擎">{{ draft.engineLabel || draft.engine || '-' }}</el-descriptions-item>
            <el-descriptions-item label="产品架构">{{ draft.architecture || '-' }}</el-descriptions-item>
            <el-descriptions-item label="地域">{{ draft.region || '-' }}</el-descriptions-item>
            <el-descriptions-item label="实例规格">{{ formatSpec(draft) }}</el-descriptions-item>
            <el-descriptions-item label="存储空间">{{ draft.storageGb ? `${draft.storageGb} GB` : '-' }}</el-descriptions-item>
            <el-descriptions-item label="使用环境">{{ environmentLabel(draft.environment) }}</el-descriptions-item>
            <el-descriptions-item label="申请名称" :span="2">{{ draft.name || '-' }}</el-descriptions-item>
            <el-descriptions-item label="申请说明" :span="2">{{ draft.reason || '-' }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>

      <el-col :xs="24" :lg="8">
        <el-card shadow="never" class="overview-card sticky-card">
          <template #header>
            <div class="card-header">
              <span>提交操作</span>
              <el-tag type="warning" effect="light">待提交</el-tag>
            </div>
          </template>

          <div class="action-panel">
            <p class="action-tip">这里先做提交前确认，真正的提交接口后面再接入。</p>
            <el-button type="primary" size="large" class="full-width" :loading="submitting" @click="confirmSubmit">确认提交</el-button>
            <el-button text class="full-width" @click="goBack">返回修改</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";

const router = useRouter();
const submitting = ref(false);
const draft = computed(() => {
  try {
    return JSON.parse(localStorage.getItem("database_application_draft") || "{}") || {};
  } catch {
    return {};
  }
});

function formatSpec(value) {
  const cpu = value?.cpu;
  const memory = value?.memory;
  if (!cpu || !memory) {
    return "-";
  }
  return `${cpu}C ${memory}G`;
}

function environmentLabel(value) {
  return {
    production: "生产环境",
    staging: "预发环境",
    testing: "测试环境",
  }[value] || value || "-";
}

async function confirmSubmit() {
  submitting.value = true;
  try {
    localStorage.setItem("database_application_preview_confirmed", JSON.stringify({ confirmedAt: new Date().toISOString(), draft: draft.value }));
    ElMessage.success("已确认提交，正式提交接口待接入");
  } finally {
    submitting.value = false;
  }
}

function goBack() {
  router.push("/resources/database-apply");
}
</script>

<style scoped>
.overview-page { padding-bottom: 24px; }
.page-heading { display: flex; align-items: center; justify-content: space-between; gap: 32px; margin-bottom: 16px; padding: 8px 4px 0; }
.page-heading h2 { margin: 3px 0 6px; font-size: 24px; color: #172033; }
.page-heading p { margin: 0; color: #7b879a; font-size: 13px; }
.eyebrow { color: #1677ff; font-size: 11px; font-weight: 700; letter-spacing: 1.5px; }
.overview-steps { width: 470px; background: transparent; }
.overview-grid { align-items: stretch; }
.overview-card { border: 1px solid #e5eaf2; box-shadow: 0 8px 28px rgba(27,45,78,.06); margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.summary-descriptions :deep(.el-descriptions__label) { width: 110px; }
.sticky-card { position: sticky; top: 20px; }
.action-panel { display: flex; flex-direction: column; gap: 12px; }
.action-tip { margin: 0; color: #7b879a; line-height: 1.7; }
.full-width { width: 100%; }
@media (max-width: 1100px) {
  .page-heading { align-items: flex-start; flex-direction: column; }
  .overview-steps { width: 100%; }
  .sticky-card { position: static; }
}
</style>