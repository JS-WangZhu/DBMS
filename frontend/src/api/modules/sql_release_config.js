import client from "../client";

export function getSqlReleaseConfig() {
  return client.get("/sql-release-config");
}

export function updateSqlReleaseConfig(payload) {
  return client.put("/sql-release-config", payload);
}
