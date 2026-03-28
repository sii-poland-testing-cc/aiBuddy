---
phase: 02-authentication
plan: 02
subsystem: auth
tags: [fastapi, jwt, pyjwt, pwdlib, argon2, httponly-cookie, sqlalchemy, pytest]

# Dependency graph
requires:
  - phase: 02-authentication
    plan: 01
    provides: "core/auth.py (hash_password, verify_password, create_access_token, decode_access_token, get_current_user, AnonymousUser), User ORM model, migration 006"
provides:
  - "POST /api/auth/register — creates user with Argon2 hash, returns 201 {id, email}; 409 on duplicate"
  - "POST /api/auth/login — validates credentials, sets httpOnly samesite=lax access_token cookie; 401 on bad creds"
  - "POST /api/auth/logout — clears access_token cookie via delete_cookie"
  - "GET /api/auth/me — returns {id, email, is_superadmin} via get_current_user dep; 401 when ENFORCE_AUTH=true and unauthenticated"
  - "backend/app/api/routes/auth.py with APIRouter export"
  - "main.py wired: auth router at /api/auth prefix"
  - "backend/tests/test_auth.py with 13 tests covering AUTH-01 through AUTH-08"
affects: [02-03-authentication, 03-rbac-core]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "auth_enabled test fixture patches both config_mod.settings and auth_mod.settings to properly override ENFORCE_AUTH in tests"
    - "Cookie: httpOnly=True, samesite=lax, secure=True only when APP_ENV=production"
    - "response.delete_cookie(key='access_token', path='/') clears cookie on logout"

key-files:
  created:
    - "backend/app/api/routes/auth.py — 4 auth endpoints with RegisterRequest/LoginRequest/UserResponse Pydantic models"
    - "backend/tests/test_auth.py — 13 comprehensive auth tests with auth_enabled fixture"
  modified:
    - "backend/app/main.py — added auth router import and include_router at /api/auth"

key-decisions:
  - "auth_enabled fixture must patch auth_mod.settings directly (not only config_mod.settings) because `from app.core.config import settings` creates a local binding in auth.py that isn't updated by module-level reassignment"
  - "Merged worktree-agent-ada14109 branch (plan 01 work) before executing plan 02 — prerequisite files were not in this worktree"

patterns-established:
  - "Auth route pattern: import get_current_user from app.core.auth; add Depends(get_current_user) to protected endpoints"
  - "Settings override in tests: patch both config_mod.settings and the module's local binding"

requirements-completed: [AUTH-02, AUTH-03, AUTH-04, AUTH-05]

# Metrics
duration: 20min
completed: 2026-03-28
---

# Phase 2 Plan 02: Auth API Endpoints Summary

**Four FastAPI auth endpoints (register/login/logout/me) with httpOnly JWT cookie, wired into main.py, with 13 tests covering all AUTH-02 through AUTH-05 behaviors and ENFORCE_AUTH bypass**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-03-28T10:30:00Z
- **Completed:** 2026-03-28T10:50:00Z
- **Tasks:** 2
- **Files modified:** 1 modified, 2 created

## Accomplishments

- POST /api/auth/register: 201 with {id, email}, 409 on duplicate email, Argon2 password hashing via plan 01 helpers
- POST /api/auth/login: sets httpOnly samesite=lax access_token cookie (secure=True only in production), 401 on bad credentials
- POST /api/auth/logout: clears access_token cookie via response.delete_cookie
- GET /api/auth/me: returns {id, email, is_superadmin} via get_current_user dependency; 401 when ENFORCE_AUTH=true and no valid cookie; returns anonymous user when ENFORCE_AUTH=false
- main.py updated: auth router registered at /api/auth prefix before context router
- 13 passing tests covering all behaviors including settings override (auth_enabled fixture) and regression check

## Task Commits

Each task was committed atomically:

1. **Task 1: Create auth routes and wire into main.py** - `4362acd` (feat)
2. **Task 2: Write test_auth.py covering all auth endpoint behaviors** - `4bc515c` (test)

## Files Created/Modified

- `backend/app/api/routes/auth.py` — APIRouter with 4 endpoints; RegisterRequest/LoginRequest/RegisterResponse/UserResponse schemas; uses hash_password, verify_password, create_access_token, get_current_user from core/auth
- `backend/tests/test_auth.py` — 13 tests with auth_enabled fixture; covers AUTH-01 through AUTH-08; helper functions register_user/login_user; fresh TestClient for isolation tests
- `backend/app/main.py` — added `from app.api.routes import auth` import and `app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])` before context router

## Decisions Made

- **auth_enabled fixture design:** The fixture must patch `auth_mod.settings` in addition to `config_mod.settings`. In Python, `from app.core.config import settings` in `auth.py` binds `auth.settings` to the original settings object. Replacing `config_mod.settings` doesn't update that binding. The fix patches both references to ensure tests that enable auth actually see ENFORCE_AUTH=true.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Merged prerequisite plan 01 commits into this worktree**
- **Found during:** Initial setup
- **Issue:** `auth_models.py` and `core/auth.py` (created in plan 01) were missing from this worktree. It was checked out at a commit predating plan 01 work.
- **Fix:** Ran `git merge worktree-agent-ada14109 --no-edit` (fast-forward merge) to bring in all plan 01 changes.
- **Files modified:** All plan 01 artifacts (auth_models.py, core/auth.py, migration 006, hierarchy_models.py, etc.)
- **Verification:** auth.py and auth_models.py present, all 13 auth tests pass
- **Committed in:** Fast-forward merge (no separate commit needed)

**2. [Rule 1 - Bug] Fixed auth_enabled fixture settings propagation**
- **Found during:** Task 2 test execution
- **Issue:** 3 of 13 tests failed — `test_me_authenticated`, `test_me_unauthenticated`, `test_get_current_user_no_token`. The `auth_enabled` fixture set `ENFORCE_AUTH=true` and called `config_mod.settings = Settings()` but `auth.py` still saw the old ENFORCE_AUTH=false because it holds its own reference to the original settings object (via `from app.core.config import settings`).
- **Fix:** Extended the fixture to also patch `auth_mod.settings = new_settings` so auth.py uses the updated settings during test execution.
- **Files modified:** `backend/tests/test_auth.py`
- **Verification:** All 13 auth tests pass; auth_enabled fixture properly overrides ENFORCE_AUTH for test duration
- **Committed in:** `4bc515c` (test commit)

---

**Total deviations:** 2 auto-fixed (1 blocking — missing prerequisite commits, 1 bug — fixture settings propagation)
**Impact on plan:** Both auto-fixes necessary for tests to work correctly. No scope creep.

## Issues Encountered

- The InsecureKeyLengthWarning from PyJWT for the default "change-me-in-production" key (23 bytes < 32 minimum for SHA256) is expected behavior in dev/test. Production must set a proper JWT_SECRET via env var.

## Known Stubs

None — all endpoints implemented with real DB operations, real JWT tokens, and real Argon2 password hashing. No hardcoded or placeholder returns.

## Next Phase Readiness

- Plan 02-03 (frontend login/register pages) can now authenticate against POST /api/auth/login and read user state via GET /api/auth/me
- All fetch calls in frontend must use `credentials: "include"` for the httpOnly cookie to be sent automatically
- 13 auth tests pass; 36 regression tests pass (hierarchy + M1 context + snapshots)

## Self-Check: PASSED

- FOUND: backend/app/api/routes/auth.py
- FOUND: backend/tests/test_auth.py
- FOUND: .planning/phases/02-authentication/02-02-SUMMARY.md
- FOUND commit 4362acd: feat(02-authentication-02)
- FOUND commit 4bc515c: test(02-authentication-02)

---
*Phase: 02-authentication*
*Completed: 2026-03-28*
