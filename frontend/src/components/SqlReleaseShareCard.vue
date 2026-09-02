<template>
  <section class="release-share-card" aria-label="工单分享卡片">
    <div class="share-card-accent"></div>
    <header>
      <div>
        <span class="share-card-kicker">DBMS · SQL 上线工单</span>
        <h3>{{ release?.title || "未命名工单" }}</h3>
      </div>
      <span class="share-card-id">#{{ release?.id || "-" }}</span>
    </header>
    <div class="share-card-grid">
      <div><span>申请人</span><strong>{{ release?.applicant_name || "-" }}</strong></div>
      <div><span>状态</span><strong>{{ statusLabel(release?.status) }}</strong></div>
      <div><span>数据源</span><strong>{{ release?.cluster_name || "-" }}</strong></div>
      <div><span>环境 / 数据库</span><strong>{{ release?.environment || "-" }} / {{ release?.database || "-" }}</strong></div>
      <div><span>数据库类型</span><strong>{{ dbTypeLabel(release?.db_type) }}</strong></div>
      <div><span>提交时间</span><strong>{{ formatBeijingTime(release?.created_at) }}</strong></div>
    </div>
    <div class="share-card-link" :title="shareLink">{{ shareLink }}</div>
    <footer>
      <el-button @click="copyReleaseInfo">复制工单信息</el-button>
      <el-button type="primary" @click="copyShareLink">复制工单链接</el-button>
    </footer>
  </section>
</template>

<script setup>
import { computed } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { formatBeijingTime } from "../utils/time";

const props = defineProps({ release: { type: Object, required: true } });
const router = useRouter();

const statusLabel = (value) => ({
  reviewing: "初审中", review_rejected: "初审未通过", review_failed: "初审失败",
  pending: "待执行", executing: "执行中", success: "成功", failed: "部分失败",
  rolling_back: "回滚中", rolled_back: "已回滚", partial_rolled_back: "部分回滚", rollback_failed: "回滚失败",
}[value] || value || "-");
const dbTypeLabel = (value) => ({ mysql: "MySQL", mongodb: "MongoDB", postgresql: "PostgreSQL" }[value] || value || "-");

const shareLink = computed(() => {
  const href = router.resolve({ path: "/data-release/history", query: { release_id: String(props.release?.id || "") } }).href;
  return new URL(href, window.location.origin).toString();
});

const releaseInfo = computed(() => [
  `【DBMS SQL 上线工单 #${props.release?.id || "-"}】${props.release?.title || "未命名工单"}`,
  `申请人：${props.release?.applicant_name || "-"}`,
  `状态：${statusLabel(props.release?.status)}`,
  `数据源：${props.release?.cluster_name || "-"}`,
  `环境 / 数据库：${props.release?.environment || "-"} / ${props.release?.database || "-"}`,
  `数据库类型：${dbTypeLabel(props.release?.db_type)}`,
  `提交时间：${formatBeijingTime(props.release?.created_at)}`,
  `工单链接：${shareLink.value}`,
].join("\n"));

async function copyText(value, successMessage) {
  try {
    if (navigator.clipboard?.writeText && window.isSecureContext) {
      await navigator.clipboard.writeText(value);
    } else {
      const textarea = document.createElement("textarea");
      textarea.value = value;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      const copied = document.execCommand("copy");
      textarea.remove();
      if (!copied) throw new Error("copy failed");
    }
    ElMessage.success(successMessage);
  } catch {
    ElMessage.error("复制失败，请手动复制");
  }
}

function copyReleaseInfo() { return copyText(releaseInfo.value, "工单信息及链接已复制"); }
function copyShareLink() { return copyText(shareLink.value, "工单链接已复制"); }
</script>

<style scoped>
.release-share-card { position: relative; overflow: hidden; border: 1px solid #dbe7f5; border-radius: 12px; padding: 20px; background: linear-gradient(145deg, #f8fbff 0%, #fff 62%); box-shadow: 0 8px 24px rgba(31, 73, 125, .08); }
.share-card-accent { position: absolute; top: 0; right: 0; left: 0; height: 4px; background: linear-gradient(90deg, #1677ff, #69b1ff); }
.release-share-card header { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }
.share-card-kicker { color: #1677ff; font-size: 12px; font-weight: 700; letter-spacing: .08em; }
.release-share-card h3 { margin: 6px 0 0; color: #1f2d3d; font-size: 18px; line-height: 1.4; word-break: break-word; }
.share-card-id { flex: none; border-radius: 999px; padding: 5px 10px; color: #1677ff; background: #eaf3ff; font-weight: 700; }
.share-card-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px 24px; margin-top: 18px; }
.share-card-grid div { min-width: 0; }
.share-card-grid span { display: block; margin-bottom: 4px; color: #8a95a7; font-size: 12px; }
.share-card-grid strong { display: block; overflow: hidden; color: #344054; font-size: 14px; text-overflow: ellipsis; white-space: nowrap; }
.share-card-link { margin-top: 18px; overflow: hidden; border-radius: 6px; padding: 9px 11px; color: #637083; background: #eef4fb; font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; text-overflow: ellipsis; white-space: nowrap; }
.release-share-card footer { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }
@media (max-width: 620px) { .share-card-grid { grid-template-columns: 1fr; } }
</style>
