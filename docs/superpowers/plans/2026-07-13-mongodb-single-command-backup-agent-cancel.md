# MongoDB Single-Command Backup and Agent Cancellation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make MongoDB partial backup execute and record one single-database `mongodump` command with multiple excluded collections, and make Agent cancellation terminate every active backup subprocess.

**Architecture:** Normalize MongoDB policy scope into one database plus a collection list, then use one command builder in each runtime (Server and Agent). Replace the Agent's optional single-process field with task-scoped process registration used by every subprocess-based execution path.

**Tech Stack:** Flask, SQLAlchemy, pytest, Python subprocess/threading, Vue 3, Element Plus, Vite.

## Global Constraints

- Partial MongoDB backup starts exactly one `mongodump` process.
- Stored and returned `command` is always a one-dimensional argument array.
- gzip and zstd produce one final backup file; encryption leaves one `.enc` final file.
- Existing full MongoDB and MySQL backup behavior remains compatible.
- Implement production changes only after the corresponding regression test fails for the expected reason.

---

### Task 1: Normalize the single-database MongoDB policy

**Files:**
- Modify: `backend/tests/test_mongodb_partial_backup.py`
- Modify: `backend/app/api/routes/backups.py`

**Interfaces:**
- Consumes: `_normalize_mongo_backup(db_type: str, config: dict | None)`.
- Produces: `{"mode": "partial", "database": str, "excluded_collections": list[str]}` or an error string.

- [ ] **Step 1: Write failing tests** for trimmed database/collections, empty database, empty or duplicate collections, full-mode normalization, unambiguous legacy conversion, and ambiguous legacy rejection.
- [ ] **Step 2: Run** `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_mongodb_partial_backup.py -q` and confirm the new shape assertions fail against the current `exclusions` model.
- [ ] **Step 3: Implement minimal normalization** in `_normalize_mongo_backup`: normalize the new structure, convert only legacy collection rows from one database, and return an explicit error for whole-database or multi-database legacy scope.
- [ ] **Step 4: Re-run the targeted tests** and confirm normalization cases pass.

### Task 2: Build and execute one Server-side mongodump command

**Files:**
- Modify: `backend/tests/test_mongodb_partial_backup.py`
- Modify: `backend/app/services/backup_executor.py`

**Interfaces:**
- Produces: `_build_partial_mongo_command(instance, password, output_file, compress, tool_path, database, excluded_collections, archive_to_stdout=False) -> list[str]`.

- [ ] **Step 1: Replace the old batch-command test** with a failing assertion that one flat command contains exactly one `--db=app`, two `--excludeCollection=...` arguments, and one archive destination.
- [ ] **Step 2: Run the targeted test** and confirm failure because only `_build_partial_mongo_commands` exists and returns nested commands.
- [ ] **Step 3: Implement the single command builder** by extending the existing MongoDB archive command with `--db` and repeated `--excludeCollection` parameters.
- [ ] **Step 4: Change `run_backup_policy`** so partial mode selects `.archive` for none/gzip and `.zst` for zstd, never imports `MongoClient`, never creates a temp directory, and routes through the existing one-command execution/compression branches.
- [ ] **Step 5: Run** `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_mongodb_partial_backup.py -q` and confirm all targeted tests pass.

### Task 3: Build one Agent-side command and add task process registration

**Files:**
- Modify: `dbms-agent/tests/test_async_backup_tasks.py`
- Create or Modify: `dbms-agent/tests/test_mongodb_partial_backup.py`
- Modify: `dbms-agent/app/api/routes/agent.py`

**Interfaces:**
- Produces: `_register_task_process(task_id, proc)`, `_unregister_task_process(task_id, proc)`, and task snapshots that omit live process objects.
- Produces: `_build_partial_mongo_command(...) -> list[str]` with the same scope semantics as Server.

- [ ] **Step 1: Write failing Agent command tests** asserting a flat single command with one database and multiple excluded collections.
- [ ] **Step 2: Write failing cancellation tests** using controllable fake processes to assert all registered processes receive `terminate()`, registration is cleaned up, and a cancelled task stays cancelled when its worker returns an error.
- [ ] **Step 3: Run** `backend\.venv\Scripts\python.exe -m pytest dbms-agent\tests\test_mongodb_partial_backup.py dbms-agent\tests\test_async_backup_tasks.py -q` and confirm expected failures.
- [ ] **Step 4: Implement the Agent single-command partial path** and remove database enumeration, temp directories, command loops, and tar creation.
- [ ] **Step 5: Implement locked process registration helpers** and initialize each submitted task with `processes: []`.
- [ ] **Step 6: Register/unregister processes in `finally`** for ordinary execution, gzip, mysqldump zstd, and mongodump zstd; pass `task_id` through helper calls.
- [ ] **Step 7: Update cancellation** to mark `cancel_requested`, snapshot all active processes under the lock, terminate live processes safely, and preserve terminal `cancelled` state.
- [ ] **Step 8: Re-run the two Agent test files** and confirm they pass.

### Task 4: Update the MongoDB policy form

**Files:**
- Modify: `frontend/src/views/BackupMongoPolicyView.vue`

**Interfaces:**
- Produces payload `extra_json.mongo_backup = {mode, database, excluded_collections}`.

- [ ] **Step 1: Replace form state** `mongo_exclusions` with `mongo_database` and `mongo_excluded_collections`.
- [ ] **Step 2: Replace the two-column exclusion rows** with one target database input and collection-only rows.
- [ ] **Step 3: Update reset, edit hydration, payload construction, and save validation** to trim values and reject blank/duplicate collection entries.
- [ ] **Step 4: Run Vue SFC compilation/build** with `npm run build` in `frontend` and confirm it passes.

### Task 5: Regression verification

**Files:**
- Verify all files changed above.

**Interfaces:**
- No new interfaces.

- [ ] **Step 1: Run targeted Backend tests:** `backend\.venv\Scripts\python.exe -m pytest backend\tests\test_mongodb_partial_backup.py backend\tests\test_remote_backup_service.py -q`.
- [ ] **Step 2: Run targeted Agent tests:** `backend\.venv\Scripts\python.exe -m pytest dbms-agent\tests\test_mongodb_partial_backup.py dbms-agent\tests\test_async_backup_tasks.py -q`.
- [ ] **Step 3: Run the broader Backend suite:** `backend\.venv\Scripts\python.exe -m pytest backend\tests -q`.
- [ ] **Step 4: Run the broader Agent suite:** `backend\.venv\Scripts\python.exe -m pytest dbms-agent\tests -q`.
- [ ] **Step 5: Run `npm run build`** in `frontend`.
- [ ] **Step 6: Inspect `git diff --check` and `git diff`** to confirm no unrelated changes, nested MongoDB command arrays, or leftover database enumeration in partial backup paths.
