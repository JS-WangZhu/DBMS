import client from "../client";

export function getPermissionApplicationSources() {
  return client.get("/data-source-permission-applications/sources");
}

export function listPermissionApplications(params = {}) {
  return client.get("/data-source-permission-applications", { params });
}

export function createPermissionApplication(payload) {
  return client.post("/data-source-permission-applications", payload);
}

export function reviewPermissionApplication(id, payload) {
  return client.patch(`/data-source-permission-applications/${id}/review`, payload);
}
