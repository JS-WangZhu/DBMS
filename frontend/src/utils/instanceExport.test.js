import assert from "node:assert/strict";
import test from "node:test";

import { getInstanceStatusExportColumns } from "./instanceExport.js";

test("MySQL status export includes both replication thread states", () => {
  const labels = getInstanceStatusExportColumns("mysql").map(([label]) => label);

  assert.deepEqual(labels, ["应用连接", "只读状态", "主从角色", "复制延迟", "I/O线程", "SQL线程"]);
});

test("PostgreSQL status export includes role and connection usage", () => {
  const labels = getInstanceStatusExportColumns("postgresql").map(([label]) => label);

  assert.deepEqual(labels, ["主从角色", "连接使用率"]);
});
