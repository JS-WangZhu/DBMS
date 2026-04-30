import client from "../client";

export function listAIConfigs() {
  return client.get("/ai/configs");
}

export function createAIConfig(data) {
  return client.post("/ai/configs", data);
}

export function updateAIConfig(id, data) {
  return client.patch(`/ai/configs/${id}`, data);
}

export function deleteAIConfig(id) {
  return client.delete(`/ai/configs/${id}`);
}

export function performAIAnalysis(data) {
  return client.post("/ai/analyze", data, {
    timeout: 120000, // AI 分析可能比较慢，设置 2 分钟超时
  });
}
