---
phase: 1
slug: db-foundation
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-03-27
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | `backend/pytest.ini` or `backend/pyproject.toml` |
| **Quick run command** | `cd backend && python -m pytest tests/ -x -q` |
| **Full suite command** | `cd backend && python -m pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |
| **Prerequisite** | pytest must be installed: `pip install pytest pytest-asyncio httpx anyio` (see Plan 01-02, Task 2) |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python -m pytest tests/ -x -q`
- **After every plan wave:** Run `cd backend && python -m pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------|-------------------|--------|
| 01-01-T1 | 01-01 | 1 | HIER-01, HIER-02 | import | `cd backend && python -c "from app.db.hierarchy_models import Organization, Workspace, DEFAULT_ORG_ID; print('OK')"` | pending |
| 01-01-T2 | 01-01 | 1 | HIER-01, HIER-02 | import | `cd backend && python -c "from app.db.engine import Base; assert 'organizations' in Base.metadata.tables; assert 'workspaces' in Base.metadata.tables; print('OK')"` | pending |
| 01-02-T1 | 01-02 | 2 | HIER-03, HIER-04 | migration | `cd backend && python -c "import importlib.util; spec = importlib.util.spec_from_file_location('m005', 'migrations/versions/005_add_hierarchy_tables.py'); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); assert mod.revision == '005'; print('OK')"` | pending |
| 01-02-T2 | 01-02 | 2 | HIER-01..04 | unit | `cd backend && python -m pytest tests/test_hierarchy.py -x -v` | pending |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [ ] `pip install pytest pytest-asyncio httpx anyio` — pytest not present in `.venv` (handled by Plan 01-02, Task 2 prerequisite step)
- [ ] `backend/tests/conftest.py` — add autouse fixture to seed default org row in test DB (Plan 01-02, Task 2)
- [ ] `backend/app/core/config.py` — add `JWT_SECRET: str = "change-me"` forward-placeholder (Plan 01-01, Task 2)

*Existing pytest infrastructure covers the phase — Wave 0 is lightweight.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Fresh DB migration from scratch | HIER-04 | Requires clean DB state | Delete `data/ai_buddy.db`, run `alembic upgrade head`, verify no errors |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 gaps identified and assigned to plan tasks
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** ready
