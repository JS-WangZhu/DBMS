import { ElMessageBox } from "element-plus";

import client from "../api/client";
import {
  getSessionDeadline,
  hasLoginSession,
  SESSION_EVENT_KEY,
  terminateSession,
  updateSessionTiming,
} from "./sessionState";

const ACTIVITY_REPORT_INTERVAL_MS = 60 * 1000;
const WARNING_BEFORE_TIMEOUT_MS = 10 * 60 * 1000;
const CHECK_INTERVAL_MS = 15 * 1000;
const ACTIVITY_EVENTS = ["pointerdown", "keydown", "touchstart"];

let lastActivityReportAt = 0;
let activityRequest = null;
let warningOpen = false;

async function reportActivity(force = false) {
  if (!hasLoginSession()) return;
  const now = Date.now();
  if (!force && now - lastActivityReportAt < ACTIVITY_REPORT_INTERVAL_MS) return;
  if (activityRequest) return activityRequest;

  lastActivityReportAt = now;
  activityRequest = client
    .post("/auth/activity")
    .then(({ data }) => {
      updateSessionTiming(data?.data || {});
      return data?.data;
    })
    .catch((error) => {
      if (error.response?.status !== 401) lastActivityReportAt = 0;
      throw error;
    })
    .finally(() => {
      activityRequest = null;
    });
  return activityRequest;
}

function onHumanActivity() {
  reportActivity().catch(() => {});
}

async function showTimeoutWarning() {
  if (warningOpen || !hasLoginSession()) return;
  warningOpen = true;
  try {
    await ElMessageBox.confirm(
      "登录会话将在 10 分钟内因长时间未操作而退出，是否继续使用？",
      "会话即将超时",
      {
        confirmButtonText: "继续使用",
        cancelButtonText: "退出登录",
        type: "warning",
        closeOnClickModal: false,
        closeOnPressEscape: false,
      },
    );
    await reportActivity(true);
  } catch {
    await logoutCurrentSession();
  } finally {
    warningOpen = false;
  }
}

function checkIdleDeadline() {
  if (!hasLoginSession()) return;
  const deadline = getSessionDeadline();
  if (!deadline) return;
  const remaining = deadline - Date.now();
  if (remaining <= 0) {
    terminateSession("SESSION_IDLE_TIMEOUT");
    return;
  }
  if (remaining <= WARNING_BEFORE_TIMEOUT_MS) showTimeoutWarning();
}

function onStorage(event) {
  if (event.key !== SESSION_EVENT_KEY || !event.newValue) return;
  try {
    const payload = JSON.parse(event.newValue);
    if (payload.type === "ended") {
      terminateSession(payload.reason, { broadcast: false });
    }
  } catch {
    terminateSession("SESSION_REVOKED", { broadcast: false });
  }
}

export function startSessionMonitor() {
  ACTIVITY_EVENTS.forEach((name) => window.addEventListener(name, onHumanActivity, { passive: true }));
  window.addEventListener("storage", onStorage);
  const timer = window.setInterval(checkIdleDeadline, CHECK_INTERVAL_MS);
  checkIdleDeadline();

  return () => {
    ACTIVITY_EVENTS.forEach((name) => window.removeEventListener(name, onHumanActivity));
    window.removeEventListener("storage", onStorage);
    window.clearInterval(timer);
  };
}

export async function logoutCurrentSession() {
  try {
    if (hasLoginSession()) await client.post("/auth/logout");
  } catch {
    // Local logout must still complete if the server session is already invalid.
  } finally {
    terminateSession("logout");
  }
}
