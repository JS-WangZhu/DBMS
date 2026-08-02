import assert from "node:assert/strict";
import test from "node:test";

import { extractReleaseObjectNames, extractSqlTableNames } from "./sqlRelease.js";

test("extracts DML and joined table names", () => {
  const names = extractSqlTableNames(`
    UPDATE billing.orders SET status='paid' WHERE id=1;
    INSERT INTO order_logs (id) SELECT id FROM orders o JOIN users u ON u.id=o.user_id;
  `);
  assert.deepEqual([...names].sort(), ["order_logs", "orders", "users"]);
});

test("extracts multiple MongoDB collection names", () => {
  const names = extractReleaseObjectNames(`
    db.orders.updateMany({status: "new"}, {$set: {status: "paid"}});
    db.audit_logs.insertOne({source: "orders"});
  `, "mongodb");
  assert.deepEqual([...names].sort(), ["audit_logs", "orders"]);
});

test("extracts DDL table names and ignores strings or comments", () => {
  const names = extractSqlTableNames(`
    -- DELETE FROM ignored_table
    ALTER TABLE \`orders\` ADD COLUMN note varchar(20);
    CREATE TABLE IF NOT EXISTS archive_orders (id bigint);
    SELECT 'FROM fake_table' FROM real_table;
  `);
  assert.deepEqual([...names].sort(), ["archive_orders", "orders", "real_table"]);
});
