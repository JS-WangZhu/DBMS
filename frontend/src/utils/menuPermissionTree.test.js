import assert from "node:assert/strict";
import test from "node:test";

import { buildMenuPermissionTree } from "./menuPermissionTree.js";

function flattenLeaves(nodes) {
  return nodes.flatMap((node) => node.children?.length ? flattenLeaves(node.children) : [node.key]);
}

test("permission tree keeps every catalog item assignable", () => {
  const catalog = [
    { key: "dashboard", label: "运行总览" },
    { key: "redis_connections", label: "Redis 连接管理" },
    { key: "postgresql_instances", label: "PostgreSQL 实例管理" },
    { key: "backup_overview", label: "备份总览" },
    { key: "future_menu", label: "未来新增菜单" },
  ];

  const tree = buildMenuPermissionTree(catalog);
  assert.deepEqual(new Set(flattenLeaves(tree.nodes)), new Set(catalog.map((item) => item.key)));
  assert.deepEqual(new Set(tree.leafKeys), new Set(catalog.map((item) => item.key)));
  assert.equal(tree.nodes.at(-1).label, "其他菜单");
});

test("permission tree applies disabled state to groups and leaves", () => {
  const tree = buildMenuPermissionTree([{ key: "dashboard", label: "运行总览" }], { disabled: true });
  assert.equal(tree.nodes[0].disabled, true);
  assert.equal(tree.nodes[0].children[0].disabled, true);
});

test("permission tree disables inherited leaves without disabling direct permissions", () => {
  const tree = buildMenuPermissionTree(
    [
      { key: "dashboard", label: "运行总览" },
      { key: "mysql_instances", label: "MySQL 实例管理" },
    ],
    { disabledKeys: ["mysql_instances"] },
  );
  const dashboard = tree.nodes.find((node) => node.key === "dashboard_group").children[0];
  const mysql = tree.nodes.find((node) => node.key === "service_manage").children[0].children[0];

  assert.equal(dashboard.disabled, false);
  assert.equal(mysql.disabled, true);
  assert.equal(mysql.inherited, true);
});

test("data copy permissions are grouped beside data release", () => {
  const catalog = [
    { key: "sql_release_apply", label: "SQL上线" },
    { key: "data_copy_tasks", label: "数据复制任务管理" },
    { key: "data_copy_config", label: "数据复制配置中心" },
  ];
  const tree = buildMenuPermissionTree(catalog);
  const dataCopy = tree.nodes.find((node) => node.key === "data_copy");

  assert.deepEqual(dataCopy.children.map((item) => item.key), ["data_copy_tasks", "data_copy_config"]);
});
