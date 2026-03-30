# Phase 2: Authentication - Context

**Gathered:** 2026-03-28
**Status:** Ready for planning

<domain>
## Phase Boundary

Add user identity to the system: `users` table, email/password registration and login, JWT in httpOnly cookie, `get_current_user()` FastAPI dependency, and `ENFORCE_AUTH` env flag. Frontend login/register pages with redirect on auth state. All existing backend tests must pass with `ENFORCE_AUTH=false`. No RBAC enforcement — that is Phase 3.

</domain>

<decisions>
## Implementation Decisions

### User ORM Model
- **D-01:** `User` model goes in a new `backend/app/db/auth_models.py` — follows the `hierarchy_models.py` pattern from Phase 1. Imports `Base` from `models.py`. Registered in `engine.py` and `migrations/env.py` via `import app.db.auth_models  # noqa: F401`.
- **D-02:** Migration `006_add_users_table.py` with `down_revision = "005"`. Creates `users` table only; `organizations.owner_id` FK constraint (deferred from Phase 1 per D-01 in 01-CONTEXT.md) added in the same migration.

### Authentication Libraries
- **D-03:** `PyJWT >= 2.9.0` for JWT encode/decode (FastAPI official recommendation; python-jose has unmaintained CVE-bearing dep). `pwdlib[argon2]` for password hashing (replaces passlib which is incompatible with bcrypt 4.x).
- **D-04:** JWT signed with `JWT_SECRET` from `settings` (already present in `config.py` as `JWT_SECRET: str = "change-me-in-production"`). Payload contains only `user_id` and `exp`.

### JWT Session Length
- **D-05:** JWT TTL = **86400 seconds (24 hours)**. Rationale: covers full workday without re-login friction; safely above the 3600s minimum (2× M1_WORKFLOW_TIMEOUT_SECONDS=1800s) required to prevent mid-workflow 401s.
- **D-06:** Cookie config: `httpOnly=True`, `samesite="lax"`, `secure=False` in dev (`APP_ENV != "production"`), `secure=True` in prod. `max_age=86400`. Path `/`.

### ENFORCE_AUTH Flag
- **D-07:** `ENFORCE_AUTH: bool = True` added to `Settings`. When `False`, `get_current_user()` returns a mock anonymous user instead of raising 401 — existing test suite passes without any test modification.

### FastAPI Dependency
- **D-08:** `get_current_user()` reads JWT from `request.cookies.get("access_token")`. Raises `HTTP 401` on missing/invalid/expired token. Placed as `Depends()` per route — not global middleware (global middleware breaks SSE and cannot read typed path params).

### Register Endpoint Access
- **D-09:** `POST /api/auth/register` is **open in Phase 2** — anyone can create an account. RBAC enforcement (what authenticated users can access) arrives in Phase 3. This is safe because Phase 2 routes do not yet enforce org/workspace scoping; that gate closes in Phase 3.

### Frontend Auth Guard
- **D-10:** Next.js `frontend/middleware.ts` handles unauthenticated redirects. Checks for `access_token` cookie; redirects to `(auth)/login` page if missing on protected routes. Matcher excludes `(auth)/*`, `_next/*`, and static assets. This prevents flash of protected content and requires no per-page guard logic.
- **D-11:** `(auth)/login` and `(auth)/register` route group directories already exist (scaffolded). Add `page.tsx` to each with minimal form UI (email + password, submit, error display). Redirect to `/` on success.

### credentials: include Strategy
- **D-12:** Create `frontend/lib/apiFetch.ts` — thin wrapper around `fetch()` with `credentials: "include"` baked in. Migrate all hook calls (`useAIBuddyChat`, `useContextBuilder`, `useRequirements`, `useMapping`, `useHeatmap`, `useProjectFiles`, `useProjects`, `usePanelFiles`, `useAuditPipeline`, `useContextStatuses`, `useSnapshots`) to use `apiFetch` instead of `fetch`. `sseStream.ts` `consumeSSE` receives a `Response` and doesn't call fetch directly — but the hooks that call `fetch()` before passing to `consumeSSE` must use `apiFetch`.

### Claude's Discretion
- Exact login/register form layout (minimal is fine — internal tool)
- Error message wording on 401/403
- Whether to add a `display_name` or `name` field to `users` (not in requirements — omit)
- Relationship back-populate between `User` and `Organization.owner_id`

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements (Phase 2 scope)
- `.planning/REQUIREMENTS.md` §Authentication — AUTH-01 through AUTH-10 define exact columns, endpoints, and behaviors
- `.planning/ROADMAP.md` §Phase 2 — Success criteria (7 items) that verification must check

### Existing codebase to extend
- `backend/app/core/config.py` — `JWT_SECRET` already present; add `ENFORCE_AUTH: bool = True`, `JWT_TTL_SECONDS: int = 86400`
- `backend/app/main.py` — Add auth router to `app.include_router()`; CORSMiddleware already has `allow_credentials=True`
- `backend/app/db/engine.py` — Add `import app.db.auth_models  # noqa: F401` (same pattern as hierarchy_models)
- `backend/migrations/env.py` — Add `import app.db.auth_models  # noqa: F401` before `target_metadata`
- `backend/migrations/versions/005_add_hierarchy_tables.py` — Latest migration; `006` sets `down_revision = "005"`
- `backend/app/db/hierarchy_models.py` — Phase 1 model file pattern to follow for `auth_models.py`; also `organizations.owner_id` needs FK added here in migration 006

### Frontend
- `frontend/app/(auth)/login/` — Directory exists, needs `page.tsx`
- `frontend/app/(auth)/register/` — Directory exists, needs `page.tsx`
- `frontend/next.config.mjs` — No auth redirects yet; `middleware.ts` handles that instead
- `frontend/lib/sseStream.ts` — `consumeSSE` reads a `ReadableStream`, doesn't call `fetch` — SSE hooks that initiate the fetch must use `apiFetch`

### Critical pitfall
- `.planning/STATE.md` §Blockers/Concerns — JWT TTL >= 3600s (covered by D-05 at 86400s); `_context_store` cache authorization order (addressed in Phase 3, not Phase 2)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `JWT_SECRET` in `config.py` — already present as `str = "change-me-in-production"`; Phase 2 adds `JWT_TTL_SECONDS` and `ENFORCE_AUTH` alongside it
- `Base` from `models.py` — shared `DeclarativeBase`; `auth_models.py` imports and uses it
- UUID + DateTime patterns from `models.py` / `hierarchy_models.py` — `default=lambda: str(uuid.uuid4())`, `DateTime(timezone=True)` — reuse for `User`
- `DEFAULT_ORG_ID` from `hierarchy_models.py` — useful in Phase 2 if we need to auto-assign new users to the default org (relevant to Phase 3, but good to know)
- `consumeSSE` in `sseStream.ts` — takes a `ReadableStream`, not a URL; hooks call `fetch(url).then(res => consumeSSE(res.body, ...))` — `apiFetch` replaces `fetch` in that call

### Established Patterns
- `render_as_batch=True` in `migrations/env.py` — SQLite ALTER TABLE works for adding FK constraints
- Route files in `backend/app/api/routes/` — new `auth.py` follows same structure (FastAPI `APIRouter`, Pydantic schemas inline or in separate schemas file)
- All async DB calls use `AsyncSession` from `engine.py`'s `get_db()` dependency
- Cookie setting in FastAPI: `response.set_cookie(key=..., value=..., httponly=True, samesite="lax", ...)` requires `Response` param in handler

### Integration Points
- `main.py` — register `auth.router` with prefix `/api/auth`
- `engine.py` — side-effect import of `auth_models` to register `User` table with `Base.metadata`
- `migrations/env.py` — same side-effect import for Alembic autogenerate
- `organization.owner_id` — currently nullable String with no FK; migration 006 adds `ForeignKey("users.id", ondelete="SET NULL")` (SET NULL so org survives if owner is deleted)
- All 10+ frontend hooks — replace `fetch(` with `apiFetch(` after creating `frontend/lib/apiFetch.ts`

</code_context>

<specifics>
## Specific Ideas

- JWT TTL = 86400s (24h) — confirmed by user; matches the "internal tool, low login friction" preference
- Register is open in Phase 2 — confirmed; RBAC locks it down in Phase 3 via `require_permission()`
- `apiFetch()` wrapper — confirmed; centralizes `credentials: "include"` and sets up for future auth header additions

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---
*Phase: 02-authentication*
*Context gathered: 2026-03-28*
