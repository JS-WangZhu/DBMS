import client from "../client";

export function listRedisInstances(params = {}) {
  return client.get("/redis/instances", { params });
}

export function createRedisInstance(payload) {
  return client.post("/redis/instances", payload);
}

export function redisClusterHealth(instanceId) {
  return client.get(`/redis/instances/${instanceId}/cluster-health`);
}
