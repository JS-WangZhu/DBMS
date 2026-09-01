import client from "../client";

export function listFeedback(params = {}) {
  return client.get("/feedback", { params });
}

export function getFeedbackSummary() {
  return client.get("/feedback/summary");
}

export function createFeedback(payload, images = []) {
  if (!images.length) return client.post("/feedback", payload);
  const formData = new FormData();
  formData.append("subject", payload.subject || "");
  formData.append("content", payload.content || "");
  images.forEach((image) => formData.append("images", image));
  return client.post("/feedback", formData);
}

export function getFeedbackAttachment(feedbackId, attachmentId) {
  return client.get(`/feedback/${feedbackId}/attachments/${attachmentId}`, { responseType: "blob" });
}

export function markFeedbackRead(feedbackId) {
  return client.patch(`/feedback/${feedbackId}/read`);
}

export function replyFeedback(feedbackId, payload) {
  return client.post(`/feedback/${feedbackId}/replies`, payload);
}
