import client from "../client";

export function queryData(payload) {
  return client.post("/data-access/query", payload);
}

function buildRouteParams(clusterId, route = {}) {
  const params = {
    cluster_id: clusterId,
  };
  if (route.route_mode) {
    params.route_mode = route.route_mode;
  }
  if (route.instance_id) {
    params.instance_id = route.instance_id;
  }
  return params;
}

export function listMongoDatabases(clusterId, route = {}) {
  return client.get("/data-access/mongodb/databases", {
    params: buildRouteParams(clusterId, route),
  });
}

export function listMongoCollections(clusterId, database, route = {}) {
  return client.get("/data-access/mongodb/collections", {
    params: {
      ...buildRouteParams(clusterId, route),
      database,
    },
  });
}

export function describeMongoCollection(clusterId, database, collection, route = {}) {
  return client.get("/data-access/mongodb/collection-info", {
    params: {
      ...buildRouteParams(clusterId, route),
      database,
      collection,
    },
  });
}

export function listMysqlDatabases(clusterId, route = {}) {
  return client.get("/data-access/mysql/databases", {
    params: buildRouteParams(clusterId, route),
  });
}

export function listMysqlObjects(clusterId, database, route = {}) {
  return client.get("/data-access/mysql/objects", {
    params: {
      ...buildRouteParams(clusterId, route),
      database,
    },
  });
}

export function listMysqlTableColumns(clusterId, database, table, route = {}) {
  return client.get("/data-access/mysql/columns", {
    params: {
      ...buildRouteParams(clusterId, route),
      database,
      table,
    },
  });
}

export function listQueryHistory(page = 1, pageSize = 10, filters = {}) {
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

export function listChangeHistory(page = 1, pageSize = 10, filters = {}) {
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
