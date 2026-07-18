import client from "../client";

export function listMysqlInstances(params = {}) {
  return client.get("/mysql/instances", { params });
}

export function createMysqlInstance(payload) {
  return client.post("/mysql/instances", payload);
}

export function mysqlReplication(instanceId, refresh = true) {
  return client.get(`/mysql/instances/${instanceId}/replication`, {
    params: { refresh: refresh ? "true" : "false" },
  });
}

export function mysqlInstanceDetail(instanceId, refresh = true) {
  return client.get(`/mysql/instances/${instanceId}/detail`, {
    params: { refresh: refresh ? "true" : "false" },
  });
}

export function startMysqlSessionProbe(instanceId) {
  return client.post("/mysql/session-probes", { instance_id: instanceId });
}

export function getMysqlProcesslist(token) {
  return client.get(`/mysql/session-probes/${token}/processlist`);
}

export function killMysqlProcess(token, processId) {
  return client.post(`/mysql/session-probes/${token}/kill`, { process_id: processId });
}

export function stopMysqlSessionProbe(token) {
  return client.post(`/mysql/session-probes/${token}/stop`);
}
