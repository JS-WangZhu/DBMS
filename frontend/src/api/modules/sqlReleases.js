import client from "../client";

export function reviewSqlRelease(payload) {
  return client.post("/sql-releases/review", payload);
}

export function submitSqlRelease(payload) {
  return client.post("/sql-releases", payload);
}

export function listSqlReleases(params = {}) {
  return client.get("/sql-releases", { params });
}

export function executeSqlRelease(id) {
  return client.post(`/sql-releases/${id}/execute`);
}

export function listSqlReleaseDatabases(clusterId, dbType) {
  return client.get("/sql-releases/databases", { params: { cluster_id: clusterId, db_type: dbType } });
}

export function listSqlReleaseObjects(clusterId, database, dbType) {
  return client.get("/sql-releases/objects", { params: { cluster_id: clusterId, database, db_type: dbType } });
}

export function listSqlReleaseTableColumns(clusterId, database, table, dbType) {
  return client.get("/sql-releases/columns", {
    params: { cluster_id: clusterId, database, table, db_type: dbType },
  });
}
