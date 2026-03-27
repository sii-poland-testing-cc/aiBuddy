# Roadmap: AI Buddy — Multi-Tenant RBAC Platform

## Overview

This milestone grafts a three-tier organizational hierarchy (Organization → Workspace → Project) and a scoped Role-Based Access Control system onto the existing AI Buddy platform. The existing "Project" entity is unchanged — two new tables are added above it. The build order is fully determined by hard dependencies: hierarchy schema first, then JWT authentication and the permission resolver (built independently), then route guards wired onto all existing endpoints, then the role assignment API, then DB-driven permissions, and finally observability and advanced features. Every phase keeps all existing tests passing (ENFORCE_AUTH=false in test env).

## Phases

- [ ] **Phase 1: DB Foundation** - Add organizations + workspaces tables; add organization_id and workspace_id FKs to projects; seed existing data; all existing tests pass
- [ ] **Phase 2: Authentication** - Users table, register/login/logout/me endpoints, JWT in httpOnly cookie, ENFORCE_AUTH flag, frontend login/register pages
- [ ] **Phase 3: RBAC Core** - Permission resolver with inheritance + memoization, require_permission() Depends wired on all existing routes, IDOR protection, SSE guards
- [ ] **Phase 4: Role Assignment API** - Assign/revoke user roles per resource, list members, superadmin bootstrap endpoint
- [ ] **Phase 5: DB-Driven Permissions** - permissions + role_permissions tables, can_user() upgraded to DB-driven, default mappings seeded
- [ ] **Phase 6: Observability and Advanced** - Audit log, role management UI, custom roles per org, ABAC creator_id, multi-tenant DB isolation

## Phase Details

### Phase 1: DB Foundation
**Goal**: The hierarchy schema exists in the database with all existing data migrated and all existing tests still passing.
**Depends on**: Nothing (first phase)
**Requirements**: HIER-01, HIER-02, HIER-03, HIER-04
**Success Criteria** (what must be TRUE):
  1. `organizations`, `workspaces` tables exist in the DB with proper FK constraints and indexes
  2. `projects` table has `organization_id` (NOT NULL FK → organizations) and `workspace_id` (nullable FK → workspaces)
  3. All existing project rows are seeded into a default organization; workspace_id left null
  4. `alembic upgrade head` runs cleanly from scratch and `alembic check` shows no drift
  5. All existing backend pytest tests pass with ENFORCE_AUTH=false after migration
**Plans:** 1/2 plans executed
Plans:
- [x] 01-01-PLAN.md — ORM models (Organization, Workspace) + Project FK columns + config fix
- [ ] 01-02-PLAN.md — Alembic migration 005 + conftest fixture + hierarchy tests

### Phase 2: Authentication
**Goal**: Users can register and log in; every API call carries a verified identity; existing functionality is unaffected when ENFORCE_AUTH=false.
**Depends on**: Phase 1
**Requirements**: AUTH-01, AUTH-02, AUTH-03, AUTH-04, AUTH-05, AUTH-06, AUTH-07, AUTH-08, AUTH-09, AUTH-10
**Success Criteria** (what must be TRUE):
  1. User can register with email and password via POST /api/auth/register and receive a 201 response
  2. User can log in via POST /api/auth/login and receive a JWT stored in an httpOnly cookie (not visible in response body)
  3. User can call GET /api/auth/me and receive their user info; unauthenticated call returns 401
  4. User can log out via POST /api/auth/logout and the cookie is cleared; subsequent /me returns 401
  5. Frontend login/register pages exist; unauthenticated users are redirected to /login; successful auth redirects to /
  6. All existing fetch calls include credentials: "include" for cookie transport
  7. All existing backend tests pass with ENFORCE_AUTH=false
**Plans**: TBD
**UI hint**: yes

### Phase 3: RBAC Core
**Goal**: Every existing API route is guarded — unauthenticated requests return 401, wrong-scope requests return 403, and SSE workflows cannot be triggered by unauthorized users.
**Depends on**: Phase 2
**Requirements**: RBAC-01, RBAC-02, RBAC-03, RBAC-04, RBAC-05, RBAC-06, RBAC-07, RBAC-08, RBAC-09
**Success Criteria** (what must be TRUE):
  1. A request to any existing route without a valid JWT cookie returns 401
  2. A request from a user with no role on the target project returns 403
  3. A project_viewer can read project data but cannot write or delete (403 on write attempts)
  4. An org_admin can access all projects under their org without an explicit project role assignment
  5. An SSE stream endpoint (context build, audit, requirements extract, mapping) returns 403 before the stream starts — no LLM tokens are consumed on a denied request
  6. User A cannot access User B's project by passing User B's project_id (IDOR protection returns 403)
  7. All existing backend tests pass with ENFORCE_AUTH=false
**Plans**: TBD

### Phase 4: Role Assignment API
**Goal**: Superadmins and org_admins can assign and revoke user roles through the API without direct DB access; the first superadmin can be bootstrapped on an empty system.
**Depends on**: Phase 3
**Requirements**: ROLE-01, ROLE-02, ROLE-03, ROLE-04
**Success Criteria** (what must be TRUE):
  1. Superadmin can assign a role to a user for any resource (org, workspace, or project) via POST /api/roles/assign
  2. Superadmin or org_admin can revoke a user's role for a resource via DELETE /api/roles/revoke
  3. Org_admin can list all members with roles on their organization via GET /api/roles/{resource_type}/{resource_id}/members
  4. POST /api/auth/bootstrap creates the first superadmin when the users table is empty; returns 409 if a superadmin already exists
  5. All existing backend tests pass with ENFORCE_AUTH=false
**Plans**: TBD

### Phase 5: DB-Driven Permissions
**Goal**: Role-to-permission mappings are stored in the database and can be inspected and modified without a code deploy; the resolver's external interface is unchanged.
**Depends on**: Phase 4
**Requirements**: PERM-01, PERM-02, PERM-03, PERM-04
**Success Criteria** (what must be TRUE):
  1. `permissions` and `role_permissions` tables exist with default mappings for all 3 built-in roles seeded
  2. `can_user()` now resolves permissions via DB query; hardcoded dict is removed
  3. The same permission tests from Phase 3 pass without any route changes (interface unchanged)
  4. Changing a role's permissions in the DB takes effect on the next request (no restart required)
  5. All existing backend tests pass with ENFORCE_AUTH=false
**Plans**: TBD

### Phase 6: Observability and Advanced
**Goal**: Admins can see a full audit trail of permission and role events, manage roles through a UI, and organizations can define custom roles; all DB queries are scoped by organization_id.
**Depends on**: Phase 5
**Requirements**: SCALE-01, SCALE-02, SCALE-03, SCALE-04, SCALE-05, ADV-01, ADV-02, ADV-03, ADV-04
**Success Criteria** (what must be TRUE):
  1. Every permission grant/deny and role assignment/revocation is recorded in the audit_log table
  2. Superadmin can retrieve a paginated, filterable audit log via GET /api/audit-log
  3. Org_admin can view org members and their roles and assign/revoke roles through the UI (no direct API call required)
  4. Org_admin can create a custom role with a custom name and permission mapping within their organization
  5. A user with a valid JWT for Org A receives 403 on any Org B resource regardless of the request method (multi-tenant isolation enforced at query level)
  6. Projects store creator_id; user can only edit projects they created (ABAC rule enforced)
**Plans**: TBD
**UI hint**: yes

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. DB Foundation | 1/2 | In Progress|  |
| 2. Authentication | 0/TBD | Not started | - |
| 3. RBAC Core | 0/TBD | Not started | - |
| 4. Role Assignment API | 0/TBD | Not started | - |
| 5. DB-Driven Permissions | 0/TBD | Not started | - |
| 6. Observability and Advanced | 0/TBD | Not started | - |
