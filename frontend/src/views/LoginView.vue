<template>
  <div class="login-wrap">
    <div class="panel">
      <h2>DBMS 管理平台</h2>
      <el-form :model="form" @submit.prevent="onLogin">
        <el-form-item>
          <el-input v-model="form.username" placeholder="用户名" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="form.password" type="password" show-password placeholder="密码" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" native-type="submit" style="width: 100%" :loading="loading" @click="onLogin">登录</el-button>
        </el-form-item>
        <div v-if="ssoEnabled" class="sso-link-wrap">
          <el-link type="primary" :underline="false" @click="onSsoLogin">
            {{ ssoLoading ? "SSO登录中..." : "使用SSO登录" }}
          </el-link>
        </div>
      </el-form>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { useRouter } from "vue-router";

import { getSsoLoginUrl, getSsoMeta, login } from "../api/modules/auth";

const router = useRouter();
const loading = ref(false);
const ssoLoading = ref(false);
const ssoEnabled = ref(false);
const form = reactive({
  username: "",
  password: "",
});

async function onLogin() {
  if (!form.username || !form.password) {
    ElMessage.warning("请输入用户名和密码");
    return;
  }

  loading.value = true;
  try {
    const { data } = await login(form);
    localStorage.setItem("dbms_token", data.data.access_token);
    localStorage.setItem("dbms_user", JSON.stringify(data.data.user));
    ElMessage.success("登录成功");
    router.push("/dashboard");
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "登录失败");
  } finally {
    loading.value = false;
  }
}

function getSsoRedirectUri() {
  return `${window.location.origin}/sso/callback`;
}

async function loadSsoMeta() {
  try {
    const { data } = await getSsoMeta(getSsoRedirectUri());
    ssoEnabled.value = !!data?.data?.enabled;
  } catch {
    ssoEnabled.value = false;
  }
}

async function onSsoLogin() {
  ssoLoading.value = true;
  try {
    const { data } = await getSsoLoginUrl(getSsoRedirectUri());
    const url = data?.data?.authorize_url;
    if (!url) {
      throw new Error("SSO authorize_url missing");
    }
    window.location.href = url;
  } catch (error) {
    ElMessage.error(error.response?.data?.message || error.message || "SSO登录初始化失败");
    ssoLoading.value = false;
  }
}

onMounted(loadSsoMeta);
</script>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  background:
    radial-gradient(600px 500px at 20% 20%, rgba(45, 127, 249, 0.35), transparent 60%),
    radial-gradient(700px 500px at 80% 80%, rgba(56, 189, 248, 0.30), transparent 60%),
    linear-gradient(135deg, #e8f1ff 0%, #eaf6ff 50%, #edf9ff 100%);
}

.login-wrap::before,
.login-wrap::after {
  content: "";
  position: absolute;
  border-radius: 50%;
  filter: blur(70px);
  pointer-events: none;
  animation: float 10s ease-in-out infinite;
}

.login-wrap::before {
  width: 340px;
  height: 340px;
  background: rgba(45, 127, 249, 0.35);
  top: -80px;
  left: -80px;
}

.login-wrap::after {
  width: 380px;
  height: 380px;
  background: rgba(56, 189, 248, 0.32);
  bottom: -100px;
  right: -100px;
  animation-delay: -4s;
}

@keyframes float {
  0%, 100% {
    transform: translate(0, 0);
  }
  50% {
    transform: translate(30px, -20px);
  }
}

.panel {
  width: 380px;
  padding: 32px 30px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: saturate(180%) blur(18px);
  -webkit-backdrop-filter: saturate(180%) blur(18px);
  box-shadow: 0 20px 50px rgba(30, 48, 80, 0.18);
  border: 1px solid rgba(255, 255, 255, 0.6);
  position: relative;
  z-index: 1;
  animation: panelIn 0.45s cubic-bezier(0.22, 1, 0.36, 1);
}

@keyframes panelIn {
  0% {
    opacity: 0;
    transform: translateY(20px) scale(0.96);
  }
  100% {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

h2 {
  margin-top: 0;
  margin-bottom: 22px;
  text-align: center;
  font-size: 22px;
  letter-spacing: 0.5px;
  background: linear-gradient(135deg, #1e6fff 0%, #38bdf8 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.panel :deep(.el-input__wrapper) {
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.7);
  transition: box-shadow 0.2s ease, transform 0.15s ease;
}

.panel :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 3px rgba(45, 127, 249, 0.22) !important;
  transform: translateY(-1px);
}

.panel :deep(.el-button--primary) {
  height: 40px;
  font-weight: 600;
  letter-spacing: 2px;
  background: linear-gradient(135deg, #1e6fff 0%, #38bdf8 100%);
  border: none;
  border-radius: 10px;
  box-shadow: 0 6px 18px rgba(45, 127, 249, 0.32);
  transition: transform 0.15s ease, box-shadow 0.2s ease, filter 0.2s ease;
}

.panel :deep(.el-button--primary:hover) {
  transform: translateY(-2px);
  filter: brightness(1.05);
  box-shadow: 0 10px 24px rgba(45, 127, 249, 0.42);
}

.panel :deep(.el-button--primary:active) {
  transform: translateY(0) scale(0.98);
  box-shadow: 0 4px 10px rgba(45, 127, 249, 0.28);
}

.sso-link-wrap {
  text-align: center;
  margin-top: 4px;
}

.sso-link-wrap :deep(.el-link) {
  transition: transform 0.15s ease, color 0.2s ease;
}

.sso-link-wrap :deep(.el-link:hover) {
  transform: translateY(-1px);
  color: #38bdf8;
}
</style>
