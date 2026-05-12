import client from "../client";

export function listInstances(dbType) {
  return client.get("/instances", { params: { db_type: dbType } });
}

export function createInstance(payload) {
  return client.post("/instances", payload);
}

export function updateInstance(instanceId, payload) {
  return client.patch(`/instances/${instanceId}`, payload);
}

export function deleteInstance(instanceId) {
  return client.delete(`/instances/${instanceId}`);
}

export function refreshResolve(instanceId) {
  return client.post(`/instances/${instanceId}/resolve`);
}

export function getInstanceStatusConfig() {
  return client.get("/instances/status-config");
}

export function updateInstanceStatusConfig(payload) {
  return client.put("/instances/status-config", payload);
}
