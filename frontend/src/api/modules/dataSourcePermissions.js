import client from "../client";

export function getDataSourcePermissionOverview() {
  return client.get("/data-source-permissions/overview");
}

export function getUserDataSourcePermissions(userId) {
  return client.get(`/data-source-permissions/users/${userId}`);
}

export function updateUserDataSourcePermissions(userId, payload) {
  return client.put(`/data-source-permissions/users/${userId}`, payload);
}

export function createDataSourceGroup(payload) {
  return client.post("/data-source-permissions/groups", payload);
}

export function updateDataSourceGroup(id, payload) {
  return client.patch(`/data-source-permissions/groups/${id}`, payload);
}

export function deleteDataSourceGroup(id) {
  return client.delete(`/data-source-permissions/groups/${id}`);
}
