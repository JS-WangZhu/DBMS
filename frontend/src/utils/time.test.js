import assert from "node:assert/strict";
import test from "node:test";

import { formatUtcTimeAsBeijing } from "./time.js";


test("formats timezone-less UTC task timestamps as Beijing time", () => {
  const formatted = formatUtcTimeAsBeijing("2026-08-16T04:05:06");

  assert.match(formatted, /2026/);
  assert.match(formatted, /08/);
  assert.match(formatted, /16/);
  assert.match(formatted, /12:05:06/);
});


test("preserves explicit timezone offsets when formatting task timestamps", () => {
  const formatted = formatUtcTimeAsBeijing("2026-08-16T12:05:06+08:00");

  assert.match(formatted, /12:05:06/);
});


test("handles empty and invalid task timestamps", () => {
  assert.equal(formatUtcTimeAsBeijing(null), "-");
  assert.equal(formatUtcTimeAsBeijing("invalid"), "invalid");
});
