import assert from "node:assert/strict";
import test from "node:test";
import { filterQuickJumpMenus, QUICK_JUMP_MENUS } from "./quickJump.js";

test("matches Chinese menu keywords", () => {
  assert.equal(filterQuickJumpMenus(QUICK_JUMP_MENUS, "巡检参数")[0].path, "/config/inspection");
});

test("matches continuous full pinyin", () => {
  assert.equal(filterQuickJumpMenus(QUICK_JUMP_MENUS, "shujuchaxun")[0].path, "/data-access/query");
});

test("matches pinyin initials", () => {
  assert.equal(filterQuickJumpMenus(QUICK_JUMP_MENUS, "xjcs")[0].path, "/config/inspection");
});

test("keeps English product names in initials", () => {
  assert.equal(filterQuickJumpMenus(QUICK_JUMP_MENUS, "mysqlslxq")[0].path, "/databases/mysql/instance-detail");
});

test("finds MongoDB instance detail by pinyin initials", () => {
  assert.equal(filterQuickJumpMenus(QUICK_JUMP_MENUS, "mongodbslxq")[0].path, "/databases/mongodb/instance-detail");
});

test("finds Redis instance detail by pinyin initials", () => {
  assert.equal(filterQuickJumpMenus(QUICK_JUMP_MENUS, "redisslxq")[0].path, "/databases/redis/instance-detail");
});

test("returns no result for an unknown keyword", () => {
  assert.deepEqual(filterQuickJumpMenus(QUICK_JUMP_MENUS, "not-a-menu"), []);
});
