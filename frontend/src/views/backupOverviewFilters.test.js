import assert from "node:assert/strict";
import test from "node:test";

import { buildClusterLabel, filterClusterOptions } from "./backupOverviewFilters.js";

const items = [
  { cluster_id: 1, cluster_name: "测试集群", db_type: "mysql", business_line: "测试业务", backup_status: "normal" },
  { cluster_id: 2, cluster_name: "Mongo集群", db_type: "mongodb", business_line: "开发业务", backup_status: "abnormal" },
  { cluster_id: 3, cluster_name: "Redis集群", db_type: "redis", business_line: "测试业务", backup_status: "abnormal" },
];

test("集群选项受业务、数据库类型和备份结果单向联动", () => {
  assert.deepEqual(
    filterClusterOptions(items, {
      business: "测试业务",
      dbType: "redis",
      result: "abnormal",
    }).map((item) => item.cluster_id),
    [3]
  );
});

test("未筛选数据库类型时在集群名称后标识数据库模型", () => {
  assert.equal(buildClusterLabel(items[0], false), "测试集群 [MySQL]");
  assert.equal(buildClusterLabel(items[0], true), "测试集群");
});
