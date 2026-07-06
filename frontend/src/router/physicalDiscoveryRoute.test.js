import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";


test("physical discovery route is attached to the main layout", () => {
  const source = fs.readFileSync(new URL("./index.js", import.meta.url), "utf8");

  assert.match(source, /routes\[2\]\.children\.push\(\{ path: "\/config\/physical-discovery"/);
  assert.doesNotMatch(source, /routes\[1\]\.children\.push/);
});
