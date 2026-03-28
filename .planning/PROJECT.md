# AI Buddy — Multi-Tenant RBAC Platform

## What This Is

AI Buddy is a QA Agent Platform for test suite audit and optimization. This milestone extends it with a full multi-tenant hierarchy (Organization → Workspace → Project) and a scoped Role-Based Access Control system, replacing the current flat anonymous project model with proper user identity, authentication, and permission enforcement.

The existing "Project" entity is **unchanged** — it stays as "Project". Two new hierarchy levels are added above it: Organization (top) and Workspace (middle). Access control is enforced at every level with hierarchical role inheritance.

## Core Value

Any user who can reach a resource should have exactly the access their role allows — no more, no less — resolved through the Organization → Workspace → Project inheritance chain.

## Requirements

### Validated

- ✓ Per-project RAG knowledge base from uploaded .docx/.pdf documents — existing
- ✓ M1 Context Builder pipeline (parse → embed → extract → review → assemble) — existing
- ✓ M2 Test Suite Analyzer (audit + optimize workflows, SSE streaming) — existing
- ✓ Faza 2 Requirements extraction from M1 RAG context — existing
- ✓ Faza 5+6 Semantic mapping + coverage scoring — existing
- ✓ Audit snapshot history with diff tracking (max 5 per project) — existing
- ✓ File upload and management (source_type: file/url/jira/confluence) — existing
- ✓ SQLite + Alembic migration-managed schema — existing
- ✓ Next.js unified project page (?mode=audit|context|requirements) — existing

### Active

#### Hierarchy (New Tables, No Rename) — Validated in Phase 01: db-foundation
- [x] Add `organizations` table (id UUID, name, owner_id FK → users)
- [x] Add `workspaces` table (id UUID, organization_id FK, name)
- [x] Add `workspace_id` FK to existing `projects` table; seed existing rows into a default workspace
- [x] Alembic migration with proper FK constraints, indexes, existing data seeding

#### Authentication — Validated in Phase 02: authentication
- [x] `users` table (id UUID, email unique, hashed_password, is_superadmin, created_at)
- [x] Email/password registration + login endpoints; JWT in httpOnly cookie (PyJWT + pwdlib/Argon2)
- [x] `get_current_user()` FastAPI Depends; `ENFORCE_AUTH` env flag for dev bypass
- [x] Frontend login/register pages; `credentials: "include"` on all fetch calls via `apiFetch` wrapper

#### RBAC Core (Hardcoded Permissions)
- [ ] `roles` table seeded with: `org_admin`, `workspace_member`, `project_viewer`
- [ ] `user_roles` table (user_id, role_id, resource_type, resource_id) with composite index
- [ ] `can_user(user_id, action, resource_type, resource_id)` with Project → Workspace → Org inheritance
- [ ] Request-scoped permission memoization (prevents N+1 in SSE workflows)
- [ ] `require_permission()` FastAPI Depends on every route; SSE guards placed before stream starts
- [ ] IDOR protection: project_id in params verified against user's accessible resources

#### Role Assignment API
- [ ] Assign/revoke user roles per resource (superadmin / org_admin)
- [ ] List members with roles on a resource
- [ ] Bootstrap endpoint for first superadmin creation

#### Full RBAC — DB-Driven
- [ ] `permissions` table (read/write/delete/manage_users)
- [ ] `role_permissions` table with default mappings for 3 built-in roles
- [ ] `can_user()` resolver upgraded to DB-driven; external interface unchanged

#### Scaling & Observability
- [ ] Audit log table + write on permission grant/deny and role changes
- [ ] Superadmin audit log endpoint (paginated, filterable)
- [ ] Role management UI (assign/revoke via UI)

#### Advanced
- [ ] Custom role names + permission mappings per organization
- [ ] ABAC: `creator_id` on projects — user can only edit projects they created
- [ ] Multi-tenant isolation at DB query level (all queries scoped by organization_id)

### Out of Scope

- Entity rename (Project → App/Application) — kept as "Project", hierarchy goes upward
- Public self-service signup — internal tooling, orgs provisioned by admins
- OAuth / social login — email/password sufficient for v1
- Separate RBAC microservice — in-process is simpler for internal tooling
- Refresh tokens in Phase 1 — session length acceptable for internal tool
- Email verification — internal tool, trust the email

## Context

**Existing codebase:** FastAPI (async) + Next.js 14 (App Router) + SQLite (dev) / PostgreSQL (prod). Alembic manages migrations. All DB models use SQLAlchemy 2.0 async Mapped API.

**No rename cost:** The existing `projects` table and all `/api/projects/` routes stay unchanged. The only schema change to the existing table is adding a `workspace_id` FK column. This is the lowest-risk migration possible.

**Auth gap:** No authentication currently exists. All endpoints are open. JWT middleware introduced via `ENFORCE_AUTH` env flag — defaults to `true` in production, `false` in dev/test to preserve existing test suite without modification.

**Internal tooling context:** Organizations are provisioned by a superadmin. No invite-by-email flow needed in Phase 1. Role assignment via API or admin UI.

**Hierarchy mapping:**
- Organization — top-level tenant boundary (a company or team); every project must belong to one
- Workspace — optional grouping within an org (a product area, a sprint, a test campaign); projects can exist directly under an org without a workspace
- Project — unchanged existing entity (an individual QA session with its own RAG context, test files, audit history)

**Permission inheritance:** Project role → Workspace role (skipped when project has no workspace) → Org role → superadmin

**Key library decisions (from research):**
- `PyJWT >= 2.9.0` — FastAPI official recommendation (python-jose has unmaintained CVE-bearing dep)
- `pwdlib[argon2]` — replaces passlib (unmaintained, incompatible with bcrypt 4.x)
- httpOnly cookie for JWT — not localStorage (XSS risk); requires `credentials: "include"` on all frontend fetches
- `Depends()` per route — not global middleware (middleware breaks SSE and can't read typed path params)
- No RBAC library — custom ~200-line resolver covers the 3-role scoped model cleanly

## Constraints

- **Tech stack**: FastAPI + Next.js — no new backend framework; RBAC built in-process
- **DB**: SQLite in dev, Alembic migrations for all schema changes
- **Auth**: JWT in httpOnly cookie; PyJWT + pwdlib/Argon2; no refresh tokens in Phase 1
- **Internal only**: No public registration; superadmin seeds orgs and workspaces
- **No rename**: Existing `projects` table, API routes, and frontend code untouched except adding `workspace_id`

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Keep "Project" name, add Workspace (optional) + Organization above | Zero rename cost; workspace optional so small teams skip the extra layer | — Pending |
| RBAC built into FastAPI (not microservice) | Internal tooling doesn't need service isolation | — Pending |
| Hardcoded permissions in Phase 1, DB-driven in Phase 2 | Ship working auth/RBAC fast, then make it flexible | — Pending |
| httpOnly cookie (not localStorage) for JWT | XSS protection; Next.js official guidance | — Pending |
| Depends() per route (not global middleware) | Middleware breaks SSE and can't read typed path params | — Pending |
| ENFORCE_AUTH env flag | Allows existing test suite to keep running during auth rollout | — Pending |
| Request-scoped memoization in Phase 1 (not Phase 3) | SSE workflows make permission N+1 a correctness issue, not just perf | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-03-27 — Phase 01 db-foundation complete: Organization/Workspace hierarchy tables live, migration 005 applied, 5 schema tests passing*
