import client from "../client";

export function listClusters(dbType, filters = {}) {
  const params = { db_type: dbType };
  if (filters.business_line) {
    params.business_line = filters.business_line;
  }
  if (filters.environment) {
    params.environment = filters.environment;
  }
  if (filters.namespace) {
    params.namespace = filters.namespace;
  }
  if (filters.action) {
    params.action = filters.action;
  }
  return client.get("/clusters", { params });
}

export function createCluster(payload) {
  return client.post("/clusters", payload);
}

export function updateCluster(clusterId, payload) {
  return client.patch(`/clusters/${clusterId}`, payload);
}

export function deleteCluster(clusterId) {
  return client.delete(`/clusters/${clusterId}`);
}

// 集群健康检测
export function collectClusterHealth(clusterId) {
  return client.post(`/clusters/${clusterId}/health/collect`);
}

export function clusterLatestHealth(clusterId) {
  return client.get(`/clusters/${clusterId}/health/latest`);
}

export function checkClusterHa(clusterId) {
  return client.post(`/clusters/${clusterId}/ha/check`);
}

export function getClusterHaTopology(clusterId) {
  return client.get(`/clusters/${clusterId}/ha/topology`);
}

export function listClusterHaSwitchHistory(clusterId, page = 1, pageSize = 10, filters = {}) {
  const params = {
    page,
    page_size: pageSize,
  };
  if (filters.keyword) {
    params.keyword = filters.keyword;
  }
  return client.get(`/clusters/${clusterId}/ha/history`, { params });
}

export function executeClusterHaSwitch(clusterId, payload) {
  return client.post(`/clusters/${clusterId}/ha/switch`, payload);
}

// 集群连接性探测（MongoDB / Redis）
export function probeClusterConnectivity(clusterId) {
  return client.post(`/clusters/${clusterId}/connectivity/probe`);
}

export function clusterConnectivityLatest(clusterId) {
  return client.get(`/clusters/${clusterId}/connectivity/latest`);
}

export function listClusterTopologyHistory(clusterId, page = 1, pageSize = 10) {
  return client.get(`/clusters/${clusterId}/topology/history`, {
    params: { page, page_size: pageSize },
    timeout: 60000,
  });
}

// 获取集群统计（按项目+按数据库类型）
export function getClusterStats() {
  return client.get("/clusters/stats");
}
