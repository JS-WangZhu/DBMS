import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const routerSource = fs.readFileSync(new URL("./index.js", import.meta.url), "utf8");
const layoutSource = fs.readFileSync(new URL("../layouts/MainLayout.vue", import.meta.url), "utf8");

test("data copy is a top-level sibling menu with task and config routes", () => {
  assert.match(routerSource, /path: "\/data-copy\/tasks"/);
  assert.match(routerSource, /path: "\/data-copy\/config"/);
  assert.match(layoutSource, /index="data-copy"/);
  assert.match(layoutSource, /<span>数据复制<\/span>/);
  assert.match(layoutSource, /index="\/data-copy\/tasks"/);
  assert.match(layoutSource, /index="\/data-copy\/config"/);
});
