# Physical Host Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add read-only, batched vCenter physical-host discovery for every database instance, with automatic mode enabled by default for new and existing instances.

**Architecture:** Persist global settings, vCenter endpoints, and run/detail history in dedicated models. A narrow read-only vCenter client returns normalized VM/host facts; an orchestrator routes instance IPs by non-overlapping CIDRs, queries each vCenter once and serially, then updates only successful automatic-mode instances. APScheduler invokes the same guarded orchestration used by manual runs.

**Tech Stack:** Flask, Flask-SQLAlchemy, APScheduler, pyVmomi, pytest, Vue 3, Element Plus, Vite.

---

### Task 1: Domain models and default-auto instance contract

**Files:**
- Create: `backend/app/models/physical_discovery.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/db_asset.py`
- Modify: `backend/app/services/instance_service.py`
- Test: `backend/tests/test_physical_discovery.py`

- [ ] Write failing tests proving missing/invalid `physical_discovery_mode` serializes as `auto`, explicit `manual` remains manual, and existing `physical_address` remains untouched.
- [ ] Run `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_physical_discovery.py -v`; expect failures because the models and default-auto normalization do not exist.
- [ ] Add `PhysicalDiscoveryConfig`, `VCenterConfig`, `PhysicalDiscoveryRun`, and `PhysicalDiscoveryDetail` with `to_dict()` methods that mask credentials. Normalize instance extra data with:

```python
mode = str(extra.get("physical_discovery_mode") or "auto").lower()
extra["physical_discovery_mode"] = mode if mode in {"auto", "manual"} else "auto"
```

- [ ] Register models and make create/update preserve an existing address while defaulting mode to `auto`.
- [ ] Re-run the focused test; expect PASS, then commit model changes.

### Task 2: CIDR validation and configuration service/API

**Files:**
- Create: `backend/app/services/physical_discovery_config.py`
- Create: `backend/app/api/routes/physical_discovery.py`
- Modify: `backend/app/api/__init__.py`
- Modify: `backend/app/api/routes/user_permissions.py`
- Test: `backend/tests/test_physical_discovery.py`

- [ ] Add failing tests for CIDR normalization, global overlap rejection, endpoint uniqueness, password encryption/masking, global settings validation, and permission-menu exposure.
- [ ] Run focused tests and confirm expected missing-service/API failures.
- [ ] Implement `normalize_cidrs()`, `validate_non_overlapping_cidrs()`, CRUD endpoints, global settings endpoints, enable/disable, and masked password updates using existing `encrypt_secret`/`decrypt_secret`.
- [ ] Re-run tests; expect PASS, then commit configuration/API changes.

### Task 3: Read-only vCenter adapter and fact normalization

**Files:**
- Create: `backend/app/services/vcenter_readonly.py`
- Modify: `backend/requirements.txt`
- Test: `backend/tests/test_vcenter_readonly.py`

- [ ] Add failing tests for VM IP extraction, vSAN result `vSAN`, Management VMkernel IP selection, missing management IP failure, session disconnect in `finally`, and an allowed-call trace containing only connect/query/disconnect.
- [ ] Run focused tests and confirm failures because the adapter is missing.
- [ ] Add `pyvmomi` and implement a minimal interface:

```python
class ReadOnlyVCenterClient:
    def query_vm_host_facts(self) -> list[dict]: ...
    def close(self) -> None: ...
```

The production adapter may only call SmartConnect, PropertyCollector/container-view reads, and Disconnect. It must not expose mutation methods.
- [ ] Re-run focused tests; expect PASS, then commit adapter changes.

### Task 4: Batched orchestration, history, and failure preservation

**Files:**
- Create: `backend/app/services/physical_discovery.py`
- Modify: `backend/app/api/routes/physical_discovery.py`
- Test: `backend/tests/test_physical_discovery.py`

- [ ] Add failing tests for IP source preference, unique CIDR routing, unmatched-IP detail, one session/query per vCenter, serial vCenter order, manual-instance exclusion, successful auto update, vSAN update, failed lookup preserving old address, partial-success run status, and re-entry rejection.
- [ ] Run focused tests and confirm behavioral failures.
- [ ] Implement `run_discovery(vcenter_id=None, trigger_type="scheduled", client_factory=...)` with a process lock, per-vCenter serial batching, short update transactions, run/detail counters, sanitized errors, and `finally` cleanup.
- [ ] Add manual-run endpoint returning HTTP 202 with the created run ID and background execution.
- [ ] Re-run focused tests; expect PASS, then commit orchestration changes.

### Task 5: Scheduler and schema compatibility

**Files:**
- Modify: `backend/app/tasks/scheduler.py`
- Modify: `backend/app/services/bootstrap.py`
- Modify: `backend/app/__init__.py`
- Test: `backend/tests/test_physical_discovery.py`

- [ ] Add failing tests showing the job is absent when globally disabled, recreated with the configured interval when enabled, uses `max_instances=1/coalesce=True`, and calls the shared orchestrator.
- [ ] Run focused tests and verify expected failures.
- [ ] Implement `sync_physical_discovery_job()` plus `job_physical_discovery()`, invoke sync at scheduler registration and config updates, and ensure legacy databases create/upgrade required tables/columns without clearing existing physical addresses.
- [ ] Re-run focused tests; expect PASS, then commit scheduler/schema changes.

### Task 6: Instance UI and discovery-management page

**Files:**
- Create: `frontend/src/api/modules/physical_discovery.js`
- Create: `frontend/src/views/PhysicalDiscoveryManageView.vue`
- Modify: `frontend/src/views/InstanceManageView.vue`
- Modify: `frontend/src/router/index.js`
- Modify: `frontend/src/layouts/MainLayout.vue`
- Test: `frontend/src/utils/physicalDiscovery.test.js`
- Create: `frontend/src/utils/physicalDiscovery.js`

- [ ] Add failing frontend unit tests for default-auto normalization, manual editability, and run-status presentation.
- [ ] Run `npm test -- --run src/utils/physicalDiscovery.test.js`; confirm failures.
- [ ] Implement API functions and the configuration page with global controls, vCenter CRUD/test/enable/run actions, and paginated run/failure details.
- [ ] Add the permission-aware route/menu and modify instance editing so `auto` is the default and makes physical address read-only while `manual` enables editing.
- [ ] Re-run unit tests and `npm run build`; expect both PASS, then commit frontend changes.

### Task 7: Full verification and documentation alignment

**Files:**
- Modify: `docs/superpowers/specs/2026-07-06-physical-host-discovery-design.md`
- Modify: `docs/api-spec.md`

- [ ] Update the design spec to state that new and existing instances default to `auto`; document endpoints and read-only vCenter requirements.
- [ ] Run `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_physical_discovery.py backend/tests/test_vcenter_readonly.py -v`; expect all focused tests PASS.
- [ ] Run `backend/.venv/Scripts/python.exe -m pytest backend/tests -q`; expect zero failures.
- [ ] Run `npm test -- --run` and `npm run build` in `frontend`; expect zero test failures and Vite exit code 0.
- [ ] Run `git diff --check` and inspect `git diff`; expect no whitespace errors, no credential exposure, and no vCenter mutation calls.
- [ ] Commit final documentation and verification adjustments.
