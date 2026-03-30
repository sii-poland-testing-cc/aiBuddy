---
phase: 2
slug: authentication
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-28
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio (backend) / Vitest (frontend) |
| **Config file** | `backend/pytest.ini` |
| **Quick run command** | `cd backend && pytest tests/test_auth.py -v` |
| **Full suite command** | `cd backend && pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && pytest tests/test_auth.py -v`
- **After every plan wave:** Run `cd backend && pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green (backend + frontend)
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 0 | AUTH-01 | unit (DB) | `pytest tests/test_auth.py::test_users_table_exists -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 0 | AUTH-02 | integration | `pytest tests/test_auth.py::test_register_creates_user -x` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 0 | AUTH-02 | integration | `pytest tests/test_auth.py::test_register_duplicate_email -x` | ❌ W0 | ⬜ pending |
| 02-01-04 | 01 | 0 | AUTH-03 | integration | `pytest tests/test_auth.py::test_login_sets_cookie -x` | ❌ W0 | ⬜ pending |
| 02-01-05 | 01 | 0 | AUTH-03 | integration | `pytest tests/test_auth.py::test_login_wrong_password -x` | ❌ W0 | ⬜ pending |
| 02-01-06 | 01 | 0 | AUTH-04 | integration | `pytest tests/test_auth.py::test_logout_clears_cookie -x` | ❌ W0 | ⬜ pending |
| 02-01-07 | 01 | 0 | AUTH-05 | integration | `pytest tests/test_auth.py::test_me_authenticated -x` | ❌ W0 | ⬜ pending |
| 02-01-08 | 01 | 0 | AUTH-05 | integration | `pytest tests/test_auth.py::test_me_unauthenticated -x` | ❌ W0 | ⬜ pending |
| 02-01-09 | 01 | 0 | AUTH-06 | unit | `pytest tests/test_auth.py::test_jwt_payload_shape -x` | ❌ W0 | ⬜ pending |
| 02-01-10 | 01 | 0 | AUTH-07 | unit | `pytest tests/test_auth.py::test_get_current_user_no_token -x` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 1 | AUTH-08 | regression | `pytest tests/ -v --ignore=tests/test_auth.py` | ✅ existing | ⬜ pending |
| 02-02-02 | 02 | 1 | AUTH-10 | unit (frontend) | `cd frontend && npm test -- tests/apiFetch.test.ts` | ❌ W0 | ⬜ pending |
| 02-03-01 | 03 | 2 | AUTH-09 | manual | n/a — visual verification | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_auth.py` — stubs for AUTH-01 through AUTH-08 (register, login, logout, /me, JWT, get_current_user)
- [ ] `frontend/tests/apiFetch.test.ts` — covers AUTH-10 (credentials: include baked in)
- [ ] Add `os.environ.setdefault("ENFORCE_AUTH", "false")` to `backend/tests/conftest.py` (before any app imports)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Frontend login/register pages render correctly | AUTH-09 | Visual verification of UI pages | 1. Run `npm run dev`. 2. Navigate to `/login` — form with email+password+submit renders. 3. Navigate to `/register` — same. 4. Navigate to `/` without auth — redirects to `/login`. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
