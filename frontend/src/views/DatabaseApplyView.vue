<template>
  <div class="page apply-page">
    <div class="page-heading">
      <div><div class="eyebrow">RESOURCE DELIVERY</div><h2>数据库申请</h2><p>选择数据库产品与交付架构，提交后将进入资源审批流程。</p></div>
      <el-steps :active="0" simple class="apply-steps"><el-step title="选择产品" /><el-step title="配置资源" /><el-step title="确认申请" /></el-steps>
    </div>
    <el-card shadow="never" class="apply-card">
      <section class="config-row">
        <div class="row-label"><strong>地域</strong><span>选择部署地域</span></div>
        <div><el-select v-model="form.region" class="region-select" size="large"><el-option v-for="region in regions" :key="region.value" :label="region.label" :value="region.value" /></el-select>
          <div class="row-tip"><el-icon><InfoFilled /></el-icon>数据库创建后地域不可更改，请确保应用服务与数据库位于同一地域。</div>
        </div>
      </section>
      <el-divider />
      <section class="config-row">
        <div class="row-label"><strong>数据库引擎</strong><span>选择交付产品</span></div>
        <div class="engine-grid">
          <button v-for="engine in engines" :key="engine.key" type="button" class="engine-card" :class="{ active: form.engine === engine.key }" @click="selectEngine(engine)">
            <span v-if="form.engine === engine.key" class="selected-mark"><el-icon><Check /></el-icon></span>
            <span class="engine-icon" :class="'engine-' + engine.key">{{ engine.badge }}</span>
            <span class="engine-main"><strong>{{ engine.name }}</strong><span>{{ engine.description }}</span></span>
            <span class="engine-meta"><em>版本</em><b>{{ engine.version }}</b></span>
          </button>
        </div>
      </section>
      <el-divider />
      <section class="config-row">
        <div class="row-label"><strong>产品架构</strong><span>标准高可用交付</span></div>
        <div class="architecture-box">
          <div class="architecture-title"><div class="architecture-icon"><el-icon><Share /></el-icon></div>
            <div><strong>{{ selectedEngine.architecture }}</strong><span>{{ selectedEngine.architectureTip }}</span></div>
          </div><el-tag type="success" effect="light">高可用</el-tag>
        </div>
      </section>
      <el-divider />
      <section class="config-row">
        <div class="row-label"><strong>实例规格</strong><span>选择计算资源</span></div>
        <div class="option-grid specification-grid">
          <button v-for="item in specifications" :key="item.key" type="button" class="option-card" :class="{ active: form.specification === item.key }" @click="selectSpecification(item)">
            <span><strong>{{ item.key }}</strong><em>{{ item.cpu }}C {{ item.memory }}G</em></span>
            <el-icon v-if="form.specification === item.key"><Check /></el-icon>
          </button>
        </div>
      </section>
      <el-divider />
      <section class="config-row">
        <div class="row-label"><strong>存储空间</strong><span>选择数据盘容量</span></div>
        <div class="option-grid storage-grid">
          <button v-for="size in storageOptions" :key="size" type="button" class="option-card storage-card" :class="{ active: form.storageGb === size }" @click="form.storageGb = size">
            <strong>{{ size }}<small>GB</small></strong>
            <el-icon v-if="form.storageGb === size"><Check /></el-icon>
          </button>
        </div>
      </section>
      <el-divider />
      <section class="config-row">
        <div class="row-label"><strong>申请信息</strong><span>完善使用信息</span></div>
        <el-form ref="formRef" :model="form" :rules="rules" label-position="top" class="basic-form">
          <el-form-item label="申请名称" prop="name"><el-input v-model="form.name" maxlength="40" show-word-limit placeholder="例如：订单中心生产数据库" /></el-form-item>
          <el-form-item label="使用环境" prop="environment"><el-radio-group v-model="form.environment">
            <el-radio-button value="production">生产环境</el-radio-button><el-radio-button value="staging">预发环境</el-radio-button><el-radio-button value="testing">测试环境</el-radio-button>
          </el-radio-group></el-form-item>
          <el-form-item label="申请说明" prop="reason" class="reason-item"><el-input v-model="form.reason" type="textarea" :rows="3" maxlength="200" show-word-limit placeholder="请说明业务用途、预估访问量等信息" /></el-form-item>
        </el-form>
      </section>
    </el-card>
    <div class="submit-bar">
      <div class="selection-summary"><span>当前选择</span><strong>{{ selectedEngine.name }} {{ selectedEngine.version }}</strong><i></i><span>{{ selectedSpecification.cpu }}C{{ selectedSpecification.memory }}G / {{ form.storageGb }}GB</span><i></i><span>{{ selectedEngine.architecture }}</span></div>
      <el-button type="primary" size="large" :loading="submitting" @click="handleNext">下一步：配置资源 <el-icon class="el-icon--right"><ArrowRight /></el-icon></el-button>
    </div>
  </div>
</template>

<script setup>
import { computed, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { ArrowRight, Check, InfoFilled, Share } from "@element-plus/icons-vue";
const engines = [
  { key:"mysql", badge:"My", name:"MySQL", version:"8.4", description:"企业级关系型数据库", architecture:"InnoDB Cluster 高可用模式", architectureTip:"多节点一致性复制，支持自动故障转移" },
  { key:"mongodb", badge:"M", name:"MongoDB", version:"7.0", description:"文档型数据库", architecture:"副本集模式", architectureTip:"主从自动选举，保障数据冗余与服务连续性" },
  { key:"redis", badge:"R", name:"Redis", version:"6.2", description:"高性能内存数据库", architecture:"Cluster 集群模式", architectureTip:"数据分片与多副本部署，支持横向扩展" },
  { key:"postgresql", badge:"Pg", name:"PostgreSQL", version:"18", description:"高级开源关系型数据库", architecture:"流复制高可用模式", architectureTip:"基于流复制构建主备架构，支持故障切换" },
];
const regions = [{ label:"上海", value:"cn-shanghai" },{ label:"深圳", value:"cn-shenzhen" },{ label:"南京", value:"cn-nanjing" },{ label:"香港", value:"cn-hongkong" }];
const specifications = [{key:"small",cpu:2,memory:4},{key:"medium",cpu:4,memory:8},{key:"large",cpu:8,memory:16},{key:"xlarge",cpu:16,memory:32}];
const storageOptions = [100,200,400,800,1000];
const formRef=ref(); const submitting=ref(false);
const form=reactive({ region:"cn-shanghai", engine:"mysql", version:"8.4", architecture:"InnoDB Cluster 高可用模式", specification:"small", cpu:2, memory:4, storageGb:100, name:"", environment:"production", reason:"" });
const rules={ name:[{required:true,message:"请输入申请名称",trigger:"blur"}], environment:[{required:true,message:"请选择使用环境",trigger:"change"}], reason:[{required:true,message:"请输入申请说明",trigger:"blur"}] };
const selectedEngine=computed(()=>engines.find(item=>item.key===form.engine)||engines[0]);
const selectedSpecification=computed(()=>specifications.find(item=>item.key===form.specification)||specifications[0]);
function selectEngine(engine){ form.engine=engine.key; form.version=engine.version; form.architecture=engine.architecture; }
function selectSpecification(item){ form.specification=item.key; form.cpu=item.cpu; form.memory=item.memory; }
async function handleNext(){ const valid=await formRef.value.validate().catch(()=>false); if(!valid)return; submitting.value=true; try { localStorage.setItem("database_application_draft",JSON.stringify({...form})); ElMessage.success("产品信息已保存，资源配置接口将在下一阶段接入"); } finally { submitting.value=false; } }
</script>

<style scoped>
.apply-page{padding-bottom:78px}.page-heading{display:flex;align-items:center;justify-content:space-between;gap:32px;margin-bottom:16px;padding:8px 4px 0}.page-heading h2{margin:3px 0 6px;font-size:24px;color:#172033}.page-heading p,.row-label span,.architecture-title span{margin:0;color:#7b879a;font-size:13px}.eyebrow{color:#1677ff;font-size:11px;font-weight:700;letter-spacing:1.5px}.apply-steps{width:470px;background:transparent}.apply-card{border:1px solid #e5eaf2;box-shadow:0 8px 28px rgba(27,45,78,.06)}.apply-card :deep(.el-card__body){padding:10px 28px}.config-row{display:grid;grid-template-columns:180px minmax(0,1fr);gap:30px;padding:22px 0}.row-label{display:flex;flex-direction:column;gap:6px}.row-label strong{font-size:16px;color:#172033}.region-select{width:380px}.row-tip{display:flex;align-items:center;gap:7px;margin-top:10px;color:#7b879a;font-size:13px}.row-tip .el-icon{color:#1677ff}.engine-grid{display:grid;grid-template-columns:repeat(2,minmax(290px,1fr));gap:14px}.engine-card{position:relative;display:grid;grid-template-columns:46px 1fr auto;align-items:center;gap:14px;min-height:94px;padding:18px;border:1px solid #dfe5ee;background:#fff;color:#172033;text-align:left;cursor:pointer;transition:.18s ease}.engine-card:hover{border-color:#86b8ff;box-shadow:0 6px 18px rgba(22,119,255,.1);transform:translateY(-1px)}.engine-card.active{border:2px solid #1677ff;padding:17px;background:linear-gradient(135deg,#f7fbff,#fff 70%);box-shadow:0 6px 20px rgba(22,119,255,.12)}.selected-mark{position:absolute;right:-1px;top:-1px;width:25px;height:25px;color:#fff;background:#1677ff;clip-path:polygon(0 0,100% 0,100% 100%)}.selected-mark .el-icon{position:absolute;top:3px;right:2px;font-size:11px}.engine-icon{display:grid;place-items:center;width:44px;height:44px;border-radius:11px;color:#fff;font-size:14px;font-weight:800}.engine-mysql{background:linear-gradient(135deg,#1677ff,#44b5ff)}.engine-mongodb{background:linear-gradient(135deg,#14854f,#4fbd73)}.engine-redis{background:linear-gradient(135deg,#d63838,#f06a50)}.engine-postgresql{background:linear-gradient(135deg,#285f9d,#4c90ca)}.engine-main{display:flex;flex-direction:column;gap:5px}.engine-main strong{font-size:16px}.engine-main span{color:#8a95a7;font-size:12px}.engine-meta{display:flex;flex-direction:column;align-items:flex-end;gap:4px;padding-right:8px}.engine-meta em{color:#9aa4b4;font-size:11px;font-style:normal}.engine-meta b{font-size:18px}.architecture-box{display:flex;align-items:center;justify-content:space-between;max-width:760px;padding:17px 20px;border:1px solid #b8d7ff;background:#f6faff}.architecture-title{display:flex;align-items:center;gap:13px}.architecture-title>div:last-child{display:flex;flex-direction:column;gap:5px}.architecture-icon{display:grid;place-items:center;width:38px;height:38px;border-radius:50%;color:#1677ff;background:#e5f1ff}.basic-form{display:grid;grid-template-columns:minmax(260px,1fr) minmax(340px,1fr);gap:2px 22px;max-width:900px}.reason-item{grid-column:1/-1}.submit-bar{position:fixed;z-index:10;right:18px;bottom:14px;left:254px;display:flex;align-items:center;justify-content:flex-end;gap:28px;min-height:62px;padding:10px 26px;border:1px solid #e1e7f0;background:rgba(255,255,255,.96);box-shadow:0 -6px 22px rgba(25,42,70,.08);backdrop-filter:blur(10px)}.selection-summary{display:flex;align-items:center;gap:9px;color:#7b879a;font-size:13px}.selection-summary strong{color:#172033}.selection-summary i{width:1px;height:16px;background:#dce2eb}.option-grid{display:flex;flex-wrap:wrap;gap:12px}.option-card{position:relative;display:flex;align-items:center;justify-content:space-between;min-width:170px;height:64px;padding:0 18px;border:1px solid #dfe5ee;background:#fff;color:#172033;text-align:left;cursor:pointer;transition:.18s ease}.option-card:hover{border-color:#86b8ff;box-shadow:0 4px 14px rgba(22,119,255,.09)}.option-card.active{border:2px solid #1677ff;padding:0 17px;background:#f7fbff}.option-card span{display:flex;flex-direction:column;gap:5px}.option-card em{color:#7b879a;font-size:13px;font-style:normal}.option-card>.el-icon{color:#1677ff}.storage-card{min-width:130px}.storage-card strong{font-size:20px}.storage-card small{margin-left:3px;color:#7b879a;font-size:12px;font-weight:500}
@media(max-width:1100px){.page-heading{align-items:flex-start;flex-direction:column}.apply-steps{width:100%}.engine-grid{grid-template-columns:1fr}.config-row{grid-template-columns:140px minmax(0,1fr)}.basic-form{grid-template-columns:1fr}.reason-item{grid-column:auto}}
</style>
