import client from "../client";

export const getPhysicalDiscoveryConfig = () => client.get("/physical-discovery/config");
export const updatePhysicalDiscoveryConfig = (payload) => client.put("/physical-discovery/config", payload);
export const listVcenters = () => client.get("/physical-discovery/vcenters");
export const createVcenter = (payload) => client.post("/physical-discovery/vcenters", payload);
export const updateVcenter = (id, payload) => client.patch(`/physical-discovery/vcenters/${id}`, payload);
export const deleteVcenter = (id) => client.delete(`/physical-discovery/vcenters/${id}`);
export const testVcenter = (id) => client.post(`/physical-discovery/vcenters/${id}/test`);
export const runVcenterDiscovery = (id) => client.post(`/physical-discovery/vcenters/${id}/run`);
export const listDiscoveryRuns = (params) => client.get("/physical-discovery/runs", { params });
export const listDiscoveryDetails = (id) => client.get(`/physical-discovery/runs/${id}/details`);
