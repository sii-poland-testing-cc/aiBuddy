# Project Research Summary

**Project:** AI Buddy — Multi-Tenant RBAC Extension
**Domain:** JWT authentication + hierarchical RBAC added to an existing FastAPI async + SQLAlchemy 2.0 application
**Researched:** 2026-03-27
**Confidence:** HIGH

## Executive Summary

AI Buddy currently has zero authentication — every endpoint is open. This milestone grafts a three-tier organizational hierarchy (Org → Project → App, where "App" is the renamed existing "Project" entity) onto the platform, then secures all existing M1/M2/Faza 2/5/6 routes with JWT-based identity and scoped RBAC. The work is an internal enterprise tooling addition, not a SaaS product: self-service registration, email invites, OAuth, refresh tokens, and MFA are all explicitly out of scope. The recommended approach is minimal-dependency (two new backend packages: `PyJWT` and `pwdlib[argon2]`), FastAPI-canonical (per-route `Depends()` guards, never global middleware), and phased (DB schema first, then auth primitives, then wire guards, then role management API).

The most important architectural decision is to keep RBAC in-process as a custom resolver (~200 lines) rather than reaching for `casbin`, `fastapi-permissions`, or `oso`. The 3-role model (org_admin, project_member, app_user) with downward inheritance is well within what a hand-rolled resolver handles cleanly. The resolver must be designed with request-scoped memoization from day one — not as a Phase 3 optimization — because the SSE streaming workflows make dozens of internal calls and unguarded N+1 auth queries will cause timeout failures before the first LLM token arrives.

The single highest-risk operation in this milestone is the DB rename of `projects` → `apps`. SQLite's `render_as_batch` mode, already in use, does not handle cross-table FK renames automatically. Every child table (5 of them) must be batch-migrated individually in dependency order, and Chroma collection names (currently tied to the entity name) must be migrated via a one-time Python script before the code rename lands. Treating this rename as a simple `op.rename_table` call will silently corrupt FK metadata and make all existing RAG indexes unreachable — a production-breaking, hard-to-diagnose failure.

---

## Key Findings

### Recommended Stack

Only two new backend packages are needed. The existing FastAPI, SQLAlchemy 2.0, Alembic, Pydantic, and aiosqlite stack already provides everything else required for JWT auth and RBAC. No new frontend packages are needed either — React Context (already used for `ProjectOperationsContext`) handles auth state, and `fetch` with `credentials: "include"` handles cookie-based token transport.

**Core technologies:**
- `PyJWT >= 2.9.0`: JWT encode/decode — official FastAPI replacement for the deprecated `python-jose`; HS256 with 256-bit secret from `SECRET_KEY` (already in `config.py`)
- `pwdlib[argon2] >= 0.2.0`: password hashing — official FastAPI replacement for the unmaintained `passlib`; Argon2 is the Password Hashing Competition winner
- `fastapi.security.OAuth2PasswordBearer` (already installed): token extraction from `Authorization: Bearer` header — no new package required
- `React Context` (built-in): frontend auth state — same pattern as existing `ProjectOperationsContext`; do not add NextAuth.js, Auth0, or Clerk
- `httpOnly` cookie storage: JWT token storage on the frontend — XSS-safe, mandated by Next.js official docs; requires adding `credentials: "include"` to all existing `fetch` calls

**Do not use:** `python-jose` (unmaintained, CVE-carrying transitive dep), `passlib` (last release 2022, broken with bcrypt 4.x), `fastapi-users` (takes over User model, incompatible with custom hierarchy), `casbin`/`oso`/`fastapi-permissions` (overkill for 3 hardcoded roles), `NextAuth.js` (OAuth-centric, fights custom FastAPI JWT backend).

See `STACK.md` for full dependency diff and version notes.

### Expected Features

RBAC is a mature 30-year-old domain. The feature set for internal tooling is well-bounded — the key insight from research is that many features that are table stakes for SaaS (email invites, password reset flows, OAuth, refresh tokens) are anti-features here.

**Must have (table stakes):**
- Email + password authentication with JWT access tokens — closes the zero-auth gap; every protected system requires identity
- Login/logout UI + token storage (httpOnly cookie) — users must be able to authenticate from the browser
- JWT guard on all API routes via `Depends(get_current_user)` — core security requirement; must not break SSE streaming
- `GET /api/auth/me` — frontend needs to resolve current user on page load
- Three-tier entity model: `organizations` → `projects` (new middle tier) → `apps` (renamed existing projects) — the hierarchy is the product
- Three built-in roles: `org_admin`, `project_member`, `app_user` — seeded via migration; no dynamic role creation in Phase 1
- `user_roles` table with `(user_id, role_id, resource_type, resource_id)` — scoped role assignments at any level
- Downward inheritance in `canUser()` resolver — org_admin implicitly accesses all child projects and apps
- Permission guards on all existing M1/M2/Faza 2/5/6 routes — wrong `project_id`/`app_id` returns 403
- Superadmin flag (`users.is_superadmin`) — bootstrap capability; no public registration
- Tenant isolation: Org A users cannot access Org B resources even with a valid JWT

**Should have (differentiators):**
- Audit log (`audit_events` table) — "who triggered this audit, when" is a real compliance question in QA tooling
- Role management UI — reduces reliance on direct DB access for admin operations; only org_admin sees it
- Request-scoped permission cache — prevents N+1 auth queries in SSE workflows (see Pitfall 5)
- Graceful 401/403 UX — explicit "You don't have access" messaging rather than JS crashes or blank screens
- App-level auto-assign on creation — creator gets `app_user` role on their new app automatically

**Defer to Phase 2+:**
- DB-driven `role_permissions` table (hardcoded dict ships first; table replaces it cleanly later)
- Redis permission cache (only needed at multi-worker scale; request-scoped dict is sufficient for Phase 1-2)
- Custom roles per org (Phase 4 only, if concrete demand is proven)

**Never build (anti-features for internal tooling):**
- Public self-service registration, email invites, password reset email flow, OAuth/social login, refresh tokens, JWT revocation/blacklist, MFA, SSO/SAML, fine-grained LLM output audit logging

See `FEATURES.md` for full feature dependency graph and MVP recommendation.

### Architecture Approach

RBAC is a cross-cutting concern implemented entirely within the existing backend via FastAPI's dependency injection system. It is not a separate service. The architecture isolates permission logic in three new files (`auth.py`, `permissions.py`, `auth_models.py`) while touching existing route files only in their function signatures — no business logic changes. The hierarchy resolver walks App → Project → Org → Superadmin with at most 4 targeted DB queries per request (not a full user_roles table scan).

**Major components:**
1. **JWT Verifier** (`backend/app/core/auth.py`) — `get_current_user()` dependency; decodes JWT, fetches User from DB; raises 401 if invalid or expired
2. **Permission Resolver** (`backend/app/core/permissions.py`) — `can_user(user_id, action, resource_type, resource_id)`; Phase 1 uses hardcoded `ROLE_PERMISSIONS` dict; walks inheritance chain with request-scoped memoization; raises 403 on denial
3. **Permission Guard factory** (`backend/app/core/permissions.py`) — `require_permission(action, resource_type, path_param)` returns a `Depends()` callable; injected into route signatures without touching route body logic
4. **Auth DB Models** (`backend/app/db/auth_models.py`) — `User`, `Role`, `UserRole` ORM models sharing the existing `Base`
5. **Hierarchy DB Models** (extended `backend/app/db/models.py`) — `Organization`, new `Project` (middle tier), renamed `App` (existing project entity)
6. **Frontend Auth** (`frontend/lib/useAuth.ts`, new) — token storage, login/logout, 401 → redirect to login; all existing hooks add `credentials: "include"` to fetch calls

The SSE streaming endpoints require special attention: permission checks must run in the `Depends()` chain before the stream generator starts. You cannot check permissions inside `async def event_stream()` because a 403 cannot be raised after `StreamingResponse` has been returned to the client.

Phase 2 upgrade path: replace `ROLE_PERMISSIONS[role_name]` dict lookup in the resolver with a DB query against `role_permissions` table. Everything else — the inheritance chain, the Depends() callables, all route signatures — stays identical. This is the key isolation benefit of the single-function design.

See `ARCHITECTURE.md` for full data model DDL, inheritance chain SQL, component boundary table, and integration change analysis.

### Critical Pitfalls

1. **SQLite FK corruption during `projects` → `apps` table rename** — `render_as_batch=True` only applies to the table being modified, not to referencing tables. `op.rename_table` will silently corrupt FK metadata in the 5 child tables (`project_files`, `audit_snapshots`, `requirements`, `requirement_tc_mappings`, `coverage_scores`). Prevention: write the rename as a sequence of individual `op.batch_alter_table` calls, one per child table in dependency order, followed by creating `apps` as a new table, copying data, and dropping `projects`. End the migration with `PRAGMA foreign_key_check`.

2. **Chroma collection names become unreachable after entity rename** — Chroma collections are named using the entity formerly called "project." After renaming the code to use "app," existing RAG indexes silently stop being found (`is_indexed()` returns False while `context_built_at` is non-null), causing `rag_ready: false` for all apps with prior M1 context. Prevention: run a one-time Python migration script that reads each existing collection, re-indexes under the new naming scheme, and deletes the old collection — this must happen in the same deployment step as the DB migration.

3. **The rename touches 5 surfaces beyond DB and routes** — SSE event payloads (`"project_id"` key in JSON), Pydantic response schemas (`ProjectOut.project_id` field), frontend routing (`/project/[projectId]`), file system path construction, and all 65+ backend test fixtures. A missed surface causes silent data loss (files to wrong path), frontend `undefined` IDs, or all tests failing with 404s before testing any logic. Prevention: enumerate all surfaces with `grep -r "project_id"` before starting; rename in a single atomic PR with full test run.

4. **IDOR vulnerability: JWT authentication is not authorization** — After auth is added, any authenticated user can pass any `app_id` in a request body and operate on it unless an explicit ownership check follows JWT validation. This affects `/api/chat/stream`, `/api/files/{project_id}/upload`, `/api/context/{project_id}/build`, and all Faza 2/5/6 routes. Prevention: always call `require_permission()` after `get_current_user()`, before any business logic. Write explicit cross-org access tests (User A tries to access User B's app_id — must return 403).

5. **SSE middleware body consumption causes 422 errors** — Any middleware that reads `await request.body()` or `await request.json()` to extract resource IDs consumes the body before the route's Pydantic model can parse it, causing a 422 validation error on every SSE endpoint. Prevention: use only `Depends(get_current_user)` per-route; never parse the request body in middleware for auth purposes.

6. **Permission resolver N+1 DB queries in SSE workflows** — Without request-scoped memoization, the 3-level hierarchy walk runs once per DB/Chroma call inside a workflow. A single `/api/chat/stream` triggers 20-50 internal calls, producing 60-150 auth DB queries. Prevention: design `can_user()` with a request-scoped memoization dict from day one — not as a Phase 3 optimization.

See `PITFALLS.md` for 13 pitfalls with full severity analysis, detection signs, and code-level prevention patterns.

---

## Implications for Roadmap

The build order is fully determined by hard dependencies. Nothing can be secured until JWT works. RBAC guards cannot be wired until the permission resolver exists. The permission resolver cannot run without the hierarchy tables. The hierarchy tables require the entity rename to be clean first.

### Phase 1: DB Foundation and Entity Rename

**Rationale:** Every subsequent phase depends on the schema. The rename must be done atomically and verified clean before any auth code is written — a broken rename discovered after auth is wired is extremely difficult to untangle.
**Delivers:** Clean `organizations`, `projects` (new middle tier), `apps` (renamed), `users`, `roles`, `user_roles` tables via Alembic migrations; seeded roles; PRAGMA foreign_key_check passing; Chroma collections migrated; all 5 child table FK references updated.
**Addresses:** Table stakes: three-tier entity model; built-in roles seeded; user model foundation.
**Avoids:** Pitfall 1 (SQLite FK corruption), Pitfall 2 (Chroma collection loss), Pitfall 3 (5-surface rename breakage), Pitfall 9 (Alembic env.py import gap for new auth models).
**Research flag:** No additional research needed — standard Alembic batch migration patterns are well-documented; the FK correction sequence is explicitly specified in PITFALLS.md.

### Phase 2: JWT Auth Primitives (2A) + Permission Resolver (2B) — Parallel

**Rationale:** These two components have no dependency on each other — only both depend on Phase 1 schema. They can be built in parallel. Neither touches any existing route yet, so no regression risk.
**2A Delivers:** `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`; `get_current_user()` Depends callable; PyJWT + pwdlib[argon2] installed; SECRET_KEY configured; frontend login page + token storage + 401 redirect.
**2B Delivers:** `can_user()` with hardcoded `ROLE_PERMISSIONS` dict and inheritance chain (App → Project → Org → Superadmin); request-scoped memoization dict; `require_permission()` factory; unit tests covering all role/scope combinations and cross-org denial.
**Addresses:** Table stakes: JWT access tokens, login/logout UI, current user endpoint, canUser() resolver with downward inheritance.
**Avoids:** Pitfall 5 (N+1 auth queries — memoization built in from the start), Pitfall 6 (global middleware — per-route Depends only), Pitfall 12 (token TTL — set to ≥ 2× M1 workflow timeout = 60+ min), Pitfall 13 (localStorage namespace by user_id).
**Research flag:** No additional research needed — PyJWT and pwdlib patterns are from official FastAPI docs; resolver design is specified in ARCHITECTURE.md.

### Phase 3: Wire Guards on All Existing Routes

**Rationale:** Depends on both 2A (get_current_user) and 2B (require_permission). This is the phase that actually closes the zero-auth security gap. Route signatures change; no route body logic changes.
**Delivers:** All M1/M2/Faza 2/5/6 routes return 401 without valid JWT and 403 with wrong scope. Auth is enforced. `_context_store` cache reads preceded by authorization check. LlamaIndex workflow entry points receive and verify app_id ownership.
**Addresses:** Table stakes: JWT middleware on all routes, permission guards on existing endpoints, tenant isolation.
**Avoids:** Pitfall 3 (IDOR — explicit ownership check after JWT validation), Pitfall 7 (_context_store cache bypass), Pitfall 8 (IDOR on request body project_id), Pitfall 10 (workflow internal calls bypassing auth).
**Research flag:** No additional research needed — the route modification pattern is mechanical; the pitfall catalogue covers all known edge cases.

### Phase 4: Role Assignment API

**Rationale:** Depends on Phase 3 (auth must exist to know who is assigning). Delivers the admin surface for actually managing role memberships without direct DB access.
**Delivers:** `POST/DELETE /api/orgs/{org_id}/members`, `POST/DELETE /api/projects/{project_id}/members`, `POST/DELETE /api/apps/{app_id}/members` — all guarded by `require_permission("manage_users", <resource_type>)`; superadmin org creation endpoint; auto-assign app_user to creator on app creation.
**Addresses:** Differentiator: role management API; app-level auto-assign on creation.
**Research flag:** No additional research needed — standard CRUD pattern following existing routes.

### Phase 5: DB-Driven Permissions + Role Management UI (Phase 2 features)

**Rationale:** Pure internal replacement of the hardcoded dict. No structural changes to the resolver, routes, or permissions system. The UI is a quality-of-life improvement for admins.
**Delivers:** `permissions` + `role_permissions` tables via Alembic migration seeded with defaults matching the Phase 1 hardcoded map; `can_user()` resolver switches to DB query; admin UI for role assignment (org_admin-only panel in UtilityPanel or dedicated `/admin` page); audit_events table.
**Addresses:** Differentiator: DB-driven permissions, role management UI, audit log.
**Research flag:** Audit log schema design may benefit from a quick research pass if specific compliance requirements emerge — the basic append-only table design is standard but event payload scope needs product input.

### Phase Ordering Rationale

- Phase 1 must be atomic and complete before anything else: a broken rename is catastrophic and compounds with every subsequent change.
- Phases 2A and 2B can be parallelized within a sprint — they have identical prerequisites (Phase 1) and no mutual dependency.
- Phase 3 is deliberately separated from Phase 2 to allow the auth primitives to be tested in isolation before any existing functionality is gated on them. An `ENFORCE_AUTH=false` env flag during transition prevents breaking working features while auth is being implemented.
- Phase 4 (role management API) is deferred from Phase 3 because Phase 3 already makes the system secure — Phase 4 improves operator ergonomics.
- Phase 5 (DB-driven permissions, UI) is deferred because the hardcoded dict fully serves 3 static roles. Moving to DB-driven only matters when custom roles per org become a requirement.

### Research Flags

Needs additional research during planning:
- **Phase 5 (audit log):** Event payload scope and retention policy need product-level input before schema design. Standard append-only table design is known, but what events to capture and for how long requires a decision.

Standard patterns (skip research-phase):
- **Phase 1:** Alembic batch migration for SQLite is a documented pattern; the FK correction sequence is fully specified in PITFALLS.md.
- **Phase 2A:** PyJWT + pwdlib usage is from current official FastAPI docs.
- **Phase 2B:** Custom RBAC resolver with inheritance is a 30-year-old pattern; the implementation is specified in ARCHITECTURE.md.
- **Phase 3:** Mechanical route signature changes; all edge cases catalogued in PITFALLS.md.
- **Phase 4:** Standard CRUD routes with guard patterns established in Phase 3.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | PyJWT and pwdlib recommendations verified directly against official FastAPI docs (fastapi.tiangolo.com, verified 2026-03-27). httpOnly cookie recommendation verified against official Next.js docs (nextjs.org/docs, v16.2.1, verified 2026-03-27). RBAC library verdicts are training-data-based ecosystem survey but corroborated by PROJECT.md constraints. |
| Features | HIGH | RBAC feature taxonomy is a mature, well-established domain. Internal vs. SaaS calibration is explicit in PROJECT.md. Feature dependency graph is fully derived; no ambiguity. |
| Architecture | HIGH | Based on direct analysis of the actual codebase (`models.py`, `config.py`, `routes/projects.py`, `main.py`, `engine.py`) plus FastAPI canonical dependency injection patterns. The data model and inheritance chain SQL are specified at implementation level. |
| Pitfalls | HIGH | Pitfalls 1–4 are grounded in direct codebase analysis (actual FK chain, actual Chroma naming code, actual route surfaces). Pitfalls 5–6 are grounded in actual workflow code (SSE streaming, LlamaIndex workflow calls). No pitfall is speculative. |

**Overall confidence:** HIGH

### Gaps to Address

- **pwdlib version on PyPI:** The version `>=0.2.0` is from training data; PyPI was inaccessible during research. Verify `pdm add "pwdlib[argon2]"` resolves to a current stable version before committing the dependency.
- **python-jose CVE specifics:** The recommendation to avoid it is confirmed by the official FastAPI docs dropping it; specific CVE numbers in the transitive `ecdsa` dependency were not verified via live fetch. The avoidance recommendation stands regardless.
- **`casbin` async support:** Assessed as "inconsistent with SQLAlchemy 2.0" based on training data. This verdict is correct for Phase 1 (3 static roles do not need casbin), but should be re-evaluated if Phase 5+ requires custom roles per org.
- **Audit log event payload scope:** What events to log and what fields to include requires product input. The table design (append-only `audit_events`) is standard; the scope is a product decision, not a technology decision.

---

## Sources

### Primary (HIGH confidence)
- FastAPI Security Tutorial (JWT): https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/ — verified 2026-03-27; PyJWT and pwdlib recommendations, dependency injection pattern
- Next.js Authentication Guide: https://nextjs.org/docs/app/guides/authentication — docs v16.2.1, verified 2026-03-27; httpOnly cookie recommendation
- Codebase — `backend/app/db/models.py`, `backend/migrations/versions/001_initial_schema.py`, `backend/migrations/env.py`, `backend/app/rag/context_builder.py`, `backend/app/api/routes/chat.py`, `backend/app/api/routes/projects.py`, `backend/app/core/config.py` — direct source analysis; entity FK chain, Chroma naming, SSE route pattern
- `.planning/PROJECT.md` — project requirements and constraints

### Secondary (MEDIUM confidence)
- FastAPI Middleware docs: https://fastapi.tiangolo.com/tutorial/middleware/ — verified 2026-03-27; Depends-over-middleware recommendation
- OWASP RBAC guidelines, NIST SP 800-162 — feature taxonomy calibration for internal tooling
- `.planning/codebase/CONCERNS.md` — existing tech debt and fragile areas

### Tertiary (training data, verify before use)
- `pwdlib >= 0.2.0` version on PyPI — confirm version with `pdm add "pwdlib[argon2]"` at install time
- `python-jose` CVE specifics in `ecdsa` transitive dependency — avoidance confirmed by official docs; CVE numbers not independently verified

---
*Research completed: 2026-03-27*
*Ready for roadmap: yes*
