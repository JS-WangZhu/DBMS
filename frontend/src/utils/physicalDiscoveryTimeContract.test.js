import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";


const source = fs.readFileSync(
  new URL("../views/PhysicalDiscoveryManageView.vue", import.meta.url),
  "utf8",
);


test("physical discovery displays all visible timestamps in Beijing time", () => {
  assert.match(source, /import \{ formatBeijingTime \} from "\.\.\/utils\/time"/);
  assert.match(source, /displayTime\(s\.row\.last_tested_at\)/);
  assert.match(source, /displayTime\(s\.row\.started_at\)/);
  assert.match(source, /label="结束时间"/);
  assert.match(source, /displayTime\(s\.row\.finished_at\)/);
});
