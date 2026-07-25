<template>
  <div class="login-page">
    <section class="brand-panel">
      <div class="brand-header">
        <div class="brand-mark">D</div>
        <div class="brand-name">
          <strong>DBMS</strong>
          <span>数据库管理平台</span>
        </div>
      </div>

      <div class="brand-content">
        <div class="brand-eyebrow">DATABASE OPERATIONS</div>
        <h1>统一、可靠的<br />数据库运维工作台</h1>
        <p>集中管理数据库资产、运行状态、备份审计，让日常运维保持清晰可控。</p>
        <div class="feature-list">
          <div class="feature-item"><span>01</span><div><strong>统一资产管理</strong><p>集中维护实例、集群和访问配置</p></div></div>
          <div class="feature-item"><span>02</span><div><strong>运行状态洞察</strong><p>实时掌握指标、巡检与会话状态</p></div></div>
          <div class="feature-item"><span>03</span><div><strong>安全操作闭环</strong><p>备份、权限和操作审计统一留痕</p></div></div>
        </div>
      </div>

      <div class="brand-footer">
        <span class="status-dot"></span>
        <span>DBMS Operations Platform</span>
      </div>
    </section>

    <main class="login-main">
      <div class="login-panel">
        <div class="mobile-brand">
          <div class="brand-mark">D</div>
          <strong>DBMS 数据库管理平台</strong>
        </div>
        <div class="login-heading">
          <span class="login-kicker">安全登录</span>
          <h2>欢迎回来</h2>
          <p>请输入平台账号，继续进入数据库管理工作台。</p>
        </div>

        <el-form :model="form" label-position="top" class="login-form" @submit.prevent="onLogin">
          <el-form-item label="用户名">
            <el-input v-model.trim="form.username" :prefix-icon="User" size="large" autocomplete="username" placeholder="请输入用户名" />
          </el-form-item>
          <el-form-item label="密码">
            <el-input v-model="form.password" :prefix-icon="Lock" type="password" show-password size="large" autocomplete="current-password" placeholder="请输入密码" />
          </el-form-item>
          <el-form-item class="submit-item">
            <el-button type="primary" native-type="submit" size="large" class="login-button" :loading="loading">
              登录平台
              <el-icon class="button-arrow"><ArrowRight /></el-icon>
            </el-button>
          </el-form-item>

          <template v-if="ssoEnabled">
            <div class="login-divider"><span>或</span></div>
            <el-button class="sso-button" size="large" :loading="ssoLoading" @click="onSsoLogin">
              使用 {{ ssoProviderName }} 登录
            </el-button>
          </template>
        </el-form>

        <div class="login-footer">仅限已授权用户访问 · 操作行为将被安全审计</div>
      </div>
    </main>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";
import { ArrowRight, Lock, User } from "@element-plus/icons-vue";
import { useRoute, useRouter } from "vue-router";

import { getSsoLoginUrl, getSsoMeta, login } from "../api/modules/auth";
import { saveLoginSession } from "../services/sessionState";

const router = useRouter();
const route = useRoute();
const loading = ref(false);
const ssoLoading = ref(false);
const ssoEnabled = ref(false);
const ssoProviderName = ref("SSO");
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
    saveLoginSession(data.data);
    ElMessage.success("登录成功");
    router.push("/dashboard");
  } catch (error) {
    const status = error.response?.status;
    const serverMessage = String(error.response?.data?.message || "").trim();
    const message = status === 401 || ["invalid credentials", "username and password are required"].includes(serverMessage.toLowerCase())
      ? "用户名或密码错误"
      : serverMessage || "登录失败，请稍后重试";
    ElMessage.error(message);
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
    const meta = data?.data || {};
    ssoEnabled.value = !!meta.enabled;
    ssoProviderName.value = meta.provider_name || "SSO";
  } catch {
    ssoEnabled.value = false;
    ssoProviderName.value = "SSO";
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

onMounted(() => {
  loadSsoMeta();
  const reason = String(route.query.reason || "");
  const messages = {
    SESSION_IDLE_TIMEOUT: "登录会话已超过8小时未操作，请重新登录",
    TOKEN_EXPIRED: "登录凭证已过期，请重新登录",
    SESSION_REVOKED: "登录会话已失效，请重新登录",
    SESSION_INVALID: "登录会话无效，请重新登录",
  };
  if (messages[reason]) {
    ElMessage.warning(messages[reason]);
    router.replace({ path: "/login" });
  }
});
</script>

<style scoped>
.login-page {
  width: 100%;
  height: 100vh;
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(420px, 43%) minmax(0, 1fr);
  overflow: hidden;
  background: var(--bg-primary);
}

.brand-panel {
  position: absolute;
  inset: 0 auto 0 0;
  width: 43%;
  min-width: 420px;
  display: flex;
  flex-direction: column;
  padding: 32px 42px 30px;
  color: #fff;
  background:
    linear-gradient(rgba(255, 255, 255, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.035) 1px, transparent 1px),
    #101828;
  background-size: 40px 40px;
  box-shadow: 4px 0 16px rgba(16, 24, 40, 0.12);
  overflow-y: auto;
}

.brand-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-mark {
  flex: 0 0 40px;
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  color: #fff;
  background: var(--brand);
  box-shadow: 0 6px 14px rgba(37, 99, 235, 0.28);
  font-size: 21px;
  font-weight: 750;
}

.brand-name {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
}

.brand-name strong {
  font-size: 15px;
  letter-spacing: 0.8px;
}

.brand-name span {
  margin-top: 2px;
  color: #98a2b3;
  font-size: 11px;
}

.brand-content {
  width: min(500px, 100%);
  margin: auto 0;
  padding: 48px 0;
}

.brand-eyebrow {
  margin-bottom: 18px;
  color: #84adff;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 2px;
}

.brand-content h1 {
  margin: 0;
  color: #fff;
  font-size: clamp(32px, 3.2vw, 50px);
  font-weight: 680;
  line-height: 1.22;
  letter-spacing: -1.5px;
}

.brand-content > p {
  max-width: 470px;
  margin: 22px 0 34px;
  color: #aeb8c7;
  font-size: 14px;
  line-height: 1.9;
}

.feature-list {
  display: grid;
  gap: 1px;
  border: 1px solid rgba(255, 255, 255, 0.09);
  background: rgba(255, 255, 255, 0.09);
}

.feature-item {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr);
  gap: 14px;
  padding: 16px 18px;
  background: rgba(16, 24, 40, 0.92);
}

.feature-item > span {
  color: #84adff;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.8px;
}

.feature-item strong {
  color: #f2f4f7;
  font-size: 13px;
  font-weight: 600;
}

.feature-item p {
  margin: 4px 0 0;
  color: #7f8da3;
  font-size: 12px;
}

.brand-footer {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #667085;
  font-size: 11px;
  letter-spacing: 0.3px;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50% !important;
  background: #12b76a;
  box-shadow: 0 0 0 4px rgba(18, 183, 106, 0.12);
}

.login-main {
  grid-column: 2;
  min-width: 0;
  height: 100vh;
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 48px;
  background:
    linear-gradient(90deg, rgba(228, 231, 236, 0.45) 1px, transparent 1px),
    linear-gradient(rgba(228, 231, 236, 0.45) 1px, transparent 1px),
    var(--bg-primary);
  background-size: 48px 48px;
  overflow-y: auto;
}

.login-panel {
  width: min(420px, 100%);
  padding: 38px 40px 32px;
  border: 1px solid var(--border-soft);
  background: #fff;
  box-shadow: var(--shadow-lg);
}

.mobile-brand {
  display: none;
}

.login-heading {
  margin-bottom: 28px;
}

.login-kicker {
  display: block;
  margin-bottom: 10px;
  color: var(--brand);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 1.5px;
}

.login-heading h2 {
  margin: 0;
  color: var(--text-primary);
  font-size: 28px;
  font-weight: 680;
  letter-spacing: -0.6px;
}

.login-heading p {
  margin: 9px 0 0;
  color: var(--text-soft);
  font-size: 13px;
}

.login-form :deep(.el-form-item__label) {
  padding-bottom: 7px;
  color: var(--text-regular);
  font-size: 13px;
  font-weight: 600;
}

.login-form :deep(.el-input__wrapper) {
  min-height: 44px;
  padding: 0 13px;
  border: 1px solid var(--border-strong);
  background: #fff;
  box-shadow: none;
  transition: border-color 0.16s ease, box-shadow 0.16s ease;
}

.login-form :deep(.el-input__wrapper:hover) {
  border-color: #98a2b3;
}

.login-form :deep(.el-input__wrapper.is-focus) {
  border-color: var(--brand);
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12) !important;
}

.login-form :deep(.el-input__prefix) {
  color: #98a2b3;
}

.submit-item {
  margin-top: 26px;
  margin-bottom: 0;
}

.login-button,
.sso-button {
  width: 100%;
  min-height: 44px;
}

.login-button {
  justify-content: center;
  box-shadow: 0 6px 14px rgba(37, 99, 235, 0.2);
  font-weight: 600;
}

.button-arrow {
  margin-left: 8px;
}

.login-divider {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 22px 0;
  color: var(--text-placeholder);
  font-size: 12px;
}

.login-divider::before,
.login-divider::after {
  content: "";
  flex: 1;
  height: 1px;
  background: var(--border-soft);
}

.sso-button {
  color: var(--text-regular);
  border-color: var(--border-strong);
  background: #fff;
}

.login-footer {
  margin-top: 28px;
  padding-top: 18px;
  border-top: 1px solid var(--border-soft);
  color: var(--text-placeholder);
  font-size: 11px;
  text-align: center;
}

@media (max-width: 900px) {
  .login-page {
    display: block;
  }

  .brand-panel {
    display: none;
  }

  .login-main {
    min-height: 100vh;
    padding: 24px;
  }

  .login-panel {
    padding: 30px 28px 26px;
  }

  .mobile-brand {
    display: flex;
    align-items: center;
    gap: 11px;
    margin-bottom: 36px;
    color: var(--text-primary);
    font-size: 14px;
  }
}

@media (max-width: 480px) {
  .login-main {
    align-items: stretch;
    padding: 0;
    background: #fff;
  }

  .login-panel {
    width: 100%;
    min-height: 100vh;
    padding: 28px 22px;
    border: 0;
    box-shadow: none;
  }
}
</style>
