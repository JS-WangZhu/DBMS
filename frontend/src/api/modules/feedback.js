import client from "../client";

export function listFeedback(params = {}) {
  return client.get("/feedback", { params });
}

export function getFeedbackSummary() {
  return client.get("/feedback/summary");
}

export function createFeedback(payload) {
  return client.post("/feedback", payload);
}

export function markFeedbackRead(feedbackId) {
  return client.patch(`/feedback/${feedbackId}/read`);
}

export function replyFeedback(feedbackId, payload) {
  return client.post(`/feedback/${feedbackId}/replies`, payload);
}
