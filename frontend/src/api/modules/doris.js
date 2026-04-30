import client from "../client";

export function listDorisInstances(params = {}) {
  return client.get("/doris/instances", { params });
}

export function createDorisInstance(payload) {
  return client.post("/doris/instances", payload);
}

export function dorisFeStatus(instanceId) {
  return client.get(`/doris/instances/${instanceId}/fe-status`);
}
