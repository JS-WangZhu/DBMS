<template>
  <div class="page">
    <el-card>
      <template #header>
        <div class="header-row">
          <span>SSO 登录管理</span>
          <div class="header-actions">
            <el-tag v-if="form.enabled" type="success" effect="dark">已启用</el-tag>
            <el-tag v-else type="info">未启用</el-tag>
          </div>
        </div>
      </template>

      <el-alert
        class="tips"
        type="info"
        show-icon
        :closable="false"
        title="SSO 登录流程"
      >
        <template #default>
          <div>1. 配置企业 SSO 登录域名，系统跳转时会自动附带回调地址参数；如需自定义参数名，可在 URL 中使用 {redirect_uri} 占位符。</div>
          <div>2. 将下方「回调地址」配置到身份提供商允许回调列表：<el-text type="primary">{{ defaultRedirectUri }}</el-text></div>
          <div>3. 企业 SSO 回跳到回调地址并追加 token 后，系统会调用 Token 校验端点完成登录校验。</div>
        </template>
      </el-alert>

      <el-form :model="form" label-width="140px" v-loading="loading" class="sso-form">
        <el-form-item label="启用 SSO 登录">
          <el-switch v-model="form.enabled" />
          <el-text class="hint" type="info">开启后登录页会显示「使用SSO登录」入口</el-text>
        </el-form-item>

        <el-form-item label="提供商名称">
          <el-input v-model="form.provider_name" placeholder="如 Keycloak / Okta / 公司 SSO" />
        </el-form-item>

        <el-form-item label="Client ID">
          <el-input v-model="form.client_id" placeholder="可选，仅 OAuth2 模式需要" />
        </el-form-item>

        <el-form-item label="Client Secret">
          <el-input
            v-model="form.client_secret"
            type="password"
            show-password
            placeholder="可选，留空或 ****** 表示不修改"
          />
        </el-form-item>

        <el-form-item label="企业 SSO 域名" required>
          <el-input v-model="form.authorize_url" placeholder="如 https://sso.example.com/login?callback={redirect_uri}" />
        </el-form-item>

        <el-form-item label="Token 校验 URL" required>
          <el-input v-model="form.token_url" placeholder="如 https://sso.example.com/token/verify?ticket={token}" />
        </el-form-item>

        <el-form-item label="UserInfo 端点 URL">
          <el-input v-model="form.userinfo_url" placeholder="如 https://sso.example.com/oauth2/userinfo（可选）" />
        </el-form-item>

        <el-form-item label="Scope">
          <el-input v-model="form.scope" placeholder="openid profile email" />
        </el-form-item>

        <el-form-item label="回调地址">
          <el-input v-model="form.redirect_uri" :placeholder="defaultRedirectUri">
            <template #append>
              <el-button @click="useDefaultRedirect">使用当前域名</el-button>
            </template>
          </el-input>
          <el-text class="hint" type="info">默认填写 {{ defaultRedirectUri }}；企业 SSO 会在末尾追加 ?token=xxx</el-text>
        </el-form-item>

        <el-form-item label="用户名字段">
          <el-input v-model="form.username_field" placeholder="preferred_username 或 data.accountName" />
          <el-text class="hint" type="info">Token 校验返回嵌套 JSON 时可填写点路径，如 data.username</el-text>
        </el-form-item>

        <el-form-item label="邮箱字段">
          <el-input v-model="form.email_field" placeholder="email 或 data.mail" />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="saving" @click="saveConfig">保存配置</el-button>
          <el-button @click="loadConfig">重新加载</el-button>
          <el-button type="success" plain :disabled="!form.enabled || saving" @click="testSsoLogin">测试 SSO 登录</el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from "vue";
import { ElMessage } from "element-plus";

import { getSsoConfig, updateSsoConfig } from "../api/modules/sso";
import { getSsoLoginUrl } from "../api/modules/auth";

const loading = ref(false);
const saving = ref(false);

const form = reactive({
  enabled: false,
  provider_name: "SSO",
  client_id: "",
  client_secret: "",
  authorize_url: "",
  token_url: "",
  userinfo_url: "",
  scope: "openid profile email",
  redirect_uri: "",
  username_field: "preferred_username",
  email_field: "email",
});

const defaultRedirectUri = computed(() => `${window.location.origin}/sso/callback`);

function useDefaultRedirect() {
  form.redirect_uri = defaultRedirectUri.value;
}

async function loadConfig() {
  loading.value = true;
  try {
    const { data } = await getSsoConfig();
    const row = data?.data || {};
    Object.assign(form, {
      enabled: !!row.enabled,
      provider_name: row.provider_name || "SSO",
      client_id: row.client_id || "",
      client_secret: row.client_secret || "",
      authorize_url: row.authorize_url || "",
      token_url: row.token_url || "",
      userinfo_url: row.userinfo_url || "",
      scope: row.scope || "openid profile email",
      redirect_uri: row.redirect_uri || "",
      username_field: row.username_field || "preferred_username",
      email_field: row.email_field || "email",
    });
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "加载 SSO 配置失败");
  } finally {
    loading.value = false;
  }
}

function validateForm() {
  if (!form.enabled) return true;
  if (!form.authorize_url || !form.token_url) {
    ElMessage.warning("启用 SSO 时企业 SSO 域名 / Token 校验 URL 均为必填");
    return false;
  }
  return true;
}

async function saveConfig() {
  if (!validateForm()) return;
  saving.value = true;
  try {
    const payload = { ...form };
    // 如果是脱敏占位符则不提交 client_secret，保留原值
    if (!payload.client_secret || /^\*+$/.test(payload.client_secret)) {
      delete payload.client_secret;
    }
    const { data } = await updateSsoConfig(payload);
    ElMessage.success("保存成功");
    const row = data?.data || {};
    if (row) {
      form.client_secret = row.client_secret || "";
    }
  } catch (error) {
    ElMessage.error(error.response?.data?.message || "保存失败");
  } finally {
    saving.value = false;
  }
}

async function testSsoLogin() {
  try {
    const redirectUri = form.redirect_uri || defaultRedirectUri.value;
    const { data } = await getSsoLoginUrl(redirectUri);
    const url = data?.data?.authorize_url;
    if (!url) throw new Error("authorize_url missing");
    window.open(url, "_blank");
  } catch (error) {
    ElMessage.error(error.response?.data?.message || error.message || "测试失败");
  }
}

onMounted(loadConfig);
</script>

<style scoped>
.page {
  padding: 20px;
}
.header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header-actions {
  display: flex;
  gap: 8px;
}
.tips {
  margin-bottom: 16px;
}
.sso-form {
  max-width: 820px;
}
.hint {
  margin-left: 10px;
}
</style>
