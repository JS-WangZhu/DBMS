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

export function startPostgreSQLSessionProbe(instanceId) {
  return client.post("/postgresql/session-probes", { instance_id: instanceId });
}

export function getPostgreSQLSessions(token) {
  return client.get(`/postgresql/session-probes/${token}/sessions`);
}

export function killPostgreSQLSession(token, processId) {
  return client.post(`/postgresql/session-probes/${token}/kill`, { process_id: processId });
}

export function stopPostgreSQLSessionProbe(token) {
  return client.post(`/postgresql/session-probes/${token}/stop`);
}
