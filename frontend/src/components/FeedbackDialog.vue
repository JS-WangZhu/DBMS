<template>
  <el-dialog
    v-model="visible"
    class="feedback-dialog"
    title="意见反馈"
    width="min(960px, 94vw)"
    top="6vh"
    destroy-on-close
    @open="onOpen"
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
          <div class="detail-heading">
            <div>
              <h3>提交新反馈</h3>
              <p>请尽量描述问题现象、期望结果和复现方式。</p>
            </div>
          </div>
          <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-position="top">
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
            <div class="form-actions">
              <el-button @click="cancelCreate">取消</el-button>
              <el-button type="primary" :loading="submitting" @click="submitFeedback">提交反馈</el-button>
            </div>
          </el-form>
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
import { computed, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { Plus } from "@element-plus/icons-vue";
import {
  createFeedback,
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
const createForm = reactive({ subject: "", content: "" });
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
}

function cancelCreate() {
  creating.value = false;
  if (items.value.length) selectFeedback(items.value[0]);
}

async function submitFeedback() {
  if (!(await createFormRef.value?.validate().catch(() => false))) return;
  submitting.value = true;
  try {
    const { data } = await createFeedback({ ...createForm });
    ElMessage.success(data.message || "反馈已提交");
    creating.value = false;
    page.value = 1;
    selected.value = null;
    await loadFeedback();
    emit("summary-change");
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "提交反馈失败");
  } finally {
    submitting.value = false;
  }
}

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

.feedback-detail-pane { display: flex; min-width: 0; flex-direction: column; padding: 20px 22px; background: #fff; }
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
.reply-box { padding-top: 14px; border-top: 1px solid #ebeef5; }
.reply-actions { margin-top: 10px; justify-content: flex-end; }
.reply-actions span { color: #a1a5ad; font-size: 11px; }
.form-actions { justify-content: flex-end; }

@media (max-width: 720px) {
  .feedback-shell { grid-template-columns: 1fr; height: 78vh; overflow-y: auto; }
  .feedback-list-pane { min-height: 260px; border-right: 0; border-bottom: 1px solid #e4e7ed; }
  .feedback-detail-pane { min-height: 420px; }
}
</style>
