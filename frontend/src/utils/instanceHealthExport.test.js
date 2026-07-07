import assert from "node:assert/strict";
import test from "node:test";

import { fetchHealthForAllRows } from "./instanceHealthExport.js";

test("export health loader fetches every row across batches", async () => {
  const rows = Array.from({ length: 5 }, (_, index) => ({ id: index + 1 }));
  const calls = [];

  const health = await fetchHealthForAllRows(rows, async (ids) => {
    calls.push(ids);
    return Object.fromEntries(ids.map((id) => [id, { running_status: `status-${id}` }]));
  }, 2);

  assert.deepEqual(calls, [[1, 2], [3, 4], [5]]);
  assert.deepEqual(Object.keys(health).sort(), ["1", "2", "3", "4", "5"]);
});
