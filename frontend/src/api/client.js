import axios from "axios";

import { terminateSession } from "../services/sessionState";

const client = axios.create({
  baseURL: "/api/v1",
  timeout: 10000,
});

client.interceptors.request.use((config) => {
  const token = localStorage.getItem("dbms_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

client.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401) {
      const reason = error.response?.data?.data?.reason || "SESSION_REVOKED";
      terminateSession(reason);
    }
    return Promise.reject(error);
  },
);

export default client;
