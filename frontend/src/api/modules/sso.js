import client from "../client";

export function getSsoConfig() {
  return client.get("/sso-config");
}

export function updateSsoConfig(data) {
  return client.put("/sso-config", data);
}
