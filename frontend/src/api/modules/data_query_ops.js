import client from "../client";

export function listDataQueryOps() {
  return client.get("/data-query-ops");
}

export function createDataQueryOp(payload) {
  return client.post("/data-query-ops", payload);
}

export function updateDataQueryOp(id, payload) {
  return client.patch(`/data-query-ops/${id}`, payload);
}

export function deleteDataQueryOp(id) {
  return client.delete(`/data-query-ops/${id}`);
}
