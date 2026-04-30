import client from "../client";

export function collectNow(instanceId) {
  return client.post(`/monitoring/collect/${instanceId}`);
}

export function latestSnapshot(instanceId) {
  return client.get(`/monitoring/latest/${instanceId}`);
}

// 获取实例健康状态（从数据库）
export function getInstanceHealth(instanceId) {
  return client.get(`/monitoring/instance/${instanceId}/health`);
}
