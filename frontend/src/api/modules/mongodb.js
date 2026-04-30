import client from "../client";

export function listMongoInstances(params = {}) {
  return client.get("/mongodb/instances", { params });
}

export function createMongoInstance(payload) {
  return client.post("/mongodb/instances", payload);
}

export function mongoReplicaStatus(instanceId) {
  return client.get(`/mongodb/instances/${instanceId}/replica-status`);
}
