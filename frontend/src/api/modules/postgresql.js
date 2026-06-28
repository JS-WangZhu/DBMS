import client from "../client";

export function listPostgreSQLInstances(params = {}) {
  return client.get("/postgresql/instances", { params });
}

export function createPostgreSQLInstance(payload) {
  return client.post("/postgresql/instances", payload);
}

export function postgresqlStatus(instanceId) {
  return client.get(`/postgresql/instances/${instanceId}/status`);
}
