# Phase 3: RBAC Core - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Implement the RBAC permission resolver and wire it onto every existing API route. Unauthenticated requests return 401. Requests from users with no role on the target resource return 403. SSE workflows cannot be triggered by unauthorized users (guard fires before the stream starts). IDOR protection verified on all project-scoped routes. Superadmin bootstrap endpoint added (moved from Phase 4). No frontend changes. All existing backend tests pass with ENFORCE_AUTH=false.

</domain>

<decisions>
## Implementation Decisions

### Permission Action Vocabulary
- **D-01:** `can_user()` uses 3 action strings: `read`, `write`, `delete`. Mapping: GET endpoints → `read`; POST/PATCH → `write`; DELETE → `delete`.
- **D-02:** Hardcoded permission map for 3 built-in roles:
  - `org_admin`: read + write + delete on all resources in their org
  - `workspace_member`: read + write on workspace and all its projects
  - `project_viewer`: read only on specific project
- **D-03:** Phase 5 adds `manage_users` action to the `permissions` table — the 3-action vocab here does not conflict; `manage_users` is simply absent from the hardcoded dict.

### Route Guarding Pattern
- **D-04:** Router-level auth: each route file uses `router = APIRouter(dependencies=[Depends(get_current_user)])`. This ensures all routes in a file require authentication without repeating `Depends(get_current_user)` on every handler.
- **D-05:** Per-handler permission: `require_permission('action', 'resource_type')` factory returns a Depends callable added to each handler signature. FastAPI's dependency cache ensures `get_current_user` runs once per request even though it appears in both `router.dependencies` and inside `require_permission()`.
- **D-06:** Routes without a `project_id` path param (e.g. `GET /api/projects/`, `POST /api/projects/`) use org-scoped permission: `require_permission('read', 'organization')` and `require_permission('write', 'organization')` respectively.

### SSE Guards
- **D-07:** SSE route handlers (`POST /api/context/{project_id}/build`, `POST /api/chat/stream`, `POST /api/requirements/{project_id}/extract`, `POST /api/mapping/{project_id}/run`) add `_: None = Depends(require_permission('write', 'project'))` in the handler signature. FastAPI resolves all Depends before executing the generator — 403 is raised before any streaming begins (no LLM tokens consumed on denied requests).
- **D-08:** The `_context_store` cache in `context.py` is correctly guarded because `require_permission` fires via Depends before the route body executes. The cache read is inside the route body — the auth/permission check always precedes it.

### ENFORCE_AUTH=false Behavior
- **D-09:** When `ENFORCE_AUTH=false`, `get_current_user()` returns `AnonymousUser` (existing Phase 2 behavior). `require_permission()` must also bypass its check when `ENFORCE_AUTH=false` — returns `None` without querying the DB. This preserves the existing test suite with zero modifications.

### Superadmin Bootstrap (moved from Phase 4)
- **D-10:** `POST /api/auth/bootstrap` added to the auth router in Phase 3. Creates the first superadmin account when the `users` table is empty (no users registered yet). Returns 409 if any user already exists. Open endpoint (no auth required). Unblocks development between Phase 3 and Phase 4 role assignment API.

### ORM Model File
- **D-11:** `Role` and `UserRole` ORM models go in a new `backend/app/db/rbac_models.py` — follows the established pattern (`hierarchy_models.py`, `auth_models.py`). Imported in `engine.py` and `migrations/env.py` as side-effect imports.

### Migration
- **D-12:** Single Alembic migration `007_add_rbac_tables.py` with `down_revision = "006"`. Steps: (1) create `roles` table, (2) seed 3 built-in roles (`org_admin`, `workspace_member`, `project_viewer`), (3) create `user_roles` table with composite index on `(user_id, resource_type, resource_id)`.

### Permission Memoization
- **D-13:** Request-scoped memoization via `request.state` dict: `can_user()` stores results keyed by `(user_id, action, resource_type, resource_id)` in `request.state.rbac_cache`. Second call for the same tuple skips DB query. Prevents N+1 in SSE workflows where multiple permission checks may fire per stream.

### Test Strategy
- **D-14:** Two new test files:
  - `backend/tests/test_rbac_unit.py` — Direct unit tests for `can_user()` with seeded DB data: org_admin grants, project_viewer denies on write, inheritance chain (project → workspace → org), memoization skips second DB call.
  - `backend/tests/test_rbac_integration.py` — HTTP integration tests with `ENFORCE_AUTH=true` and seeded users+roles: unauthenticated → 401, wrong-scope → 403, IDOR (user A cannot access user B's project) → 403, SSE endpoint → 403 before stream starts.

### Claude's Discretion
- Exact SQL for the composite index on `user_roles` (name, column order within index)
- Whether `can_user()` lives in `app.core.rbac` or `app.core.auth` (new module preferred for separation)
- Error message wording for 401 vs 403 responses
- Whether to add a `description` field to `roles` table (not in requirements — omit)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements (Phase 3 scope)
- `.planning/REQUIREMENTS.md` §RBAC Core — RBAC-01 through RBAC-09 define exact table schemas, permission map, and success criteria
- `.planning/ROADMAP.md` §Phase 3 — Success criteria (7 items) that verification must check

### Existing codebase to extend
- `backend/app/core/auth.py` — `get_current_user()` + `AnonymousUser`; `require_permission()` must match the same ENFORCE_AUTH bypass pattern
- `backend/app/db/auth_models.py` — `User` model; `UserRole` FK references `users.id`
- `backend/app/db/hierarchy_models.py` — `Organization`, `Workspace` models; `DEFAULT_ORG_ID` constant; `can_user()` resolves project → workspace → org chain using these models
- `backend/app/db/models.py` — `Project` model; has `organization_id` (required) and `workspace_id` (nullable) columns used by `can_user()` for hierarchy traversal
- `backend/migrations/versions/006_add_users_table.py` — Latest migration; `007` sets `down_revision = "006"`
- `backend/app/db/hierarchy_models.py` — Pattern to follow for `rbac_models.py`
- `backend/app/db/engine.py` — Add `import app.db.rbac_models  # noqa: F401`
- `backend/migrations/env.py` — Add `import app.db.rbac_models  # noqa: F401`

### Route files to guard (all 8)
- `backend/app/api/routes/projects.py` — CRUD routes; list/create use org-scoped permission
- `backend/app/api/routes/files.py` — Upload and list; project-scoped
- `backend/app/api/routes/chat.py` — SSE stream; `require_permission('write', 'project')` before generator
- `backend/app/api/routes/context.py` — SSE build + status/mindmap/glossary GETs; guard SSE before stream
- `backend/app/api/routes/snapshots.py` — Audit history; project-scoped
- `backend/app/api/routes/requirements.py` — Faza 2 SSE + CRUD; project-scoped
- `backend/app/api/routes/mapping.py` — Faza 5+6 SSE + read routes; project-scoped
- `backend/app/api/routes/auth.py` — Register/login/logout/me remain open or auth-only; add bootstrap endpoint here

### Pitfalls from prior phases
- `.planning/STATE.md` §Blockers/Concerns — `_context_store` cache auth order (D-08 above resolves this via Depends chain ordering)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `get_current_user()` in `app.core.auth` — already handles `ENFORCE_AUTH=false` via `AnonymousUser`; `require_permission()` reads the same flag
- `AnonymousUser` dataclass — `is_superadmin=False`, `id="anonymous"`; when `ENFORCE_AUTH=false`, permission check sees this and bypasses
- `DEFAULT_ORG_ID` from `hierarchy_models.py` — constant for the seeded default org; `can_user()` uses it as a fallback org when project has no explicit workspace
- UUID + DateTime patterns from prior model files — reuse same `default=lambda: str(uuid.uuid4())` and `DateTime(timezone=True)` for `roles` and `user_roles`
- `AsyncSessionLocal` from `engine.py` — available for direct DB use in `can_user()` when not going through `get_db()`

### Established Patterns
- `render_as_batch=True` in `migrations/env.py` — SQLite ALTER TABLE batch mode; already configured
- Model side-effect import pattern: `import app.db.rbac_models  # noqa: F401` in `engine.py` and `migrations/env.py`
- `router = APIRouter()` in each route file — Phase 3 changes these to `APIRouter(dependencies=[Depends(get_current_user)])`
- FastAPI dependency caching within a request — same `Depends(get_current_user)` instance resolves once even if referenced in multiple places

### Integration Points
- `backend/app/main.py` — No changes needed (routers already registered; `dependencies=` added within each router file)
- `backend/app/api/routes/auth.py` — Bootstrap endpoint added here (alongside register/login/logout/me)
- `request.state` — FastAPI Request carries per-request state dict; `rbac_cache` key added by `can_user()` for memoization
- `Project.organization_id` + `Project.workspace_id` — read inside `can_user()` to resolve hierarchy when `resource_type='project'`

</code_context>

<specifics>
## Specific Ideas

- `require_permission()` factory pattern with FastAPI dependency caching — user explicitly chose this for cleaner handler signatures (no `current_user` param repeated everywhere)
- Router-level `dependencies=[Depends(get_current_user)]` — one line per route file covers all handlers for auth; permission check still per-handler
- `POST /api/auth/bootstrap` pulled into Phase 3 — superadmin seed before Phase 4 role assignment API exists

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---

*Phase: 03-rbac-core*
*Context gathered: 2026-03-28*
