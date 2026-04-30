import client from "../client";

export function login(payload) {
  return client.post("/auth/login", payload);
}

export function me() {
  return client.get("/auth/me");
}

export function changePassword(payload) {
  return client.patch("/auth/password", payload);
}

export function getSsoMeta(redirectUri) {
  return client.get("/auth/sso/meta", { params: { redirect_uri: redirectUri } });
}

export function getSsoLoginUrl(redirectUri) {
  return client.get("/auth/sso/url", { params: { redirect_uri: redirectUri } });
}

export function loginBySsoCallback(params) {
  return client.get("/auth/sso/callback", { params });
}
