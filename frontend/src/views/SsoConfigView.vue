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
          <div>1. 在 SSO 身份提供商（如 Keycloak / Okta / 公司统一登录）创建 OAuth2 应用，获取 Client ID 与 Client Secret。</div>
          <div>2. 将下方「回调地址」配置到身份提供商允许回调列表：<el-text type="primary">{{ defaultRedirectUri }}</el-text></div>
          <div>3. 填写授权端点、Token 端点、UserInfo 端点等信息并启用，保存后用户即可在登录页使用 SSO 登录。</div>
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

        <el-form-item label="Client ID" required>
          <el-input v-model="form.client_id" placeholder="OAuth2 应用的 Client ID" />
        </el-form-item>

        <el-form-item label="Client Secret" required>
          <el-input
            v-model="form.client_secret"
            type="password"
            show-password
            placeholder="留空或 ****** 表示不修改"
          />
        </el-form-item>

        <el-form-item label="授权端点 URL" required>
          <el-input v-model="form.authorize_url" placeholder="如 https://sso.example.com/oauth2/authorize" />
        </el-form-item>

        <el-form-item label="Token 端点 URL" required>
          <el-input v-model="form.token_url" placeholder="如 https://sso.example.com/oauth2/token" />
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
          <el-text class="hint" type="info">必须与 SSO 提供商处配置的 redirect_uri 完全一致</el-text>
        </el-form-item>

        <el-form-item label="用户名字段">
          <el-input v-model="form.username_field" placeholder="preferred_username" />
        </el-form-item>

        <el-form-item label="邮箱字段">
          <el-input v-model="form.email_field" placeholder="email" />
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
  if (!form.client_id || !form.authorize_url || !form.token_url) {
    ElMessage.warning("启用 SSO 时 Client ID / 授权端点 / Token 端点 均为必填");
    return false;
  }
  if (!form.client_secret) {
    ElMessage.warning("启用 SSO 时 Client Secret 必填（或使用先前保存的值）");
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
