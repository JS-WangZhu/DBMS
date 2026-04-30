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
  background: linear-gradient(135deg, #d2e8ff 0%, #f2f9ff 40%, #dff3ef 100%);
}

.panel {
  width: 360px;
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

.sso-link-wrap {
  text-align: center;
}
</style>
