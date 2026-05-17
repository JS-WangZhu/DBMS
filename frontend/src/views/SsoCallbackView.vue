<template>
  <div class="login-wrap">
    <div class="panel">
      <h2>SSO 登录</h2>
      <el-result v-if="errorText" icon="error" title="登录失败" :sub-title="errorText" />
      <el-result v-else icon="info" title="正在登录..." sub-title="请稍候，正在完成 SSO 回调处理" />
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import { ElMessage } from "element-plus";
import { useRoute, useRouter } from "vue-router";

import { loginBySsoCallback } from "../api/modules/auth";

const route = useRoute();
const router = useRouter();
const errorText = ref("");

function getSsoRedirectUri() {
  return `${window.location.origin}/sso/callback`;
}

async function completeSsoLogin() {
  const code = String(route.query.code || "");
  const state = String(route.query.state || "");
  const token = String(route.query.token || route.query.access_token || "");
  if (!token && (!code || !state)) {
    errorText.value = "缺少 SSO 回调参数";
    return;
  }
  try {
    const params = { redirect_uri: getSsoRedirectUri() };
    if (token) {
      params.token = token;
    } else {
      params.code = code;
      params.state = state;
    }
    const { data } = await loginBySsoCallback(params);
    localStorage.setItem("dbms_token", data.data.access_token);
    localStorage.setItem("dbms_user", JSON.stringify(data.data.user));
    ElMessage.success("登录成功");
    router.replace("/dashboard");
  } catch (error) {
    errorText.value = error.response?.data?.message || "SSO 登录失败";
  }
}

onMounted(completeSsoLogin);
</script>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #d2e8ff 0%, #f2f9ff 40%, #dff3ef 100%);
}

.panel {
  width: 420px;
  padding: 28px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.95);
  box-shadow: 0 16px 36px rgba(8, 40, 71, 0.15);
}

h2 {
  margin-top: 0;
  margin-bottom: 20px;
  color: #0a3964;
}
</style>
