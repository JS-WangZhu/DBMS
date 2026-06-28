import client from "../client";

export function getInspectionOverview(params = {}) {
  return client.get("/inspection/overview", { params });
}

export function runInspectionNow() {
  return client.post("/inspection/run");
}

export function muteInspectionAlert(alertId, durationMinutes) {
  return client.put(`/inspection/alerts/${alertId}/mute`, { duration_minutes: durationMinutes });
}

export function getInspectionConfig() {
  return client.get("/inspection/config");
}

export function updateInspectionConfig(payload) {
  return client.put("/inspection/config", payload);
}

export function getInspectionConfigOptions() {
  return client.get("/inspection/config/options");
}
