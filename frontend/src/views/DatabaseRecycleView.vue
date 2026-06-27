<template>
  <div class="page resource-list-page">
    <div class="list-heading"><div><h2>数据库回收</h2><p>发起闲置或到期数据库的安全回收申请。</p></div><el-button type="primary" disabled>发起回收</el-button></div>
    <el-card shadow="never"><el-empty><template #description><p>暂无待回收数据库，回收流程接口将在下一阶段接入</p></template></el-empty></el-card>
  </div>
</template>
<style scoped>
.list-heading{display:flex;justify-content:space-between;align-items:center;margin:4px 2px 16px}.list-heading h2{margin:0 0 6px;font-size:24px;color:#172033}.list-heading p{margin:0;color:#7b879a;font-size:13px}.resource-list-page :deep(.el-card__body){min-height:420px;display:grid;place-items:center}
</style>
