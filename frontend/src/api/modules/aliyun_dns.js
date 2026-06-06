import client from "../client";

export function listAliyunDomainConfigs(params = {}) {
  return client.get("/aliyun-dns/configs", { params });
}

export function createAliyunDomainConfig(payload) {
  return client.post("/aliyun-dns/configs", payload);
}

export function updateAliyunDomainConfig(id, payload) {
  return client.patch(`/aliyun-dns/configs/${id}`, payload);
}

export function deleteAliyunDomainConfig(id) {
  return client.delete(`/aliyun-dns/configs/${id}`);
}

export function listAliyunDnsRecords(params = {}) {
  return client.get("/aliyun-dns/records", { params });
}

export function createAliyunDnsRecord(payload) {
  return client.post("/aliyun-dns/records", payload);
}

export function updateAliyunDnsRecord(recordId, payload) {
  return client.patch(`/aliyun-dns/records/${recordId}`, payload);
}

export function deleteAliyunDnsRecord(recordId, params = {}) {
  return client.delete(`/aliyun-dns/records/${recordId}`, { params });
}
