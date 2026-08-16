import assert from "node:assert/strict";
import test from "node:test";

import { maskSecret, nextDraftId, readDraftList, sanitizeDraftConfig, writeDraftList } from "./dataCopyDraftStore.js";

function memoryStorage() {
  const values = new Map();
  return { getItem: (key) => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) };
}

test("data copy drafts can be persisted and restored", () => {
  const storage = memoryStorage();
  writeDraftList("tasks", [{ id: 1, name: "mysql-cdc" }], storage);
  assert.deepEqual(readDraftList("tasks", storage), [{ id: 1, name: "mysql-cdc" }]);
});

test("data copy draft helpers generate ids and mask credentials", () => {
  assert.equal(nextDraftId([{ id: 2 }, { id: 7 }]), 8);
  assert.equal(maskSecret("secret"), "••••••••");
  assert.equal(maskSecret(""), "-");
});

test("data copy configuration never persists plaintext credentials", () => {
  const account = sanitizeDraftConfig("account", { username: "repl", password: "secret" });
  const endpoint = sanitizeDraftConfig("endpoint", { credential: "token-value" });

  assert.equal(account.password, undefined);
  assert.equal(account.password_set, true);
  assert.equal(endpoint.credential, undefined);
  assert.equal(endpoint.credential_set, true);
});
