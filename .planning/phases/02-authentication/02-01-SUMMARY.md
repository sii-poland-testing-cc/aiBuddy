---
phase: 02-authentication
plan: 01
subsystem: auth
tags: [jwt, pyjwt, pwdlib, argon2, sqlalchemy, alembic, fastapi]

# Dependency graph
requires:
  - phase: 01-db-foundation
    provides: "Organization/Workspace ORM models + migration 005 (organizations table with owner_id column)"
provides:
  - "User ORM model (users table) with email/hashed_password/is_superadmin/created_at columns"
  - "Alembic migration 006 creating users table + fk_organizations_owner_id FK"
  - "core/auth.py: hash_password, verify_password, create_access_token, decode_access_token, get_current_user"
  - "ENFORCE_AUTH + JWT_TTL_SECONDS settings fields"
  - "PyJWT and pwdlib[argon2] installed"
affects: [02-02-authentication, 02-03-authentication, 03-rbac-core]

# Tech tracking
tech-stack:
  added:
    - "pyjwt>=2.9.0 — JWT encode/decode with HS256"
    - "pwdlib[argon2]>=0.3.0 — password hashing with Argon2"
    - "argon2-cffi (transitive dep of pwdlib)"
  patterns:
    - "JWT payload minimal: only user_id + exp claims (no roles, no email in token)"
    - "httpOnly cookie named access_token for JWT transport"
    - "ENFORCE_AUTH=false returns AnonymousUser dataclass (dev/test bypass)"
    - "auth_models.py side-effect imported in engine.py and migrations/env.py"

key-files:
  created:
    - "backend/app/db/auth_models.py — User ORM model"
    - "backend/app/core/auth.py — JWT + password + get_current_user dependency"
    - "backend/migrations/versions/006_add_users_table.py — users table + owner_id FK"
  modified:
    - "backend/app/db/engine.py — added auth_models side-effect import"
    - "backend/migrations/env.py — added auth_models side-effect import"
    - "backend/app/core/config.py — added ENFORCE_AUTH and JWT_TTL_SECONDS"
    - "backend/tests/conftest.py — added ENFORCE_AUTH=false env override"
    - "backend/pyproject.toml — added pyjwt and pwdlib dependencies"

key-decisions:
  - "JWT payload contains only user_id + exp (no roles/email) — roles resolved per-request in Phase 3"
  - "AnonymousUser dataclass (not None) returned when ENFORCE_AUTH=false — callers can always access .id/.email/.is_superadmin"
  - "migration 006 down_revision=005 — users table created before FK added to organizations.owner_id"
  - "Worktree was 8 commits behind feature/multitenat-rbac-phase2; merged Phase 01 changes before executing Phase 02"

patterns-established:
  - "Auth dependency: import get_current_user from app.core.auth; add to route as Depends(get_current_user)"
  - "Anonymous bypass: ENFORCE_AUTH env var; tests set os.environ.setdefault('ENFORCE_AUTH', 'false') in conftest.py"

requirements-completed: [AUTH-01, AUTH-06, AUTH-07, AUTH-08]

# Metrics
duration: 5min
completed: 2026-03-28
---

# Phase 2 Plan 01: Authentication DB Foundation Summary

**User ORM with Argon2 password hashing, PyJWT HS256 tokens, httpOnly-cookie FastAPI dependency, and Alembic migration 006 adding users table + organizations.owner_id FK**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-28T09:30:38Z
- **Completed:** 2026-03-28T09:36:11Z
- **Tasks:** 2
- **Files modified:** 7 modified, 3 created

## Accomplishments

- User ORM model (`class User(Base)`) with email (unique+indexed), hashed_password, is_superadmin, created_at columns
- Migration 006: creates users table, ix_users_email index, and fk_organizations_owner_id FK (organizations.owner_id → users.id SET NULL)
- core/auth.py with all five required exports: hash_password, verify_password, create_access_token, decode_access_token, get_current_user
- PyJWT 2.12.1 and pwdlib 0.3.0 (Argon2) installed via PDM; all existing tests continue to pass with ENFORCE_AUTH=false

## Task Commits

Each task was committed atomically:

1. **Task 1: User ORM model, migration 006, install deps** - `79a0d3a` (feat)
2. **Task 2: core/auth.py with JWT helpers and get_current_user** - `a151865` (feat)

## Files Created/Modified

- `backend/app/db/auth_models.py` — User SQLAlchemy 2.0 ORM model (users table)
- `backend/migrations/versions/006_add_users_table.py` — Alembic migration 006 (users + owner_id FK)
- `backend/app/core/auth.py` — JWT encode/decode, Argon2 hash/verify, get_current_user FastAPI dep
- `backend/app/db/engine.py` — side-effect import for auth_models
- `backend/migrations/env.py` — side-effect import for auth_models (Alembic autogenerate)
- `backend/app/core/config.py` — ENFORCE_AUTH: bool = True + JWT_TTL_SECONDS: int = 86400
- `backend/tests/conftest.py` — ENFORCE_AUTH=false env override added
- `backend/pyproject.toml` + `backend/pdm.lock` — pyjwt and pwdlib[argon2] dependencies

## Decisions Made

- JWT payload is minimal: only `user_id` and `exp` (no roles, no email embedded). Roles are resolved per-request from DB in Phase 3.
- `AnonymousUser` is a dataclass (not None) when ENFORCE_AUTH=false — callers can safely access `.id`, `.email`, `.is_superadmin` without None checks.
- Migration order: users table created first, then FK from organizations.owner_id added (prevents FK referencing non-existent table).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Worktree was 8 commits behind source branch**
- **Found during:** Initial setup (before Task 1)
- **Issue:** The worktree `worktree-agent-ada14109` was checked out at commit `7ba8e89` (before Phase 01 work). Migration 005 and hierarchy_models.py (prerequisites for migration 006) were missing.
- **Fix:** Ran `git merge feature/multitenat-rbac-phase2 --no-edit` (fast-forward merge) to bring in all Phase 01 changes.
- **Files modified:** All Phase 01 files (hierarchy_models.py, migration 005, updated conftest, etc.)
- **Verification:** Migration 005 present, hierarchy tests pass (5/5)
- **Committed in:** Fast-forward merge (no separate commit needed)

---

**Total deviations:** 1 auto-fixed (1 blocking — missing prerequisite commits)
**Impact on plan:** Necessary to bring worktree up to date before Phase 02 could proceed. No scope creep.

## Issues Encountered

- PyJWT emits `InsecureKeyLengthWarning` when key is below 32 bytes (default "change-me-in-production" is 23 bytes). This is expected behavior in dev/test; production deployments must set a proper JWT_SECRET via env var.

## Known Stubs

None — all functionality is wired with real implementations (not hardcoded/placeholder returns).

## Next Phase Readiness

- Plan 02-02 (auth routes: register, login, logout, /me) can now import `get_current_user`, `create_access_token`, `hash_password`, `verify_password` from `app.core.auth`
- `User` model available for DB operations in routes
- Migration 006 ready to apply (`alembic upgrade head`)
- All existing tests pass with ENFORCE_AUTH=false

---
*Phase: 02-authentication*
*Completed: 2026-03-28*

## Self-Check: PASSED

- FOUND: backend/app/db/auth_models.py
- FOUND: backend/app/core/auth.py
- FOUND: backend/migrations/versions/006_add_users_table.py
- FOUND: commit 79a0d3a (Task 1)
- FOUND: commit a151865 (Task 2)
- FOUND: commit bbe438e (docs/metadata)
