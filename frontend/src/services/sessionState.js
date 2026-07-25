const SESSION_DEADLINE_KEY = "dbms_session_idle_deadline";
const SESSION_TIMEOUT_KEY = "dbms_session_idle_timeout";
const SESSION_EVENT_KEY = "dbms_session_event";

export function hasLoginSession() {
  return !!localStorage.getItem("dbms_token");
}

export function updateSessionTiming(session = {}) {
  const remainingSeconds = Number(session.idle_remaining_seconds);
  const timeoutSeconds = Number(session.idle_timeout_seconds);
  if (Number.isFinite(remainingSeconds) && remainingSeconds >= 0) {
    localStorage.setItem(SESSION_DEADLINE_KEY, String(Date.now() + remainingSeconds * 1000));
  }
  if (Number.isFinite(timeoutSeconds) && timeoutSeconds > 0) {
    localStorage.setItem(SESSION_TIMEOUT_KEY, String(timeoutSeconds));
  }
}

export function saveLoginSession(data) {
  localStorage.setItem("dbms_token", data.access_token);
  localStorage.setItem("dbms_user", JSON.stringify(data.user));
  updateSessionTiming(data.session);
}

export function getSessionDeadline() {
  return Number(localStorage.getItem(SESSION_DEADLINE_KEY) || 0);
}

export function clearLoginSession() {
  localStorage.removeItem("dbms_token");
  localStorage.removeItem("dbms_user");
  localStorage.removeItem(SESSION_DEADLINE_KEY);
  localStorage.removeItem(SESSION_TIMEOUT_KEY);
}

export function terminateSession(reason = "SESSION_REVOKED", options = {}) {
  const { broadcast = true, redirect = true } = options;
  clearLoginSession();

  if (broadcast) {
    localStorage.setItem(
      SESSION_EVENT_KEY,
      JSON.stringify({ type: "ended", reason, at: Date.now(), nonce: Math.random() }),
    );
  }

  if (redirect && window.location.pathname !== "/login") {
    const queryReason = encodeURIComponent(String(reason || "SESSION_REVOKED"));
    window.location.assign(`/login?reason=${queryReason}`);
  }
}

export { SESSION_EVENT_KEY };
