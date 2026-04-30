import client from "../client";

export function listHAConfigs() {
  return client.get("/ha/configs");
}

export function createHAConfig(payload) {
  return client.post("/ha/configs", payload);
}

export function updateHAConfig(id, payload) {
  return client.patch(`/ha/configs/${id}`, payload);
}

export function deleteHAConfig(id) {
  return client.delete(`/ha/configs/${id}`);
}

export function verifyHAConfig(payload) {
  return client.post("/ha/configs/verify", payload);
}
