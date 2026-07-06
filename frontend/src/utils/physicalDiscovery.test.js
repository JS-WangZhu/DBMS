import assert from "node:assert/strict";
import test from "node:test";
import { discoveryStatusType, normalizeDiscoveryMode } from "./physicalDiscovery.js";

test("defaults missing and invalid modes to auto", () => {
  assert.equal(normalizeDiscoveryMode(), "auto");
  assert.equal(normalizeDiscoveryMode("invalid"), "auto");
  assert.equal(normalizeDiscoveryMode("manual"), "manual");
});

test("maps partial success to warning", () => {
  assert.equal(discoveryStatusType("partial_success"), "warning");
});
