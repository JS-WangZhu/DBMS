<template>
  <el-dialog
    v-model="visible"
    class="feedback-dialog"
    title="意见反馈"
    width="min(960px, 94vw)"
    top="6vh"
    destroy-on-close
    @open="onOpen"
    @closed="onClosed"
  >
    <div class="feedback-shell" v-loading="loading">
      <aside class="feedback-list-pane">
        <div class="feedback-toolbar">
          <div>
            <strong>{{ isAdmin ? "用户反馈" : "我的反馈" }}</strong>
            <span>共 {{ total }} 条</span>
          </div>
          <el-button v-if="!isAdmin" type="primary" size="small" @click="showCreateForm">
            <el-icon><Plus /></el-icon>
            提交反馈
          </el-button>
        </div>

        <el-segmented v-if="isAdmin" v-model="statusFilter" :options="statusOptions" size="small" @change="changeStatusFilter" />

        <el-scrollbar class="feedback-scrollbar">
          <button
            v-for="item in items"
            :key="item.id"
            type="button"
            class="feedback-list-item"
            :class="{ active: selected?.id === item.id, unread: itemUnread(item) }"
            @click="selectFeedback(item)"
          >
            <span class="feedback-item-heading">
              <span class="feedback-subject">{{ item.subject }}</span>
              <i v-if="itemUnread(item)" aria-label="未读"></i>
            </span>
            <span v-if="isAdmin" class="feedback-user">{{ item.username }}</span>
            <span class="feedback-item-meta">
              <el-tag :type="item.status === 'replied' ? 'success' : 'warning'" size="small" effect="plain">
                {{ item.status === "replied" ? "已回复" : "待回复" }}
              </el-tag>
              <time>{{ formatBeijingTime(item.updated_at) }}</time>
            </span>
          </button>
          <el-empty v-if="!items.length && !loading" :description="isAdmin ? '暂无用户反馈' : '暂无反馈记录'" :image-size="72" />
        </el-scrollbar>

        <el-pagination
          v-if="total > pageSize"
          v-model:current-page="page"
          small
          layout="prev, pager, next"
          :page-size="pageSize"
          :total="total"
          @current-change="loadFeedback"
        />
      </aside>

      <main class="feedback-detail-pane">
        <template v-if="creating">
          <div class="create-feedback-form" @paste="handleImagePaste">
          <div class="detail-heading">
            <div>
              <h3>提交新反馈</h3>
              <p>请尽量描述问题现象、期望结果和复现方式。</p>
            </div>
          </div>
          <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-position="top">
            <div class="create-form-fields">
              <el-form-item label="反馈主题" prop="subject">
                <el-input v-model="createForm.subject" maxlength="120" show-word-limit placeholder="请简要概括反馈内容" />
              </el-form-item>
              <el-form-item label="反馈内容" prop="content">
                <el-input
                  v-model="createForm.content"
                  type="textarea"
                  :rows="9"
                  maxlength="4000"
                  show-word-limit
                  resize="none"
                  placeholder="请输入详细反馈内容"
                />
              </el-form-item>
              <el-form-item label="问题截图">
                <div class="image-uploader">
                  <input
                    ref="imageInputRef"
                    class="image-file-input"
                    type="file"
                    accept="image/png,image/jpeg,image/gif,image/webp"
                    multiple
                    @change="handleImageSelect"
                  />
                  <div class="image-upload-actions">
                    <el-button :icon="Picture" @click="imageInputRef?.click()">上传图片</el-button>
                    <span>支持选择或 Ctrl + V 粘贴，最多 5 张，单张不超过 5MB</span>
                  </div>
                  <div v-if="pendingImages.length" class="pending-image-grid">
                    <div v-for="(image, index) in pendingImages" :key="image.id" class="pending-image-item">
                      <el-image :src="image.previewUrl" fit="cover" :preview-src-list="pendingPreviewUrls" :initial-index="index" />
                      <button type="button" aria-label="移除图片" @click="removePendingImage(index)">
                        <el-icon><Close /></el-icon>
                      </button>
                      <span :title="image.file.name">{{ image.file.name }}</span>
                    </div>
                  </div>
                </div>
              </el-form-item>
            </div>
            <div class="form-actions">
              <el-button @click="cancelCreate">取消</el-button>
              <el-button type="primary" :loading="submitting" @click="submitFeedback">提交反馈</el-button>
            </div>
          </el-form>
          </div>
        </template>

        <template v-else-if="selected">
          <div class="detail-heading">
            <div>
              <h3>{{ selected.subject }}</h3>
              <p>
                <span v-if="isAdmin">{{ selected.username }} · </span>
                {{ formatBeijingTime(selected.created_at) }}
              </p>
            </div>
            <el-tag :type="selected.status === 'replied' ? 'success' : 'warning'">
              {{ selected.status === "replied" ? "已回复" : "待回复" }}
            </el-tag>
          </div>

          <el-scrollbar class="conversation-scrollbar">
            <section class="message-card user-message">
              <header>
                <strong>{{ selected.username }}</strong>
                <time>{{ formatBeijingTime(selected.created_at) }}</time>
              </header>
              <p>{{ selected.content }}</p>
              <div v-if="selected.attachments?.length" class="message-image-grid">
                <el-image
                  v-for="(attachment, index) in selected.attachments"
                  :key="attachment.id"
                  :src="attachmentUrls[attachment.id]"
                  :alt="attachment.original_name"
                  fit="cover"
                  :preview-src-list="selectedPreviewUrls"
                  :initial-index="index"
                >
                  <template #error><div class="image-load-error">加载失败</div></template>
                </el-image>
              </div>
            </section>
            <section v-for="reply in selected.replies" :key="reply.id" class="message-card admin-message">
              <header>
                <strong>管理员 · {{ reply.admin_name }}</strong>
                <time>{{ formatBeijingTime(reply.created_at) }}</time>
              </header>
              <p>{{ reply.content }}</p>
            </section>
            <el-empty v-if="!selected.replies?.length" description="管理员暂未回复" :image-size="64" />
          </el-scrollbar>

          <div v-if="isAdmin" class="reply-box">
            <el-input
              v-model="replyContent"
              type="textarea"
              :rows="3"
              maxlength="4000"
              show-word-limit
              resize="none"
              placeholder="输入回复内容，用户将在此处看到回复"
              @keydown.ctrl.enter="submitReply"
            />
            <div class="reply-actions">
              <span>Ctrl + Enter 快速发送</span>
              <el-button type="primary" :loading="replying" @click="submitReply">发送回复</el-button>
            </div>
          </div>
        </template>

        <el-empty v-else description="请选择一条反馈查看详情" />
      </main>
    </div>
  </el-dialog>
</template>

<script setup>
import { computed, onBeforeUnmount, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { Close, Picture, Plus } from "@element-plus/icons-vue";
import {
  createFeedback,
  getFeedbackAttachment,
  listFeedback,
  markFeedbackRead,
  replyFeedback,
} from "../api/modules/feedback";
import { formatBeijingTime } from "../utils/time";

const props = defineProps({
  role: { type: String, default: "user" },
});
const emit = defineEmits(["summary-change"]);
const visible = defineModel({ type: Boolean, default: false });

const isAdmin = computed(() => props.role === "admin");
const loading = ref(false);
const submitting = ref(false);
const replying = ref(false);
const creating = ref(false);
const items = ref([]);
const selected = ref(null);
const total = ref(0);
const page = ref(1);
const pageSize = 20;
const statusFilter = ref("all");
const replyContent = ref("");
const createFormRef = ref(null);
const imageInputRef = ref(null);
const createForm = reactive({ subject: "", content: "" });
const pendingImages = ref([]);
const attachmentUrls = reactive({});
let pendingImageSequence = 0;
const maxImageCount = 5;
const maxImageBytes = 5 * 1024 * 1024;
const allowedImageTypes = new Set(["image/png", "image/jpeg", "image/gif", "image/webp"]);
const pendingPreviewUrls = computed(() => pendingImages.value.map((image) => image.previewUrl));
const selectedPreviewUrls = computed(() =>
  (selected.value?.attachments || []).map((attachment) => attachmentUrls[attachment.id]).filter(Boolean),
);
const createRules = {
  subject: [{ required: true, message: "请输入反馈主题", trigger: "blur" }],
  content: [{ required: true, message: "请输入反馈内容", trigger: "blur" }],
};
const statusOptions = [
  { label: "全部", value: "all" },
  { label: "待回复", value: "pending" },
  { label: "已回复", value: "replied" },
];

function itemUnread(item) {
  return isAdmin.value ? item.admin_unread : item.user_unread;
}

async function onOpen() {
  page.value = 1;
  await loadFeedback();
}

async function loadFeedback() {
  loading.value = true;
  try {
    const params = { page: page.value, page_size: pageSize };
    if (statusFilter.value !== "all") params.status = statusFilter.value;
    const { data } = await listFeedback(params);
    items.value = data.data?.items || [];
    total.value = data.data?.total || 0;
    if (selected.value) {
      selected.value = items.value.find((item) => item.id === selected.value.id) || null;
    }
    if (!selected.value && items.value.length && !creating.value) {
      await selectFeedback(items.value[0]);
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载反馈失败");
  } finally {
    loading.value = false;
  }
}

function changeStatusFilter() {
  page.value = 1;
  selected.value = null;
  loadFeedback();
}

async function selectFeedback(item) {
  creating.value = false;
  selected.value = item;
  replyContent.value = "";
  await loadSelectedImages(item);
  if (!itemUnread(item)) return;
  try {
    const { data } = await markFeedbackRead(item.id);
    const refreshed = data.data;
    const index = items.value.findIndex((row) => row.id === item.id);
    if (index >= 0) items.value[index] = refreshed;
    selected.value = refreshed;
    emit("summary-change");
  } catch {
    // Reading the feedback itself should still work when read-state refresh fails.
  }
}

function showCreateForm() {
  selected.value = null;
  creating.value = true;
  createForm.subject = "";
  createForm.content = "";
  clearPendingImages();
}

function cancelCreate() {
  creating.value = false;
  clearPendingImages();
  if (items.value.length) selectFeedback(items.value[0]);
}

async function submitFeedback() {
  if (!(await createFormRef.value?.validate().catch(() => false))) return;
  submitting.value = true;
  try {
    const { data } = await createFeedback(
      { ...createForm },
      pendingImages.value.map((image) => image.file),
    );
    ElMessage.success(data.message || "反馈已提交");
    creating.value = false;
    page.value = 1;
    selected.value = null;
    clearPendingImages();
    await loadFeedback();
    emit("summary-change");
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "提交反馈失败");
  } finally {
    submitting.value = false;
  }
}

function appendImages(files) {
  for (const file of files) {
    if (pendingImages.value.length >= maxImageCount) {
      ElMessage.warning(`最多上传 ${maxImageCount} 张图片`);
      break;
    }
    if (!allowedImageTypes.has(file.type)) {
      ElMessage.warning(`${file.name || "粘贴的文件"} 不是支持的图片格式`);
      continue;
    }
    if (file.size > maxImageBytes) {
      ElMessage.warning(`${file.name || "图片"} 超过 5MB`);
      continue;
    }
    pendingImages.value.push({
      id: ++pendingImageSequence,
      file,
      previewUrl: URL.createObjectURL(file),
    });
  }
}

function handleImageSelect(event) {
  appendImages(Array.from(event.target.files || []));
  event.target.value = "";
}

function handleImagePaste(event) {
  const files = Array.from(event.clipboardData?.items || [])
    .filter((item) => item.kind === "file" && item.type.startsWith("image/"))
    .map((item) => item.getAsFile())
    .filter(Boolean);
  if (!files.length) return;
  event.preventDefault();
  const namedFiles = files.map((file, index) => {
    if (file.name && file.name !== "image.png") return file;
    const extension = file.type === "image/jpeg" ? "jpg" : (file.type.split("/")[1] || "png");
    return new File([file], `粘贴图片-${Date.now()}-${index + 1}.${extension}`, { type: file.type });
  });
  appendImages(namedFiles);
  ElMessage.success(`已粘贴 ${namedFiles.length} 张图片`);
}

function removePendingImage(index) {
  const [removed] = pendingImages.value.splice(index, 1);
  if (removed) URL.revokeObjectURL(removed.previewUrl);
}

function clearPendingImages() {
  pendingImages.value.forEach((image) => URL.revokeObjectURL(image.previewUrl));
  pendingImages.value = [];
  if (imageInputRef.value) imageInputRef.value.value = "";
}

async function loadSelectedImages(item) {
  const attachments = item?.attachments || [];
  await Promise.all(
    attachments.map(async (attachment) => {
      if (attachmentUrls[attachment.id]) return;
      try {
        const { data } = await getFeedbackAttachment(item.id, attachment.id);
        attachmentUrls[attachment.id] = URL.createObjectURL(data);
      } catch {
        attachmentUrls[attachment.id] = "";
      }
    }),
  );
}

function clearAttachmentUrls() {
  Object.keys(attachmentUrls).forEach((id) => {
    if (attachmentUrls[id]) URL.revokeObjectURL(attachmentUrls[id]);
    delete attachmentUrls[id];
  });
}

function onClosed() {
  clearPendingImages();
  clearAttachmentUrls();
  // Blob URLs are revoked above. Drop the selection as well so reopening the
  // dialog selects the first row again and downloads fresh attachment blobs.
  selected.value = null;
}

onBeforeUnmount(() => {
  clearPendingImages();
  clearAttachmentUrls();
});

async function submitReply() {
  const content = replyContent.value.trim();
  if (!selected.value || !content || replying.value) {
    if (!content) ElMessage.warning("请输入回复内容");
    return;
  }
  replying.value = true;
  try {
    const { data } = await replyFeedback(selected.value.id, { content });
    const refreshed = data.data;
    const index = items.value.findIndex((item) => item.id === refreshed.id);
    if (index >= 0) items.value[index] = refreshed;
    selected.value = refreshed;
    replyContent.value = "";
    ElMessage.success(data.message || "回复已发送");
    emit("summary-change");
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "发送回复失败");
  } finally {
    replying.value = false;
  }
}
</script>

<style scoped>
.feedback-shell {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  height: min(680px, 76vh);
  margin: -10px -4px -14px;
  overflow: hidden;
  border: 1px solid #e4e7ed;
  border-radius: 10px;
}

.feedback-list-pane {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 12px;
  padding: 16px 12px 12px;
  border-right: 1px solid #e4e7ed;
  background: #f8fafc;
}

.feedback-toolbar,
.feedback-item-heading,
.feedback-item-meta,
.detail-heading,
.message-card header,
.reply-actions,
.form-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.feedback-toolbar > div { display: flex; flex-direction: column; gap: 2px; }
.feedback-toolbar strong { color: #1f2937; font-size: 15px; }
.feedback-toolbar span { color: #909399; font-size: 12px; }
.feedback-scrollbar { min-height: 0; flex: 1; }

.feedback-list-item {
  width: 100%;
  margin-bottom: 8px;
  padding: 12px;
  text-align: left;
  border: 1px solid transparent;
  border-radius: 8px;
  background: #fff;
  cursor: pointer;
  transition: border-color 0.16s ease, box-shadow 0.16s ease;
}

.feedback-list-item:hover { border-color: #b6d2ff; }
.feedback-list-item.active { border-color: #409eff; box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.08); }
.feedback-subject { min-width: 0; overflow: hidden; color: #303133; font-size: 14px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.feedback-item-heading i { width: 7px; height: 7px; flex: 0 0 auto; border-radius: 50%; background: #f56c6c; }
.feedback-user { display: block; margin-top: 6px; overflow: hidden; color: #606266; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.feedback-item-meta { margin-top: 9px; }
.feedback-item-meta time { color: #a1a5ad; font-size: 11px; }

.feedback-detail-pane { display: flex; min-width: 0; min-height: 0; flex-direction: column; overflow: hidden; padding: 20px 22px; background: #fff; }
.create-feedback-form { display: grid; min-height: 0; flex: 1; grid-template-rows: auto minmax(0, 1fr); overflow: hidden; }
.create-feedback-form :deep(.el-form) { display: grid; min-height: 0; grid-template-rows: minmax(0, 1fr) auto; overflow: hidden; }
.create-form-fields { min-height: 0; flex: 1; overflow-y: auto; padding: 16px 6px 0 0; }
.detail-heading { align-items: flex-start; padding-bottom: 14px; border-bottom: 1px solid #ebeef5; }
.detail-heading h3 { margin: 0; color: #1f2937; font-size: 18px; }
.detail-heading p { margin: 6px 0 0; color: #909399; font-size: 12px; }
.conversation-scrollbar { min-height: 0; flex: 1; padding: 16px 8px 8px 0; }
.message-card { margin-bottom: 14px; padding: 14px 16px; border-radius: 9px; }
.user-message { background: #f4f7fb; }
.admin-message { margin-left: 28px; border: 1px solid #cfe3ff; background: #eef6ff; }
.message-card header strong { color: #303133; font-size: 13px; }
.message-card time { color: #909399; font-size: 11px; }
.message-card p { margin: 10px 0 0; color: #3f4754; line-height: 1.75; white-space: pre-wrap; overflow-wrap: anywhere; }
.image-uploader { width: 100%; }
.image-file-input { display: none; }
.image-upload-actions { display: flex; align-items: center; gap: 12px; }
.image-upload-actions span { color: #909399; font-size: 12px; }
.pending-image-grid,
.message-image-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(104px, 1fr)); gap: 10px; margin-top: 12px; }
.pending-image-item { position: relative; min-width: 0; }
.pending-image-item :deep(.el-image),
.message-image-grid :deep(.el-image) { width: 100%; height: 92px; overflow: hidden; border: 1px solid #dcdfe6; border-radius: 7px; background: #f5f7fa; }
.pending-image-item button { position: absolute; top: -7px; right: -7px; display: grid; width: 22px; height: 22px; padding: 0; color: #fff; border: 2px solid #fff; border-radius: 50%; background: #606266; cursor: pointer; place-items: center; }
.pending-image-item > span { display: block; margin-top: 3px; overflow: hidden; color: #606266; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.message-image-grid { grid-template-columns: repeat(auto-fill, minmax(120px, 160px)); }
.message-image-grid :deep(.el-image) { height: 112px; cursor: zoom-in; }
.image-load-error { display: grid; width: 100%; height: 100%; color: #a8abb2; font-size: 12px; place-items: center; }
.reply-box { padding-top: 14px; border-top: 1px solid #ebeef5; }
.reply-actions { margin-top: 10px; justify-content: flex-end; }
.reply-actions span { color: #a1a5ad; font-size: 11px; }
.form-actions { min-height: 48px; flex: 0 0 auto; justify-content: flex-end; padding: 14px 0 2px; border-top: 1px solid #ebeef5; background: #fff; }

@media (max-width: 720px) {
  .feedback-shell { grid-template-columns: 1fr; height: 78vh; overflow-y: auto; }
  .feedback-list-pane { min-height: 260px; border-right: 0; border-bottom: 1px solid #e4e7ed; }
  .feedback-detail-pane { min-height: 420px; }
  .image-upload-actions { align-items: flex-start; flex-direction: column; gap: 6px; }
}
</style>
