export function normalizeDiscoveryMode(value) {
  return value === "manual" ? "manual" : "auto";
}

export function discoveryStatusType(value) {
  if (value === "success") return "success";
  if (value === "partial_success") return "warning";
  if (value === "running") return "primary";
  return "danger";
}
