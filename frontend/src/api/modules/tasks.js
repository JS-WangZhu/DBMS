import client from "../client";

export function listTaskSchedules(params = {}) {
  return client.get("/task-management/schedules", { params });
}

export function createTaskSchedule(payload) {
  return client.post("/task-management/schedules", payload);
}

export function updateTaskSchedule(taskId, payload) {
  return client.patch(`/task-management/schedules/${taskId}`, payload);
}

export function deleteTaskSchedule(taskId) {
  return client.delete(`/task-management/schedules/${taskId}`);
}

export function runTaskSchedule(taskId) {
  return client.post(`/task-management/schedules/${taskId}/run`);
}

export function listTaskResults(params = {}) {
  return client.get("/task-management/results", { params });
}

export function getTaskResult(runId) {
  return client.get(`/task-management/results/${runId}`);
}

export function deleteTaskResults(ids) {
  return client.delete("/task-management/results", { data: { ids } });
}

export function retryTaskResult(runId) {
  return client.post(`/task-management/results/${runId}/retry`);
}
