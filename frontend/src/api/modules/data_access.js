import client from "../client";

export function queryData(payload) {
  return client.post("/data-access/query", payload);
}

export function listMongoDatabases(clusterId) {
  return client.get("/data-access/mongodb/databases", {
    params: {
      cluster_id: clusterId,
    },
  });
}

export function listMysqlDatabases(clusterId) {
  return client.get("/data-access/mysql/databases", {
    params: {
      cluster_id: clusterId,
    },
  });
}

export function listQueryHistory(page = 1, pageSize = 20, filters = {}) {
  const params = {
    page,
    page_size: pageSize,
  };
  if (filters.keyword) {
    params.keyword = filters.keyword;
  }
  if (filters.start_date) {
    params.start_date = filters.start_date;
  }
  if (filters.end_date) {
    params.end_date = filters.end_date;
  }
  return client.get("/data-access/history/query", {
    params,
  });
}

export function listChangeHistory(page = 1, pageSize = 20, filters = {}) {
  const params = {
    page,
    page_size: pageSize,
  };
  if (filters.keyword) {
    params.keyword = filters.keyword;
  }
  if (filters.start_date) {
    params.start_date = filters.start_date;
  }
  if (filters.end_date) {
    params.end_date = filters.end_date;
  }
  return client.get("/data-access/history/change", {
    params,
  });
}

export function cancelDataAccessExecution(executionId) {
  return client.post("/data-access/cancel", {
    execution_id: executionId,
  });
}

export function changeData(payload) {
  return client.post("/data-access/change", payload);
}

export function changeDataApi(payload, apiKey) {
  return client.post("/data-access/change/api", payload, {
    headers: {
      "X-API-Key": apiKey,
    },
  });
}
