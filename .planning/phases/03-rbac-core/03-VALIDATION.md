---
phase: 3
slug: rbac-core
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-30
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | `backend/pytest.ini` (existing) |
| **Quick run command** | `pytest tests/test_rbac_unit.py -v` |
| **Full suite command** | `pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_rbac_unit.py -v`
- **After every plan wave:** Run `pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 3-01-01 | 01 | 1 | RBAC-01, RBAC-02 | unit | `pytest tests/test_rbac_unit.py::test_roles_seeded tests/test_rbac_unit.py::test_user_roles_schema -x` | ❌ W0 | ⬜ pending |
| 3-01-02 | 01 | 1 | RBAC-03, RBAC-04, RBAC-05 | unit | `pytest tests/test_rbac_unit.py -x` | ❌ W0 | ⬜ pending |
| 3-02-01 | 02 | 1 | RBAC-06, RBAC-07 | integration | `pytest tests/test_rbac_integration.py::test_401_no_token tests/test_rbac_integration.py::test_403_no_role -x` | ❌ W0 | ⬜ pending |
| 3-02-02 | 02 | 1 | RBAC-08 | integration | `pytest tests/test_rbac_integration.py::test_sse_403_before_stream -x` | ❌ W0 | ⬜ pending |
| 3-02-03 | 02 | 1 | RBAC-09 | integration | `pytest tests/test_rbac_integration.py::test_idor_403 -x` | ❌ W0 | ⬜ pending |
| 3-02-04 | 02 | 2 | D-10 | integration | `pytest tests/test_rbac_integration.py::test_bootstrap_success tests/test_rbac_integration.py::test_bootstrap_409 -x` | ❌ W0 | ⬜ pending |
| 3-03-01 | 03 | 2 | RBAC-07 (regression) | regression | `pytest tests/ -v` | ✅ existing | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_rbac_unit.py` — stubs for RBAC-01 through RBAC-05: `test_roles_seeded`, `test_user_roles_schema`, `test_can_user_org_admin`, `test_can_user_hierarchy`, `test_memoization`, `test_project_viewer_deny_write`
- [ ] `tests/test_rbac_integration.py` — stubs for RBAC-06 through RBAC-09 + bootstrap: `test_401_no_token`, `test_403_no_role`, `test_sse_403_before_stream`, `test_idor_403`, `test_bootstrap_success`, `test_bootstrap_409`

*Existing infrastructure: pytest, conftest.py, app_client fixture — all in place from prior phases. No framework installation needed.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
