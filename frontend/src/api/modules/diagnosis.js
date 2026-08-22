import client from "../client";

export function getParameterCollectionConfig() {
  return client.get("/diagnosis/parameter-check/config");
}

export function updateParameterCollectionConfig(payload) {
  return client.put("/diagnosis/parameter-check/config", payload);
}

export function runParameterCollection() {
  return client.post("/diagnosis/parameter-check/collect");
}

export function listParameterCheckInstances(params = {}) {
  return client.get("/diagnosis/parameter-check/instances", { params });
}

export function listParameterVersions(instanceId) {
  return client.get(`/diagnosis/parameter-check/instances/${instanceId}/versions`);
}

export function getSlowQueryCapabilities() {
  return client.get("/diagnosis/slow-query/capabilities");
}
