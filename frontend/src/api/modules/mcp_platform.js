import client from "../client";

export function listMcpApiKeys() {
  return client.get("/mcp/api-keys");
}

export function createMcpApiKey(payload) {
  return client.post("/mcp/api-keys", payload);
}

export function deleteMcpApiKey(id) {
  return client.delete(`/mcp/api-keys/${id}`);
}
