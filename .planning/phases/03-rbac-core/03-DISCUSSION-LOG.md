# Phase 3: RBAC Core - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-28
**Phase:** 03-rbac-core
**Areas discussed:** Permission vocabulary, Bootstrap timing, Test strategy, require_permission() wiring

---

## Permission vocabulary

| Option | Description | Selected |
|--------|-------------|----------|
| read / write / delete | 3 actions. GET=read, POST/PATCH=write, DELETE=delete. Phase-5-compatible (manage_users added later). | ✓ |
| read / write / delete / manage_users | 4 actions — matches Phase 5 permissions table exactly. manage_users unused in Phase 3. | |

**User's choice:** read / write / delete (3-action vocab)
**Notes:** Simpler, forward-compatible. Phase 5 adds manage_users to the permissions table without changing Phase 3 action strings.

---

## Bootstrap timing

| Option | Description | Selected |
|--------|-------------|----------|
| Phase 3 — move it here | POST /api/auth/bootstrap in Phase 3. Superadmin seed on empty users table. Unblocks dev. | ✓ |
| Phase 4 — keep as planned | Bootstrap stays in Phase 4 alongside full role assignment API. | |

**User's choice:** Move bootstrap to Phase 3
**Notes:** Phase 3 locks all routes; without bootstrap, fresh-registered users hit 403 everywhere. Superadmin can then operate via ENFORCE_AUTH=false locally or seed roles directly until Phase 4.

---

## Test strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Unit + integration | test_rbac_unit.py (can_user() logic) + test_rbac_integration.py (HTTP, ENFORCE_AUTH=true) | ✓ |
| Integration only | HTTP tests only, can_user() internals tested indirectly | |
| Unit tests only | can_user() function only, no route-level testing | |

**User's choice:** Unit + integration (both files)
**Notes:** Unit tests cover inheritance chain logic and memoization directly. Integration tests verify 401/403/IDOR/SSE-guard at the HTTP level with ENFORCE_AUTH=true and seeded users+roles.

---

## require_permission() wiring

| Option | Description | Selected |
|--------|-------------|----------|
| Factory Depends per handler | require_permission() on each handler. current_user explicit in every signature. | |
| Router-level auth + per-route permission | router.dependencies=[Depends(get_current_user)]. require_permission() per handler only. | ✓ |

**User's choice:** Router-level auth + per-route permission
**Notes:** Cleaner handler signatures — no `current_user` param on every handler. FastAPI dependency cache ensures get_current_user runs once per request even referenced in both router.dependencies and inside require_permission().

Follow-up: Routes without project_id (list/create projects) guard at org scope.

| Option | Description | Selected |
|--------|-------------|----------|
| Org-scoped permission | require_permission('read'/'write', 'organization') on list/create routes | ✓ |
| Auth-only (no scope check) | Any authenticated user can list/create projects | |

**User's choice:** Org-scoped permission
**Notes:** Any org_admin or workspace_member can list/create projects. Scope enforcement at org level matches the hierarchy design.

---

## Claude's Discretion

- ORM file location: `rbac_models.py` (follow established file-per-concern pattern)
- `can_user()` module: `app.core.rbac` (new module, separate from auth)
- Memoization: `request.state.rbac_cache` dict
- Migration: single `007_add_rbac_tables.py`
- Error message wording for 401/403

## Deferred Ideas

None.
