import client from "../client";

export function listManagedInstances(dbType) {
  const params = {};
  if (dbType) params.db_type = dbType;
  return client.get("/backups/managed-instances", { params });
}

export function listPostgresqlBackupDatabases(params) {
  return client.get("/backups/postgresql/metadata/databases", { params });
}

export function listPostgresqlBackupTables(params) {
  return client.get("/backups/postgresql/metadata/tables", { params });
}

export function listNotifyTargets(params = {}) {
  return client.get("/backups/notify-targets", { params });
}

export function createNotifyTarget(payload) {
  return client.post("/backups/notify-targets", payload);
}

export function updateNotifyTarget(id, payload) {
  return client.patch(`/backups/notify-targets/${id}`, payload);
}

export function deleteNotifyTarget(id) {
  return client.delete(`/backups/notify-targets/${id}`);
}

export function testNotifyTarget(id) {
  return client.post(`/backups/notify-targets/${id}/test`);
}

export function listBackupPoliciesByType(dbType) {
  return client.get("/backups/policies", { params: { db_type: dbType } });
}

export function createBackupPolicy(payload) {
  return client.post("/backups/policies", payload);
}

export function updateBackupPolicy(id, payload) {
  return client.patch(`/backups/policies/${id}`, payload);
}

export function deleteBackupPolicy(id) {
  return client.delete(`/backups/policies/${id}`);
}

export function runBackup(policyId, dryRun = false) {
  return client.post(`/backups/run/${policyId}`, null, { params: { dry_run: dryRun } });
}

export function listBackupLogs(params = {}) {
  return client.get("/backups/logs", { params });
}

export function cancelBackupLog(logId) {
  return client.post("/backups/logs/" + logId + "/cancel");
}

export function deleteBackupLog(logId, deleteFile = false) {
  return client.delete(`/backups/logs/${logId}`, {
    params: {
      delete_file: deleteFile,
    },
  });
}

export function backupOverview(hours = 48) {
  return client.get("/backups/overview", { params: { hours } });
}

export function listBackupToolConfigs(params = {}) {
  return client.get("/backups/tool-configs", { params });
}

export function createBackupToolConfig(payload) {
  return client.post("/backup-tools", payload);
}

export function updateBackupToolConfig(id, payload) {
  return client.patch(`/backup-tools/${id}`, payload);
}

export function deleteBackupToolConfig(id) {
  return client.delete(`/backup-tools/${id}`);
}

export function verifyBackupToolConfig(id) {
  return client.post(`/backup-tools/${id}/verify`);
}

export function verifyToolOnAgent(payload) {
  return client.post("/backup-tools/agent/verify", payload);
}

export function listS3StorageConfigs(params = {}) {
  return client.get("/backups/s3-storage-configs", { params });
}

export function listS3StorageConfigsDirect(params = {}) {
  return client.get("/s3-storage/configs", { params });
}

export function createS3StorageConfig(payload) {
  return client.post("/s3-storage/configs", payload);
}

export function updateS3StorageConfig(id, payload) {
  return client.patch(`/s3-storage/configs/${id}`, payload);
}

export function deleteS3StorageConfig(id) {
  return client.delete(`/s3-storage/configs/${id}`);
}

export function listBackupAgents(params = {}) {
  return client.get("/backup-agents", { params });
}

export function createBackupAgent(payload) {
  return client.post("/backup-agents", payload);
}

export function updateBackupAgent(id, payload) {
  return client.patch(`/backup-agents/${id}`, payload);
}

export function deleteBackupAgent(id) {
  return client.delete(`/backup-agents/${id}`);
}

export function testBackupAgent(id) {
  return client.post(`/backup-agents/${id}/test`);
}

export function getBackupAgentHealth(id) {
  return client.get(`/backup-agents/${id}/health`);
}

export function listBackupKeys(params = {}) {
  return client.get("/backups/keys", { params });
}

export function createBackupKey(payload) {
  return client.post("/backups/keys", payload);
}

export function updateBackupKey(id, payload) {
  return client.patch(`/backups/keys/${id}`, payload);
}

export function deleteBackupKey(id) {
  return client.delete(`/backups/keys/${id}`);
}

export function getBackupPrivateKey(id) {
  return client.get(`/backups/keys/${id}/private-key`);
}

export function getBackupDownloadUrl(logId) {
  return client.get(`/backups/logs/${logId}/download-url`);
}

export function downloadBackupFile(logId) {
  return client.get(`/backups/logs/${logId}/download`, { responseType: "blob" });
}

export function listUserPermissions(userId) {
  return client.get(`/users/permissions/${userId}`);
}

export function listMyUserPermissions() {
  return client.get("/users/permissions/me");
}

export function updateUserPermissions(userId, payload) {
  return client.put(`/users/permissions/${userId}`, payload);
}

export function createUserApiKey(userId) {
  return client.post(`/users/permissions/${userId}/api-key`);
}

export function deleteUserApiKey(userId, keyId) {
  return client.delete(`/users/permissions/${userId}/api-key/${keyId}`);
}

export function downloadBackupFileFromAgent(logId) {
  return client.get(`/backups/logs/${logId}/download-agent`, { responseType: "blob" });
}
