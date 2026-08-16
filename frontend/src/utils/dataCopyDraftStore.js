export const DATA_COPY_STORAGE_KEYS = {
  tasks: "dbms_data_copy_tasks_draft",
  kafka: "dbms_data_copy_kafka_draft",
  accounts: "dbms_data_copy_accounts_draft",
  endpoints: "dbms_data_copy_endpoints_draft",
};

export function readDraftList(key, storage = globalThis.localStorage) {
  if (!storage) return [];
  try {
    const value = JSON.parse(storage.getItem(key) || "[]");
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}

export function writeDraftList(key, value, storage = globalThis.localStorage) {
  if (!storage) return;
  storage.setItem(key, JSON.stringify(Array.isArray(value) ? value : []));
}

export function nextDraftId(items) {
  return Math.max(0, ...(items || []).map((item) => Number(item.id) || 0)) + 1;
}

export function maskSecret(value) {
  return value ? "••••••••" : "-";
}

export function sanitizeDraftConfig(type, item, previous = {}) {
  const sanitized = { ...item };
  if (type === "account" || type === "kafka") {
    sanitized.password_set = Boolean(item.password || previous.password_set);
    delete sanitized.password;
  }
  if (type === "endpoint") {
    sanitized.credential_set = Boolean(item.credential || previous.credential_set);
    delete sanitized.credential;
  }
  return sanitized;
}
