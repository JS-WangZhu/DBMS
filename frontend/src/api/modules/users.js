import client from "../client";

export function listUsers(params = {}) {
  return client.get("/users", { params });
}

export function createUser(payload) {
  return client.post("/users", payload);
}

export function updateUser(userId, payload) {
  return client.patch(`/users/${userId}`, payload);
}

export function deleteUser(userId) {
  return client.delete(`/users/${userId}`);
}

export function listRoleGroups(params = {}) {
  return client.get("/users/permissions/role-groups", { params });
}

export function listRoleGroupOptions() {
  return client.get("/users/permissions/role-groups/options");
}

export function createRoleGroup(payload) {
  return client.post("/users/permissions/role-groups", payload);
}

export function updateRoleGroup(roleGroupId, payload) {
  return client.patch(`/users/permissions/role-groups/${roleGroupId}`, payload);
}

export function deleteRoleGroup(roleGroupId) {
  return client.delete(`/users/permissions/role-groups/${roleGroupId}`);
}
