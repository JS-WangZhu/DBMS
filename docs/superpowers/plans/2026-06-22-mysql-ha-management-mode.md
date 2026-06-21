# MySQL HA Management Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the MySQL HA enable switch with `none`, `orc`, and `dbms` management modes, allowing DBMS HA mutations only in `dbms` mode.

**Architecture:** Store the management owner on `DatabaseCluster.ha_mode`, normalize and validate it at the cluster API boundary, and enforce it again at every HA mutation endpoint. Topology and history remain readable in all modes; frontend controls communicate ownership and expose mutation actions only for DBMS-managed clusters.

**Tech Stack:** Flask, Flask-SQLAlchemy, pytest, Vue 3, Element Plus, Vite.

---

## File map

- `backend/app/models/db_asset.py`: cluster field and serialized API contract.
- `backend/app/services/bootstrap.py`: additive schema compatibility migration.
- `backend/app/api/routes/clusters.py`: mode normalization, cluster CRUD, topology visibility, and HA mutation guard.
- `backend/app/services/mcp_status.py`: MCP cluster status contract.
- `backend/tests/test_clusters.py`: cluster CRUD/default/validation behavior.
- `backend/tests/test_mysql_ha_mode.py`: endpoint authorization by HA mode.
- `frontend/src/views/ClusterManageView.vue`: mode configuration and list display.
- `frontend/src/views/MysqlConnectionManageView.vue`: ownership display and HA action availability.

### Task 1: Add the HA mode data contract

**Files:**
- Modify: `backend/app/models/db_asset.py`
- Modify: `backend/app/services/bootstrap.py`
- Test: `backend/tests/test_clusters.py`

- [ ] **Step 1: Write failing model/default tests**

Add tests that create a MySQL cluster without `ha_mode` and assert:

```python
assert response.get_json()["data"]["ha_mode"] == "none"
assert DatabaseCluster.query.get(cluster_id).ha_mode == "none"
assert "ha_switch_enabled" not in response.get_json()["data"]
```

Also create an in-memory `DatabaseCluster` and assert `to_dict()` exposes `ha_mode`.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
wsl -e bash -lc "cd '/mnt/d/个人项目空间/DBMS/backend' && .venv/bin/python -c 'import werkzeug,pytest; werkzeug.__version__=\"unknown\"; raise SystemExit(pytest.main([\"tests/test_clusters.py\",\"-q\"]))'"
```

Expected: FAIL because `ha_mode` is absent or `ha_switch_enabled` is still returned.

- [ ] **Step 3: Implement the model and additive migration**

In `DatabaseCluster` add:

```python
ha_mode = db.Column(db.String(16), nullable=False, default="none")
```

In `to_dict()` normalize unknown legacy values:

```python
ha_mode = str(self.ha_mode or "none").strip().lower()
if ha_mode not in {"none", "orc", "dbms"}:
    ha_mode = "none"
```

Return `"ha_mode": ha_mode` and remove `ha_switch_enabled` from the response.

In `ensure_backup_extra_columns()` add:

```python
if table_columns["db_clusters"] and "ha_mode" not in table_columns["db_clusters"]:
    statements.append(
        "ALTER TABLE db_clusters ADD COLUMN ha_mode VARCHAR(16) NOT NULL DEFAULT 'none'"
    )
```

Leave the old physical column untouched, but remove the model property so application code cannot accidentally use it.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the Task 1 command again.

Expected: all `test_clusters.py` tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/db_asset.py backend/app/services/bootstrap.py backend/tests/test_clusters.py
git commit -m "feat: add MySQL HA management mode"
```

### Task 2: Validate HA modes in cluster CRUD and MCP output

**Files:**
- Modify: `backend/app/api/routes/clusters.py`
- Modify: `backend/app/services/mcp_status.py`
- Test: `backend/tests/test_clusters.py`

- [ ] **Step 1: Write failing CRUD tests**

Add tests for:

```python
def test_mysql_cluster_accepts_valid_ha_modes(client):
    # create with "orc", patch to "dbms", assert both responses and DB rows

def test_cluster_rejects_invalid_ha_mode(client):
    # POST mysql with ha_mode="external" and expect HTTP 400
    # PATCH mysql with ha_mode="external" and expect HTTP 400

def test_non_mysql_cluster_forces_ha_mode_none(client):
    # POST mongodb with ha_mode="dbms" and expect returned/stored "none"
```

Add a direct `_cluster_data()` test or MCP service test asserting `ha_mode` is returned and `ha_switch_enabled` is absent.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
wsl -e bash -lc "cd '/mnt/d/个人项目空间/DBMS/backend' && .venv/bin/python -c 'import werkzeug,pytest; werkzeug.__version__=\"unknown\"; raise SystemExit(pytest.main([\"tests/test_clusters.py\",\"-q\"]))'"
```

Expected: invalid values are accepted or modes are not persisted.

- [ ] **Step 3: Add a single normalization boundary**

In `clusters.py` add:

```python
MYSQL_HA_MODES = {"none", "orc", "dbms"}


def _normalize_ha_mode(value, db_type: str):
    if db_type != "mysql":
        return "none"
    mode = str(value or "none").strip().lower()
    if mode not in MYSQL_HA_MODES:
        raise ValueError("ha_mode must be none, orc or dbms")
    return mode
```

Use it during create:

```python
try:
    ha_mode = _normalize_ha_mode(payload.get("ha_mode"), db_type)
except ValueError as exc:
    return error_response(str(exc), code=400)
```

Pass `ha_mode=ha_mode` to `DatabaseCluster`.

Use it during patch when `ha_mode` is present:

```python
try:
    cluster.ha_mode = _normalize_ha_mode(payload.get("ha_mode"), cluster.db_type)
except ValueError as exc:
    return error_response(str(exc), code=400)
```

Delete the `ha_switch_enabled` patch handling.

In `mcp_status.py`, replace:

```python
"ha_switch_enabled": bool(cluster.ha_switch_enabled),
```

with:

```python
"ha_mode": cluster.to_dict()["ha_mode"],
```

- [ ] **Step 4: Run tests and verify GREEN**

Run the Task 2 command again.

Expected: cluster and MCP mode tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/clusters.py backend/app/services/mcp_status.py backend/tests/test_clusters.py
git commit -m "feat: validate cluster HA management modes"
```

### Task 3: Enforce DBMS ownership at HA mutation endpoints

**Files:**
- Modify: `backend/app/api/routes/clusters.py`
- Create: `backend/tests/test_mysql_ha_mode.py`

- [ ] **Step 1: Write failing endpoint tests**

Create helper data with an admin user, a MySQL cluster, cluster permission, and JWT headers. Test both:

```python
@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("none", "not enabled for DBMS HA management"),
        ("orc", "managed by Orchestrator"),
    ],
)
def test_ha_switch_rejects_non_dbms_modes(client, mode, message):
    response = client.post(
        f"/api/v1/clusters/{cluster_id}/ha/switch",
        json={"switch_type": "normal", "target_instance_id": 1},
        headers=headers,
    )
    assert response.status_code == 400
    assert message in response.get_json()["message"]
```

Repeat the assertion for `/ha/switch/stream`.

For `dbms`, patch `_execute_ha_switch` and assert the ordinary endpoint reaches it. Do not execute real MySQL HA logic.

Add a topology test showing `/ha/topology` is not rejected solely because mode is `none` or `orc`; patch `build_cluster_topology` to return an empty topology.

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
wsl -e bash -lc "cd '/mnt/d/个人项目空间/DBMS/backend' && .venv/bin/python -c 'import werkzeug,pytest; werkzeug.__version__=\"unknown\"; raise SystemExit(pytest.main([\"tests/test_mysql_ha_mode.py\",\"-q\"]))'"
```

Expected: old boolean guard either errors or blocks topology incorrectly.

- [ ] **Step 3: Replace the boolean guard with ownership enforcement**

Replace `_ensure_ha_switch_enabled` with:

```python
def _ensure_dbms_ha_management(cluster: DatabaseCluster):
    mode = str(getattr(cluster, "ha_mode", None) or "none").strip().lower()
    if mode == "orc":
        raise RuntimeError(
            "cluster is managed by Orchestrator; DBMS HA intervention is not allowed"
        )
    if mode != "dbms":
        raise RuntimeError("cluster is not enabled for DBMS HA management")
```

Call this guard in both `/ha/switch` and `/ha/switch/stream`.

Remove the HA mode/enable guard from `/ha/topology`; retain MySQL type and query permission checks.

- [ ] **Step 4: Run tests and verify GREEN**

Run the Task 3 command again.

Expected: all new HA mode endpoint tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/routes/clusters.py backend/tests/test_mysql_ha_mode.py
git commit -m "feat: restrict HA mutations to DBMS-managed clusters"
```

### Task 4: Replace the cluster management switch with a mode selector

**Files:**
- Modify: `frontend/src/views/ClusterManageView.vue`

- [ ] **Step 1: Replace list presentation**

Replace the “HA切换” boolean tag column with an “HA管理模式” column using:

```vue
<el-tag :type="haModeTagType(scope.row.ha_mode)">
  {{ haModeLabel(scope.row.ha_mode) }}
</el-tag>
```

Add:

```javascript
const haModeOptions = [
  { label: "无", value: "none" },
  { label: "ORC", value: "orc" },
  { label: "DBMS", value: "dbms" },
];

function normalizeHaMode(value) {
  return ["none", "orc", "dbms"].includes(value) ? value : "none";
}

function haModeLabel(value) {
  return { none: "无", orc: "ORC 托管", dbms: "DBMS 托管" }[normalizeHaMode(value)];
}

function haModeTagType(value) {
  return { none: "info", orc: "warning", dbms: "success" }[normalizeHaMode(value)];
}
```

- [ ] **Step 2: Replace form state and payload**

Replace `ha_switch_enabled` with:

```javascript
ha_mode: "none",
```

Use an `el-select` in the MySQL form:

```vue
<el-form-item v-if="dbType === 'mysql'" label="HA管理模式">
  <el-select v-model="form.ha_mode" style="width: 100%">
    <el-option
      v-for="item in haModeOptions"
      :key="item.value"
      :label="item.label"
      :value="item.value"
    />
  </el-select>
</el-form-item>
```

Reset to `none`, load with `normalizeHaMode(row.ha_mode)`, and submit:

```javascript
ha_mode: dbType.value === "mysql" ? normalizeHaMode(form.ha_mode) : "none",
```

Remove every `ha_switch_enabled` reference.

- [ ] **Step 3: Compile the Vue component**

Run:

```powershell
C:\Users\WZMIN\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe -e "const fs=require('fs'); const {parse,compileScript,compileTemplate}=require('./frontend/node_modules/@vue/compiler-sfc'); const file='frontend/src/views/ClusterManageView.vue'; const s=fs.readFileSync(file,'utf8'); const r=parse(s,{filename:file}); if(r.errors.length) throw r.errors[0]; compileScript(r.descriptor,{id:file}); const out=compileTemplate({source:r.descriptor.template.content,filename:file,id:file}); if(out.errors.length) throw out.errors[0]; console.log(file+' ok');"
```

Expected: `ClusterManageView.vue ok`.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/ClusterManageView.vue
git commit -m "feat: configure MySQL HA management mode"
```

### Task 5: Make the MySQL HA page ownership-aware

**Files:**
- Modify: `frontend/src/views/MysqlConnectionManageView.vue`

- [ ] **Step 1: Add shared UI helpers**

Add:

```javascript
function normalizeHaMode(value) {
  return ["none", "orc", "dbms"].includes(value) ? value : "none";
}

function haModeLabel(value) {
  return { none: "无", orc: "ORC 托管", dbms: "DBMS 托管" }[normalizeHaMode(value)];
}

function haModeTagType(value) {
  return { none: "info", orc: "warning", dbms: "success" }[normalizeHaMode(value)];
}

function haModeHint(value) {
  const mode = normalizeHaMode(value);
  if (mode === "orc") return "该集群由 Orchestrator 托管，DBMS 不进行切换干预";
  if (mode === "none") return "该集群未配置 DBMS HA 管理";
  return "";
}
```

- [ ] **Step 2: Update list and topology presentation**

Add an HA mode tag column. Keep topology, check, and history actions available.

Render “高可用切换” only when:

```vue
v-if="normalizeHaMode(scope.row.ha_mode) === 'dbms'"
```

For non-DBMS modes render a disabled text/button with `haModeHint(scope.row.ha_mode)` as tooltip.

Replace the dialog’s old enable tag with:

```vue
<el-tag :type="haModeTagType(topologyCluster?.ha_mode)">
  {{ haModeLabel(topologyCluster?.ha_mode) }}
</el-tag>
```

Replace the old alert with an alert shown when mode is not `dbms`, using `haModeHint`.

- [ ] **Step 3: Harden client-side action checks**

In `switchActionDisabled` replace the boolean check with:

```javascript
if (normalizeHaMode(topologyCluster.value?.ha_mode) !== "dbms") {
  return true;
}
```

At the start of `openSwitchDialog` and `submitHaSwitch`, reject non-DBMS mode with `ElMessage.warning(haModeHint(...))`.

- [ ] **Step 4: Compile both touched Vue components and build**

Run:

```powershell
C:\Users\WZMIN\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe -e "const fs=require('fs'); const {parse,compileScript,compileTemplate}=require('./frontend/node_modules/@vue/compiler-sfc'); for(const file of ['frontend/src/views/ClusterManageView.vue','frontend/src/views/MysqlConnectionManageView.vue']){const s=fs.readFileSync(file,'utf8');const r=parse(s,{filename:file});if(r.errors.length)throw r.errors[0];compileScript(r.descriptor,{id:file});const out=compileTemplate({source:r.descriptor.template.content,filename:file,id:file});if(out.errors.length)throw out.errors[0];console.log(file+' ok');}"
```

Then:

```powershell
npm run build
```

from `frontend`.

Expected: both components compile and Vite build exits 0.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/MysqlConnectionManageView.vue
git commit -m "feat: show MySQL HA ownership in operations"
```

### Task 6: Final regression and contract scan

**Files:**
- Verify only

- [ ] **Step 1: Ensure no business code uses the old switch**

Run:

```powershell
rg -n "ha_switch_enabled" backend/app backend/tests frontend/src
```

Expected: no matches. The design documents may still mention the legacy field.

- [ ] **Step 2: Run focused backend tests**

Run:

```powershell
wsl -e bash -lc "cd '/mnt/d/个人项目空间/DBMS/backend' && .venv/bin/python -c 'import werkzeug,pytest; werkzeug.__version__=\"unknown\"; raise SystemExit(pytest.main([\"tests/test_clusters.py\",\"tests/test_mysql_ha_mode.py\",\"-q\"]))'"
```

Expected: all focused tests pass.

- [ ] **Step 3: Run the full backend suite**

Run:

```powershell
wsl -e bash -lc "cd '/mnt/d/个人项目空间/DBMS/backend' && .venv/bin/python -c 'import werkzeug,pytest; werkzeug.__version__=\"unknown\"; raise SystemExit(pytest.main([\"tests\",\"-q\"]))'"
```

Expected: all backend tests pass. If unrelated existing failures remain, record the exact test names and errors.

- [ ] **Step 4: Run frontend production build**

Run `npm run build` from `frontend`.

Expected: exit code 0.

- [ ] **Step 5: Review final diff**

Run:

```powershell
git status --short
git diff --check
git diff HEAD~5 -- backend/app backend/tests frontend/src
```

Verify that:

- Existing clusters default to `none`.
- ORC and none remain topology-readable.
- Only DBMS mode reaches mutation logic.
- No Orchestrator integration was accidentally introduced.

