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

export function startMongoSessionProbe(instanceId) {
  return client.post("/mongodb/session-probes", { instance_id: instanceId });
}

export function getMongoOperations(token) {
  return client.get(`/mongodb/session-probes/${token}/operations`);
}

export function killMongoOperation(token, operationId) {
  return client.post(`/mongodb/session-probes/${token}/kill`, { operation_id: operationId });
}

export function stopMongoSessionProbe(token) {
  return client.post(`/mongodb/session-probes/${token}/stop`);
}
