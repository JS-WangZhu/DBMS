<template>
  <div class="page">
    <el-card>
      <template #header><b>物理机探测管理</b></template>
      <el-form :inline="true" :model="config">
        <el-form-item label="启用自动探测"><el-switch v-model="config.enabled" /></el-form-item>
        <el-form-item label="轮询周期（分钟）"><el-input-number v-model="config.poll_interval_minutes" :min="1" /></el-form-item>
        <el-form-item label="连接超时（秒）"><el-input-number v-model="config.connect_timeout_seconds" :min="1" /></el-form-item>
        <el-form-item label="单批实例数"><el-input-number v-model="config.batch_size" :min="1" /></el-form-item>
        <el-form-item><el-button type="primary" @click="saveConfig">保存配置</el-button></el-form-item>
      </el-form>
    </el-card>

    <el-card class="section">
      <template #header>
        <div class="header"><b>vCenter 配置</b><el-button type="primary" @click="openCreate">新增 vCenter</el-button></div>
      </template>
      <el-table :data="vcenters" v-loading="loading">
        <el-table-column prop="name" label="名称" />
        <el-table-column label="地址"><template #default="s">{{ s.row.address }}:{{ s.row.port }}</template></el-table-column>
        <el-table-column label="CIDR"><template #default="s">{{ s.row.cidrs.join(', ') }}</template></el-table-column>
        <el-table-column prop="username" label="只读用户" />
        <el-table-column label="状态"><template #default="s"><el-tag :type="s.row.enabled ? 'success' : 'info'">{{ s.row.enabled ? '启用' : '停用' }}</el-tag></template></el-table-column>
        <el-table-column label="最近测试"><template #default="s">{{ s.row.last_test_message || '-' }}</template></el-table-column>
        <el-table-column label="操作" width="320">
          <template #default="s">
            <el-button link type="primary" @click="openEdit(s.row)">编辑</el-button>
            <el-button link @click="toggle(s.row)">{{ s.row.enabled ? '停用' : '启用' }}</el-button>
            <el-button link @click="testConnection(s.row)">连接测试</el-button>
            <el-button link type="success" :disabled="!config.enabled || !s.row.enabled" @click="runNow(s.row)">立即探测</el-button>
            <el-button link type="danger" @click="remove(s.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card class="section">
      <template #header><b>探测记录</b></template>
      <el-table :data="runs.items" @row-click="showDetails">
        <el-table-column prop="id" label="运行ID" width="90" />
        <el-table-column prop="vcenter_name" label="vCenter" />
        <el-table-column prop="trigger_type" label="触发方式" />
        <el-table-column label="状态"><template #default="s"><el-tag :type="discoveryStatusType(s.row.status)">{{ s.row.status }}</el-tag></template></el-table-column>
        <el-table-column label="成功/失败"><template #default="s">{{ s.row.success_count }}/{{ s.row.failed_count }}</template></el-table-column>
        <el-table-column prop="started_at" label="开始时间" />
        <el-table-column prop="error_message" label="汇总错误" />
      </el-table>
      <el-pagination v-model:current-page="page" :page-size="20" :total="runs.total" @current-change="loadRuns" />
    </el-card>

    <el-dialog v-model="dialogVisible" :title="form.id ? '编辑 vCenter' : '新增 vCenter'" width="560px">
      <el-form label-width="120px">
        <el-form-item label="名称"><el-input v-model.trim="form.name" /></el-form-item>
        <el-form-item label="地址"><el-input v-model.trim="form.address" /></el-form-item>
        <el-form-item label="端口"><el-input-number v-model="form.port" :min="1" :max="65535" /></el-form-item>
        <el-form-item label="虚机 IP CIDR"><el-input v-model="form.cidrsText" type="textarea" placeholder="每行一个，例如 10.20.0.0/16" /></el-form-item>
        <el-form-item label="只读用户"><el-input v-model.trim="form.username" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="form.password" type="password" show-password :placeholder="form.id ? '留空则不修改' : ''" /></el-form-item>
        <el-form-item label="校验证书"><el-switch v-model="form.verify_ssl" /></el-form-item>
        <el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialogVisible=false">取消</el-button><el-button type="primary" @click="saveVcenter">保存</el-button></template>
    </el-dialog>

    <el-drawer v-model="detailVisible" title="探测明细" size="55%">
      <el-table :data="details">
        <el-table-column prop="instance_name" label="实例" />
        <el-table-column prop="input_ip" label="输入 IP" />
        <el-table-column prop="status" label="状态" />
        <el-table-column prop="discovered_address" label="发现结果" />
        <el-table-column prop="error_message" label="失败原因" />
      </el-table>
    </el-drawer>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage, ElMessageBox } from "element-plus";
import {
  createVcenter, deleteVcenter, getPhysicalDiscoveryConfig, listDiscoveryDetails,
  listDiscoveryRuns, listVcenters, runVcenterDiscovery, testVcenter,
  updatePhysicalDiscoveryConfig, updateVcenter,
} from "../api/modules/physical_discovery";
import { discoveryStatusType } from "../utils/physicalDiscovery";

const config = reactive({ enabled: false, poll_interval_minutes: 30, connect_timeout_seconds: 10, batch_size: 500 });
const vcenters = ref([]); const loading = ref(false); const dialogVisible = ref(false);
const detailVisible = ref(false); const details = ref([]); const page = ref(1);
const runs = reactive({ items: [], total: 0 });
const form = reactive({ id: null, name: "", address: "", port: 443, cidrsText: "", username: "", password: "", verify_ssl: true, enabled: true });

async function loadAll() {
  loading.value = true;
  try {
    Object.assign(config, (await getPhysicalDiscoveryConfig()).data.data);
    vcenters.value = (await listVcenters()).data.data || [];
    await loadRuns();
  } finally { loading.value = false; }
}
async function loadRuns() { const data = (await listDiscoveryRuns({ page: page.value, page_size: 20 })).data.data; runs.items = data.items; runs.total = data.total; }
async function saveConfig() { Object.assign(config, (await updatePhysicalDiscoveryConfig(config)).data.data); ElMessage.success("配置已保存"); }
function resetForm() { Object.assign(form, { id: null, name: "", address: "", port: 443, cidrsText: "", username: "", password: "", verify_ssl: true, enabled: true }); }
function openCreate() { resetForm(); dialogVisible.value = true; }
function openEdit(row) { Object.assign(form, { ...row, password: "", cidrsText: row.cidrs.join("\n") }); dialogVisible.value = true; }
function payload() { const data = { ...form, cidrs: form.cidrsText.split(/[\n,]+/).map(v => v.trim()).filter(Boolean) }; delete data.id; delete data.cidrsText; if (!data.password) delete data.password; return data; }
async function saveVcenter() { if (form.id) await updateVcenter(form.id, payload()); else await createVcenter(payload()); dialogVisible.value = false; await loadAll(); }
async function toggle(row) { await updateVcenter(row.id, { enabled: !row.enabled }); await loadAll(); }
async function testConnection(row) { await testVcenter(row.id); await loadAll(); ElMessage.success("连接测试已完成"); }
async function runNow(row) { await runVcenterDiscovery(row.id); ElMessage.success("探测任务已执行"); await loadRuns(); }
async function remove(row) { await ElMessageBox.confirm(`确认删除 ${row.name}？`, "提示"); await deleteVcenter(row.id); await loadAll(); }
async function showDetails(row) { details.value = (await listDiscoveryDetails(row.id)).data.data || []; detailVisible.value = true; }
onMounted(loadAll);
</script>

<style scoped>
.page { padding: 18px; } .section { margin-top: 16px; } .header { display:flex; justify-content:space-between; align-items:center; }
</style>
