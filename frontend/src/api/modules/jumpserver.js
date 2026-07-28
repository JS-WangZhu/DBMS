import client from "../client";

export function listJumpServerConfigs() {
  return client.get("/jumpserver-configs");
}

export function listJumpServerOptions() {
  return client.get("/jumpserver-configs/options");
}

export function createJumpServerConfig(payload) {
  return client.post("/jumpserver-configs", payload);
}

export function updateJumpServerConfig(id, payload) {
  return client.patch(`/jumpserver-configs/${id}`, payload);
}

export function deleteJumpServerConfig(id) {
  return client.delete(`/jumpserver-configs/${id}`);
}

export function testJumpServerConfig(id) {
  return client.post(`/jumpserver-configs/${id}/test`);
}

export function downloadJumpServerMappingTemplate() {
  return client.get("/jumpserver-configs/mapping-template", { responseType: "blob" });
}

export function importJumpServerMappings(file) {
  const formData = new FormData();
  formData.append("file", file);
  return client.post("/jumpserver-configs/mapping-import", formData);
}
