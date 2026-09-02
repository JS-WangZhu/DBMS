<template>
  <Teleport to="body">
    <Transition name="quick-jump-fade">
      <div v-if="open" class="quick-jump-overlay" @mousedown.self="close">
        <section class="quick-jump-panel" role="dialog" aria-modal="true" aria-label="快速跳转">
          <div class="quick-jump-search">
            <el-icon><Search /></el-icon>
            <input ref="inputRef" v-model="query" class="quick-jump-input" autocomplete="off"
              placeholder="输入菜单关键字、拼音或首字母" aria-label="搜索菜单"
              @keydown.down.prevent="moveSelection(1)" @keydown.up.prevent="moveSelection(-1)"
              @keydown.enter.prevent="selectActive" @keydown.esc.prevent="close" />
            <kbd>ESC</kbd>
          </div>
          <div v-if="results.length" class="quick-jump-results" role="listbox">
            <button v-for="(item, index) in results" :key="item.path" :ref="(element) => setItemRef(element, index)"
              type="button" class="quick-jump-item" :class="{ 'is-active': index === activeIndex }" role="option"
              :aria-selected="index === activeIndex" @mouseenter="activeIndex = index" @click="selectItem(item)">
              <span class="quick-jump-item-icon"><el-icon><component :is="menuIcon(item)" /></el-icon></span>
              <span class="quick-jump-item-copy"><strong>{{ item.label }}</strong><small>{{ item.group }}</small></span>
              <el-icon class="quick-jump-enter"><Right /></el-icon>
            </button>
          </div>
          <div v-else class="quick-jump-empty">没有找到匹配的菜单</div>
          <footer class="quick-jump-footer">
            <span><kbd>↑</kbd><kbd>↓</kbd> 选择</span><span><kbd>Enter</kbd> 跳转</span>
            <span class="quick-jump-trigger">双击 <kbd>Shift</kbd> 唤起</span>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import {
  Avatar, Bell, Box, CircleCheck, CirclePlus, Clock, Coin, Connection, DataAnalysis,
  Delete, Document, EditPen, Files, FolderOpened, Histogram, Key, Lightning, Link,
  Location, Lock, Monitor, Notebook, Odometer, Operation, Position, Promotion, Right,
  Search, SetUp, Setting, Share, Tickets, Timer, Tools, TrendCharts, UserFilled, View,
} from "@element-plus/icons-vue";
import DorisIcon from "./icons/DorisIcon.vue";
import MongoIcon from "./icons/MongoIcon.vue";
import MysqlIcon from "./icons/MysqlIcon.vue";
import PostgreSQLIcon from "./icons/PostgreSQLIcon.vue";
import RedisIcon from "./icons/RedisIcon.vue";
import { filterQuickJumpMenus } from "../utils/quickJump";

const props = defineProps({ items: { type: Array, default: () => [] } });
const emit = defineEmits(["select"]);
const open = ref(false);
const query = ref("");
const activeIndex = ref(0);
const inputRef = ref(null);
const itemRefs = [];
let lastShiftAt = 0;
let shiftResetTimer = null;
const results = computed(() => filterQuickJumpMenus(props.items, query.value));

const iconMap = {
  dashboard: Odometer,
  database_apply: CirclePlus, database_recycle: Delete, application_history: Document,
  mysql_instances: MysqlIcon, mysql_instance_detail: TrendCharts, mysql_clusters: Share,
  mysql_connections: Connection, mysql_session_probe: View,
  mongodb_instances: MongoIcon, mongodb_instance_detail: TrendCharts, mongodb_clusters: FolderOpened, mongodb_connections: Link,
  mongodb_session_probe: View,
  redis_instances: RedisIcon, redis_instance_detail: TrendCharts, redis_clusters: Coin, redis_connections: Promotion,
  postgresql_instances: PostgreSQLIcon, postgresql_clusters: Coin,
  doris_instances: DorisIcon, doris_clusters: Histogram,
  diagnosis_parameter_check: SetUp, diagnosis_slow_query: TrendCharts,
  inspection_manage: CircleCheck, inspection_param_config: Setting,
  data_query: Search, data_change: EditPen, data_history: Clock,
  task_schedule: Operation, task_results: Tickets, aliyun_dns_tool: Position,
  backup_overview: Notebook, backup_mysql_policies: MysqlIcon,
  backup_postgresql_policies: PostgreSQLIcon, backup_mongo_policies: MongoIcon,
  backup_records: Files, backup_tool_configs: Tools, backup_s3_storage: Box, backup_keys: Key,
  users_info: UserFilled, users_role_groups: Avatar, users_permissions: Lock,
  backup_agents: Monitor, ai_model_config: TrendCharts, ha_config: Lightning,
  instance_status_config: Timer, physical_discovery_manage: Monitor,
  data_query_op_config: DataAnalysis, backup_notify_targets: Bell, domain_config: Location,
  mcp_platform: SetUp, sso_config: Key, jumpserver_config: Monitor,
};

watch(results, () => {
  activeIndex.value = 0;
  nextTick(scrollActiveIntoView);
});
watch(activeIndex, () => nextTick(scrollActiveIntoView));

function menuIcon(item) { return iconMap[item?.permission] || Position; }
function setItemRef(element, index) { itemRefs[index] = element; }
function scrollActiveIntoView() { itemRefs[activeIndex.value]?.scrollIntoView({ block: "nearest" }); }
function show() {
  open.value = true;
  query.value = "";
  activeIndex.value = 0;
  nextTick(() => inputRef.value?.focus());
}
function close() { open.value = false; query.value = ""; }
function moveSelection(offset) {
  if (results.value.length) activeIndex.value = (activeIndex.value + offset + results.value.length) % results.value.length;
}
function selectItem(item) {
  if (!item) return;
  close();
  emit("select", item);
}
function selectActive(event) {
  if (!event?.isComposing) selectItem(results.value[activeIndex.value]);
}
function onGlobalKeydown(event) {
  if (event.key !== "Shift" || event.repeat || event.ctrlKey || event.altKey || event.metaKey) return;
  const now = Date.now();
  if (now - lastShiftAt <= 420) {
    lastShiftAt = 0;
    if (shiftResetTimer) window.clearTimeout(shiftResetTimer);
    show();
    return;
  }
  lastShiftAt = now;
  if (shiftResetTimer) window.clearTimeout(shiftResetTimer);
  shiftResetTimer = window.setTimeout(() => { lastShiftAt = 0; shiftResetTimer = null; }, 430);
}

onMounted(() => window.addEventListener("keydown", onGlobalKeydown, true));
onUnmounted(() => {
  window.removeEventListener("keydown", onGlobalKeydown, true);
  if (shiftResetTimer) window.clearTimeout(shiftResetTimer);
});
</script>

<style scoped>
.quick-jump-overlay { position:fixed; inset:0; z-index:4000; display:flex; align-items:flex-start; justify-content:center; padding:min(16vh,150px) 20px 20px; background:rgba(15,23,42,.36); backdrop-filter:blur(3px); }
.quick-jump-panel { width:min(620px,calc(100vw - 32px)); overflow:hidden; border:1px solid rgba(148,163,184,.3); border-radius:16px; background:#fff; box-shadow:0 24px 64px rgba(15,23,42,.22); }
.quick-jump-search { display:flex; align-items:center; gap:12px; min-height:64px; padding:0 18px; border-bottom:1px solid #e5e7eb; color:var(--el-color-primary,#409eff); font-size:22px; }
.quick-jump-input { flex:1; min-width:0; border:0; outline:0; background:transparent; color:#111827; font:inherit; font-size:17px; }
.quick-jump-input::placeholder { color:#9ca3af; }
.quick-jump-results { max-height:min(52vh,430px); overflow-y:auto; padding:8px; }
.quick-jump-item { display:flex; align-items:center; gap:12px; width:100%; padding:10px 12px; border:0; border-radius:10px; background:transparent; color:#1f2937; text-align:left; cursor:pointer; }
.quick-jump-item.is-active { background:var(--el-color-primary-light-9,#ecf5ff); color:var(--el-color-primary,#409eff); }
.quick-jump-item-icon { display:grid; flex:0 0 36px; width:36px; height:36px; place-items:center; border-radius:9px; background:#f3f4f6; font-size:18px; }
.quick-jump-item.is-active .quick-jump-item-icon { background:#fff; }
.quick-jump-item-copy { display:flex; flex:1; min-width:0; flex-direction:column; gap:3px; }
.quick-jump-item-copy strong,.quick-jump-item-copy small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.quick-jump-item-copy strong { font-size:14px; }.quick-jump-item-copy small { color:#9ca3af; font-size:12px; }
.quick-jump-enter { flex:0 0 auto; opacity:0; }.quick-jump-item.is-active .quick-jump-enter { opacity:1; }
.quick-jump-empty { display:grid; min-height:150px; place-items:center; color:#9ca3af; font-size:14px; }
.quick-jump-footer { display:flex; align-items:center; gap:16px; min-height:42px; padding:0 14px; border-top:1px solid #e5e7eb; background:#f9fafb; color:#6b7280; font-size:12px; }
.quick-jump-trigger { margin-left:auto; }
kbd { display:inline-flex; align-items:center; justify-content:center; min-width:22px; min-height:20px; padding:0 5px; border:1px solid #d1d5db; border-bottom-width:2px; border-radius:5px; background:#fff; color:#6b7280; font-family:inherit; font-size:11px; }
.quick-jump-fade-enter-active,.quick-jump-fade-leave-active { transition:opacity 150ms ease; }
.quick-jump-fade-enter-active .quick-jump-panel,.quick-jump-fade-leave-active .quick-jump-panel { transition:transform 150ms ease,opacity 150ms ease; }
.quick-jump-fade-enter-from,.quick-jump-fade-leave-to { opacity:0; }
.quick-jump-fade-enter-from .quick-jump-panel,.quick-jump-fade-leave-to .quick-jump-panel { opacity:0; transform:translateY(-8px) scale(.985); }
@media (max-width:560px) { .quick-jump-overlay { padding:72px 12px 12px; }.quick-jump-footer { gap:8px; }.quick-jump-trigger { display:none; } }
@media (prefers-reduced-motion:reduce) { .quick-jump-fade-enter-active,.quick-jump-fade-leave-active,.quick-jump-fade-enter-active .quick-jump-panel,.quick-jump-fade-leave-active .quick-jump-panel { transition:none; } }
</style>
