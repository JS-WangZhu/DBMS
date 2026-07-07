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

test("Redis status export includes cluster state", () => {
  const labels = getInstanceStatusExportColumns("redis").map(([label]) => label);

  assert.deepEqual(labels, ["主从角色", "高可用模式", "集群状态", "复制源信息", "实例内存使用率"]);
});
