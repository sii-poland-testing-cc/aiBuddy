# Architecture Patterns: Scoped RBAC with Hierarchical Inheritance

**Domain:** Multi-tenant RBAC added to an existing FastAPI async + SQLAlchemy 2.0 app
**Researched:** 2026-03-27
**Overall confidence:** HIGH — based on direct codebase analysis + established FastAPI dependency injection patterns

---

## Recommended Architecture

### System Structure

The RBAC system sits as a cross-cutting concern across all layers. It is NOT a separate service — it is a set of FastAPI `Depends()` callables and a permission resolver function that any route can inject.

```
HTTP Request
     │
     ▼
┌──────────────────────────────────────────────────────────┐
│  JWT Middleware  (FastAPI Middleware or Depends chain)    │
│  • Decode token → extract user_id                        │
│  • Attach CurrentUser to request state                   │
└──────────────┬───────────────────────────────────────────┘
               │ user_id
               ▼
┌──────────────────────────────────────────────────────────┐
│  Permission Guard  (Depends(require_permission(...)))    │
│  • Calls PermissionResolver with (user_id, action,       │
│    resource_type, resource_id)                           │
│  • Raises HTTP 403 if access denied                      │
└──────────────┬───────────────────────────────────────────┘
               │ user + verified permission
               ▼
┌──────────────────────────────────────────────────────────┐
│  Route Handler  (existing routes, minimally modified)    │
│  • Receives db session + current_user as before          │
│  • No permission logic inside handlers                   │
└──────────────────────────────────────────────────────────┘
```

### Component Boundaries

| Component | Location | Responsibility | Communicates With |
|-----------|----------|---------------|-------------------|
| **JWT Issuer** | `backend/app/api/routes/auth.py` | `/register`, `/login` → issues JWT; `/me` returns current user | DB (User table), `jose`/`PyJWT` |
| **JWT Verifier** | `backend/app/core/auth.py` | `get_current_user()` dependency — decodes JWT, fetches User from DB | DB (User table), `jose`/`PyJWT` |
| **Permission Resolver** | `backend/app/core/permissions.py` | `can_user(user_id, action, resource_type, resource_id)` — runs inheritance chain | DB (UserRoles, Roles), in-request cache |
| **Permission Guard** | `backend/app/core/permissions.py` | `require_permission(action, resource_type)` — factory returning a `Depends()` callable | Permission Resolver, current_user |
| **Auth DB Models** | `backend/app/db/auth_models.py` | `User`, `Role`, `UserRole` ORM models | SQLAlchemy Base (shared with existing models) |
| **Hierarchy DB Models** | `backend/app/db/models.py` (extended) | `Organization`, `Project` (new), rename `Project`→`App` | Existing cascade FK chain |
| **RBAC Route Guards** | All existing route files | `Depends(require_permission(...))` injected into route signatures | Permission Guard |
| **Frontend Auth** | `frontend/lib/useAuth.ts` (new) | Token storage (localStorage), attach `Authorization: Bearer` header, redirect to login on 401 | All existing hooks |

### Data Model

```
organizations
  id (PK, UUID)
  name
  owner_id (FK → users.id)
  created_at

projects                          ← NEW middle tier
  id (PK, UUID)
  organization_id (FK → organizations.id, CASCADE)
  name
  created_at

apps                              ← renamed from "projects"
  id (PK, UUID)
  project_id (FK → projects.id, CASCADE)
  name, description, context_*, ...  ← all existing columns

users
  id (PK, UUID)
  email (UNIQUE, NOT NULL)
  hashed_password
  is_superadmin (Boolean, default False)
  created_at

roles
  id (PK, UUID)
  name (UNIQUE)  ← "org_admin" | "project_member" | "app_user"

user_roles
  id (PK, UUID)
  user_id (FK → users.id, CASCADE)
  role_id (FK → roles.id, CASCADE)
  resource_type  ← "org" | "project" | "app"
  resource_id    ← UUID of the org / project / app
  UNIQUE (user_id, role_id, resource_type, resource_id)

-- Phase 2 only:
permissions
  id (PK, UUID)
  action  ← "read" | "write" | "delete" | "manage_users"

role_permissions
  role_id (FK → roles.id, CASCADE)
  permission_id (FK → permissions.id, CASCADE)
  PRIMARY KEY (role_id, permission_id)
```

---

## Data Flow

### Authentication Flow (per request)

```
Client sends:  GET /api/apps/{app_id}
               Authorization: Bearer <jwt>

1. JWT Verifier (get_current_user):
   a. Decode JWT → user_id (jose.jwt.decode with SECRET_KEY)
   b. SELECT * FROM users WHERE id = user_id
   c. Return User ORM object (or raise 401 if missing/expired)

2. Permission Guard (require_permission("read", "app")):
   a. Extract resource_id from path param (app_id)
   b. Call can_user(user.id, "read", "app", app_id)
   c. Raise HTTP 403 if False

3. Route handler executes with verified user
```

### Permission Resolution — Inheritance Chain

The inheritance chain moves from narrow to broad: the resolver checks the most specific scope first and climbs the hierarchy until a granting role is found.

```
can_user(user_id, action, "app", app_id):

  Step 1 — Direct app-level role?
    SELECT ur.* FROM user_roles ur
    WHERE ur.user_id = :user_id
      AND ur.resource_type = 'app'
      AND ur.resource_id = :app_id
    → If role grants action → ALLOW

  Step 2 — Project-level role covers this app?
    SELECT a.project_id FROM apps WHERE id = :app_id  → project_id
    SELECT ur.* FROM user_roles ur
    WHERE ur.user_id = :user_id
      AND ur.resource_type = 'project'
      AND ur.resource_id = :project_id
    → If role grants action → ALLOW

  Step 3 — Org-level role covers this project?
    SELECT p.organization_id FROM projects WHERE id = :project_id  → org_id
    SELECT ur.* FROM user_roles ur
    WHERE ur.user_id = :user_id
      AND ur.resource_type = 'org'
      AND ur.resource_id = :org_id
    → If role grants action → ALLOW

  Step 4 — Superadmin?
    user.is_superadmin == True → ALLOW

  Else → DENY
```

The resolver requires at most 4 DB queries per request (3 hierarchy lookups + 1 user fetch). A request-scoped dict cache (keyed on `(user_id, action, resource_type, resource_id)`) reduces this to 0 additional queries for repeated checks within the same request (e.g. when a route calls multiple services that each check permission).

### Phase 1 Hardcoded Permission Map

```python
# backend/app/core/permissions.py

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "org_admin":       {"read", "write", "delete", "manage_users"},
    "project_member":  {"read", "write"},
    "app_user":        {"read"},
}

def _role_grants(role_name: str, action: str) -> bool:
    return action in ROLE_PERMISSIONS.get(role_name, set())
```

This dict is the only thing replaced in Phase 2 when `permissions` + `role_permissions` tables become the source of truth.

### Phase 2 DB-Driven Permission Resolution

```
SELECT p.action
FROM role_permissions rp
JOIN permissions p ON p.id = rp.permission_id
WHERE rp.role_id = :role_id
```

The resolver switches from `ROLE_PERMISSIONS[role_name]` to a DB query (or cached result). Everything else — the inheritance chain, the Depends() callables, the route signatures — stays identical. This is the key design advantage of isolating permission resolution in a single function.

### SSE Route Handling

SSE routes (`/api/context/{app_id}/build`, `/api/chat/stream`, etc.) use `StreamingResponse`. They cannot use FastAPI middleware in the standard sense because the response is already streaming. Permission checks must happen via `Depends()` in the route signature, before the stream starts — not inside the generator.

```python
@router.post("/{app_id}/build")
async def build_context(
    app_id: str,
    files: list[UploadFile],
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_permission("write", "app", path_param="app_id")),
    db: AsyncSession = Depends(get_db),
):
    # Stream starts only after Depends chain completes (auth + permission verified)
    async def event_stream():
        ...
    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

---

## Suggested Build Order

Order is dictated by hard dependencies: nothing can be permission-guarded until JWT works; RBAC guards cannot be wired until the permission resolver exists; the permission resolver cannot run without the hierarchy tables.

### Step 1 — DB Schema Foundation (prerequisite for everything)

**Why first:** All subsequent steps depend on the tables existing.

- Alembic migration: `organizations`, `users`, `roles`, `user_roles` tables
- Alembic migration: rename `projects` → `apps`, add `project_id` FK; add new `projects` table
- Alembic migration: update all FK references (`app_files.app_id`, `audit_snapshots.app_id`, etc.)
- Seed `roles` table: `org_admin`, `project_member`, `app_user`

**What can proceed in parallel after this step:** JWT auth implementation + Permission resolver implementation (no dependency between them; both depend only on the schema).

### Step 2A — JWT Auth (parallel with 2B)

**Why second:** Route guards need `get_current_user()` to exist.

- `User` ORM model + password hashing (`passlib[bcrypt]`)
- `POST /api/auth/register`, `POST /api/auth/login` (returns JWT)
- `GET /api/auth/me`
- `get_current_user()` Depends callable in `backend/app/core/auth.py`
- `SECRET_KEY` + `JWT_ALGORITHM` + `JWT_EXPIRE_MINUTES` in `Settings`
- Frontend: login page, token storage, 401 → redirect to login

### Step 2B — Permission Resolver (parallel with 2A)

**Why second:** Route guards wrap this function.

- `can_user(user_id, action, resource_type, resource_id)` in `backend/app/core/permissions.py`
- `ROLE_PERMISSIONS` hardcoded dict (Phase 1)
- Inheritance chain: app → project → org → superadmin
- Request-scoped cache dict (passed via `request.state` or assembled inline)
- `require_permission(action, resource_type, path_param)` factory returning `Depends()` callable
- Unit tests: org_admin gets access, project_member gets project+app, app_user gets app only, stranger gets nothing, inheritance works

### Step 3 — Wire Guards on Existing Routes

**Why third:** Needs both `get_current_user()` (Step 2A) and `require_permission()` (Step 2B).

- Add `Depends(get_current_user)` + `Depends(require_permission(...))` to all route signatures
- Route-to-resource mapping:
  - `/api/apps/{app_id}/*` → `require_permission(action, "app")`
  - `/api/projects/{project_id}/*` → `require_permission(action, "project")`
  - `/api/orgs/{org_id}/*` → `require_permission(action, "org")`
- No route handler logic changes — only signature changes
- Test: all routes return 401 without token, 403 with wrong scope, 200 with correct role

### Step 4 — Role Assignment API

**Why fourth:** Needs auth (who is assigning) + hierarchy tables (what can be assigned).

- `POST /api/orgs/{org_id}/members` — assign user a role in org
- `POST /api/projects/{project_id}/members` — assign user a role in project
- `POST /api/apps/{app_id}/members` — assign user a role in app
- `DELETE` variants for revocation
- All assignment endpoints guarded by `require_permission("manage_users", <resource_type>)`

### Step 5 — DB-Driven Permissions (Phase 2)

**Why last:** Pure replacement of the hardcoded dict; no structural changes.

- `permissions` + `role_permissions` Alembic migration
- Seed default permissions matching the Phase 1 hardcoded map
- Replace `ROLE_PERMISSIONS[role_name]` lookup with DB query in `can_user()`
- Admin API: assign/revoke permissions from roles (guarded by superadmin check)

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Permission Checks Inside Business Logic

**What:** Checking `can_user()` inside a workflow or service function rather than at the route boundary.

**Why bad:** Business logic becomes entangled with auth concerns. Workflows run asynchronously after the HTTP response starts (SSE). If a permission check fails mid-stream, the stream has already started — you cannot return HTTP 403 anymore.

**Instead:** All permission checks happen in the `Depends()` chain before the route handler executes. The handler assumes the user is authorized by the time it runs.

### Anti-Pattern 2: Storing JWT Claims Beyond user_id

**What:** Embedding `role_names`, `permissions`, or `resource_ids` inside the JWT payload.

**Why bad:** Stale tokens carry stale permissions. If a user's role is revoked, their token still claims the old role until it expires. For an internal tool, this is an invisible privilege escalation window.

**Instead:** JWT carries only `user_id` (+ `exp`, `iat`). Permission resolution happens on every request via DB (with request-scoped cache for repeated same-request checks).

### Anti-Pattern 3: Global Middleware for RBAC

**What:** A single `@app.middleware("http")` that tries to extract the resource from the URL and check permissions before the request reaches the router.

**Why bad:** URL parsing is fragile (regex on path strings). It cannot access path parameters (FastAPI hasn't parsed them yet). SSE routes need special handling. It runs on every request including `/health` and `/docs`.

**Instead:** Use FastAPI's `Depends()` system. Permission guards are composed at the route level where path parameters are already typed and available.

### Anti-Pattern 4: Single `user_roles` Query Fetching All User Roles at Once

**What:** `SELECT * FROM user_roles WHERE user_id = :user_id` on every request, then filtering in Python.

**Why bad:** Unbounded result set if a user has many role assignments. Fetches all resources (orgs, projects, apps) when you only need one.

**Instead:** Scoped queries: check only the specific `resource_id` at each level of the inheritance chain. Three targeted queries (app-level, project-level, org-level) with indexed FKs are faster than one unindexed full-scan.

### Anti-Pattern 5: Applying Guards to Routes Before Auth Works

**What:** Adding `Depends(require_permission(...))` to routes before `get_current_user()` is implemented and tested.

**Why bad:** Breaks all existing functionality immediately without a working replacement. The development team loses the ability to test non-auth features during transition.

**Instead:** Follow the build order above. Keep all routes open (no guards) until Step 3. Use a feature flag env var (`ENFORCE_AUTH=false`) during transition to allow running without auth in dev while implementing auth.

---

## Scalability Considerations

| Concern | Phase 1 (current) | Phase 3 (cache) | Phase 4+ (distributed) |
|---------|-------------------|-----------------|------------------------|
| DB queries per request | 4 (user + 3 hierarchy lookups) | 1 (user only; rest from request-state cache) | 0 for cached users (Redis TTL) |
| Role assignment propagation | Immediate (next request re-queries DB) | Immediate (request-scoped cache expires per-request) | TTL delay (Redis TTL, e.g. 60s) |
| Superadmin bypass | `user.is_superadmin` flag | Same | Same |
| Multi-worker deployment | Safe (no in-process shared state) | Safe (per-request cache is request-local) | Requires Redis (no local state) |

The request-scoped cache (Phase 3) is a dict on `request.state` populated during the Depends chain. It is destroyed at request end — no cross-request contamination, no invalidation problem, no multi-worker coordination needed.

---

## Integration with Existing Codebase

### What Changes vs. What Stays

**Stays identical:**
- All workflow logic (M1, M2, Faza 2/5/6)
- SSE streaming pattern and event format
- Chroma per-app vector stores (key changes from `project_id` to `app_id` in naming only)
- `get_db()` dependency injection pattern — auth dependencies follow the same pattern

**Changes minimally (signature only, no body logic):**
- All route files: add `current_user: User = Depends(get_current_user)` and `Depends(require_permission(...))` to each route function signature

**Changes substantially:**
- `backend/app/db/models.py` — add `Organization`, rename `Project`→`App`, add `Project` (middle tier), update all FK column names
- `backend/app/main.py` — add `auth` router, update route prefixes (`/api/projects/` → `/api/apps/`)
- All Alembic migrations — rename tables and FK columns

**New files:**
- `backend/app/db/auth_models.py` — `User`, `Role`, `UserRole` ORM models
- `backend/app/core/auth.py` — `get_current_user()`, JWT encode/decode helpers
- `backend/app/core/permissions.py` — `can_user()`, `require_permission()`, `ROLE_PERMISSIONS`
- `backend/app/api/routes/auth.py` — `/register`, `/login`, `/me`
- `backend/app/api/routes/orgs.py` — org CRUD + member management
- `backend/migrations/versions/002_add_hierarchy_tables.py` — organizations, projects (new), apps rename
- `backend/migrations/versions/003_add_auth_rbac_tables.py` — users, roles, user_roles
- `frontend/lib/useAuth.ts` — token storage, login/logout, 401 handling
- `frontend/app/login/page.tsx` — login page
- `frontend/app/register/page.tsx` — register page

### Route Prefix Rename Impact

Current: `/api/projects/{project_id}/...`
Target: `/api/apps/{app_id}/...`

The `next.config.mjs` already has permanent redirects for old URLs. The same approach covers the API: the old `/api/projects/*` routes can be kept as 301 redirects during transition, then removed. All frontend hooks must be updated to the new path.

---

## Sources

- Direct codebase analysis of `backend/app/db/models.py`, `backend/app/core/config.py`, `backend/app/api/routes/projects.py`, `backend/app/main.py`, `backend/app/db/engine.py` (HIGH confidence — source of truth)
- `.planning/PROJECT.md` — project requirements and hierarchy spec (HIGH confidence)
- `.planning/codebase/ARCHITECTURE.md` — existing layer analysis (HIGH confidence)
- FastAPI dependency injection pattern for auth: `https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/` (MEDIUM confidence — pattern is stable and well-established, not verified against current docs in this session due to tool unavailability)
