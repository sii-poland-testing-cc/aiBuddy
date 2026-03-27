# Requirements: AI Buddy — Multi-Tenant RBAC Platform

**Defined:** 2026-03-27
**Core Value:** Any user who can reach a resource should have exactly the access their role allows — resolved through the Organization → Workspace → Project inheritance chain.

---

## Naming Convention

```
Organization   — top-level tenant boundary (a company or team)
  ├── Project  — project directly under an org (workspace omitted)
  └── Workspace  — optional grouping layer
        └── Project  — project grouped within a workspace
```

Workspace is **optional**. Every project must belong to an organization. Workspace is an optional grouping within that org.

**DB tables:**
- `organizations` (new)
- `workspaces` (new)
- `projects` (existing — gains `organization_id` FK required + `workspace_id` FK nullable)

**Permission inheritance:** Project role → Workspace role (skipped if project has no workspace) → Org role → superadmin

---

## v1 Requirements

### Hierarchy (New Tables, No Rename)

- [x] **HIER-01**: `organizations` table created (id UUID, name, owner_id FK → users, created_at)
- [x] **HIER-02**: `workspaces` table created (id UUID, organization_id FK → organizations, name, created_at)
- [x] **HIER-03**: `projects` table gains `organization_id` FK (required) and `workspace_id` FK (nullable → workspaces); existing rows seeded into a default organization; workspace_id left null by default
- [x] **HIER-04**: Alembic migration covers all schema changes with proper FK constraints and indexes; all existing tests still pass after migration

### Authentication

- [ ] **AUTH-01**: `users` table created (id UUID, email unique, hashed_password, created_at, is_superadmin bool)
- [ ] **AUTH-02**: `POST /api/auth/register` — email + password; password hashed with Argon2 via pwdlib; returns 201 with user id
- [ ] **AUTH-03**: `POST /api/auth/login` — validates credentials; returns JWT in httpOnly cookie (not response body)
- [ ] **AUTH-04**: `POST /api/auth/logout` — clears httpOnly cookie
- [ ] **AUTH-05**: `GET /api/auth/me` — returns current user info from JWT; 401 if not authenticated
- [ ] **AUTH-06**: JWT signed with `SECRET_KEY` from config; payload contains only `user_id` and `exp`; PyJWT library
- [ ] **AUTH-07**: `get_current_user()` FastAPI dependency resolves JWT from cookie; raises 401 if missing or invalid
- [ ] **AUTH-08**: `ENFORCE_AUTH` env flag (default `true`); when `false`, all routes bypass auth check (dev/test mode, preserves existing test suite)
- [ ] **AUTH-09**: Frontend login page (`/login`) and register page (`/register`); redirect to `/` on success; unauthenticated users redirected to `/login`
- [ ] **AUTH-10**: All existing frontend fetch calls updated with `credentials: "include"` for cookie transport

### RBAC Core (Hardcoded Permissions)

- [ ] **RBAC-01**: `roles` table seeded with: `org_admin`, `workspace_member`, `project_viewer`
- [ ] **RBAC-02**: `user_roles` table (user_id FK, role_id FK, resource_type ENUM: organization/workspace/project, resource_id UUID); composite index on `(user_id, resource_type, resource_id)`
- [ ] **RBAC-03**: `can_user(user_id, action, resource_type, resource_id)` function implementing inheritance: checks project role → workspace role (skipped if project has no workspace) → org role → superadmin flag
- [ ] **RBAC-04**: Request-scoped permission memoization (dict cache per request) to avoid repeated DB queries in SSE workflows
- [ ] **RBAC-05**: Hardcoded permission map: `org_admin` → all actions everywhere; `workspace_member` → read/write on workspace + all its projects; `project_viewer` → read-only on specific project
- [ ] **RBAC-06**: `require_permission(action, resource_type)` FastAPI `Depends()` callable wiring `can_user` onto every route; raises 403 on denial
- [ ] **RBAC-07**: All existing API routes guarded: projects, files, chat, context, snapshots, requirements, mapping routes require authentication + permission check
- [ ] **RBAC-08**: SSE route guards placed in `Depends` chain before the stream generator starts (cannot change HTTP status once streaming begins)
- [ ] **RBAC-09**: IDOR protection verified — `project_id` in route params checked against user's actual accessible resources, not just DB existence

### Role Assignment API

- [ ] **ROLE-01**: `POST /api/roles/assign` — superadmin assigns a role to a user for a resource (resource_type + resource_id); requires superadmin
- [ ] **ROLE-02**: `DELETE /api/roles/revoke` — removes a user's role for a resource; requires superadmin or org_admin on that org
- [ ] **ROLE-03**: `GET /api/roles/{resource_type}/{resource_id}/members` — list users with roles on a resource; requires org_admin on that resource
- [ ] **ROLE-04**: Superadmin bootstrap via `POST /api/auth/bootstrap` (callable once when user table is empty) or DB seed script

### Full RBAC — DB-Driven

- [ ] **PERM-01**: `permissions` table (id, action: read/write/delete/manage_users)
- [ ] **PERM-02**: `role_permissions` table (role_id FK, permission_id FK)
- [ ] **PERM-03**: `can_user()` resolver replaced with DB-driven permission lookup (role → permissions join); external interface unchanged — zero route changes required
- [ ] **PERM-04**: Default role-permission mappings seeded in migration for all 3 built-in roles

### Scaling & Observability

- [ ] **SCALE-01**: Audit log table (`audit_log`: id, user_id, action, resource_type, resource_id, timestamp, metadata JSON)
- [ ] **SCALE-02**: All permission grant/deny events written to audit log
- [ ] **SCALE-03**: Role assignment/revocation events written to audit log
- [ ] **SCALE-04**: `GET /api/audit-log` endpoint for superadmin — paginated, filterable by user/resource/action
- [ ] **SCALE-05**: Role management UI — view org members + roles, assign/revoke via UI (superadmin + org_admin)

### Advanced

- [ ] **ADV-01**: Custom role names per organization (org_admin can define new role names within their org)
- [ ] **ADV-02**: Custom role-permission mappings editable per org via API
- [ ] **ADV-03**: ABAC rule: "user can only edit projects they created" — `creator_id` column on projects, checked as additional condition in `can_user()`
- [ ] **ADV-04**: Multi-tenant isolation enforced at DB query level — all queries scoped by `organization_id`; no cross-org data leakage possible

---

## v2 Requirements

- **V2-01**: Redis-backed permission cache (replace request-scoped dict with distributed cache for multi-process deployments)
- **V2-02**: OAuth / SSO login (SAML, Google Workspace)
- **V2-03**: Email invite flow — org_admin invites user by email; one-time token
- **V2-04**: JWT refresh tokens
- **V2-05**: Webhook notifications on role changes

---

## Out of Scope

| Feature | Reason |
|---------|--------|
| Entity rename (Project → App/Application) | Kept as "Project" — zero rename cost, hierarchy names go upward |
| Public self-service signup | Internal tooling — orgs provisioned by admins |
| OAuth / social login | Email/password sufficient for v1 |
| Separate RBAC microservice | In-process is simpler for internal tooling |
| Row-level security (PostgreSQL RLS) | Application-level RBAC is sufficient |
| Refresh tokens (Phase 1) | Session length acceptable for internal tool |
| Email verification on register | Internal tool — trust the email |

---

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| HIER-01 | Phase 1 | Complete |
| HIER-02 | Phase 1 | Complete |
| HIER-03 | Phase 1 | Complete |
| HIER-04 | Phase 1 | Complete |
| AUTH-01 | Phase 2 | Pending |
| AUTH-02 | Phase 2 | Pending |
| AUTH-03 | Phase 2 | Pending |
| AUTH-04 | Phase 2 | Pending |
| AUTH-05 | Phase 2 | Pending |
| AUTH-06 | Phase 2 | Pending |
| AUTH-07 | Phase 2 | Pending |
| AUTH-08 | Phase 2 | Pending |
| AUTH-09 | Phase 2 | Pending |
| AUTH-10 | Phase 2 | Pending |
| RBAC-01 | Phase 3 | Pending |
| RBAC-02 | Phase 3 | Pending |
| RBAC-03 | Phase 3 | Pending |
| RBAC-04 | Phase 3 | Pending |
| RBAC-05 | Phase 3 | Pending |
| RBAC-06 | Phase 3 | Pending |
| RBAC-07 | Phase 3 | Pending |
| RBAC-08 | Phase 3 | Pending |
| RBAC-09 | Phase 3 | Pending |
| ROLE-01 | Phase 4 | Pending |
| ROLE-02 | Phase 4 | Pending |
| ROLE-03 | Phase 4 | Pending |
| ROLE-04 | Phase 4 | Pending |
| PERM-01 | Phase 5 | Pending |
| PERM-02 | Phase 5 | Pending |
| PERM-03 | Phase 5 | Pending |
| PERM-04 | Phase 5 | Pending |
| SCALE-01 | Phase 6 | Pending |
| SCALE-02 | Phase 6 | Pending |
| SCALE-03 | Phase 6 | Pending |
| SCALE-04 | Phase 6 | Pending |
| SCALE-05 | Phase 6 | Pending |
| ADV-01 | Phase 6 | Pending |
| ADV-02 | Phase 6 | Pending |
| ADV-03 | Phase 6 | Pending |
| ADV-04 | Phase 6 | Pending |

**Coverage:**
- v1 requirements: 40 total
- Mapped to phases: 40
- Unmapped: 0

---
*Requirements defined: 2026-03-27*
*Last updated: 2026-03-27 — traceability table expanded to per-requirement rows; ROLE-01..04 moved to Phase 4, PERM to Phase 5, SCALE+ADV to Phase 6*
