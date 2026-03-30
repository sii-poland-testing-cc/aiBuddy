# Domain Pitfalls: Auth + RBAC on an Existing FastAPI App

**Domain:** Adding JWT auth + scoped RBAC to an existing FastAPI + SQLAlchemy async app
**Researched:** 2026-03-27
**Overall confidence:** HIGH — findings are grounded in the actual codebase at `D:/kod/sii/aiBuddy` plus established FastAPI/SQLAlchemy patterns

---

## Critical Pitfalls

Mistakes in this category cause partial system failure, data integrity loss, or forced rewrites.

---

### Pitfall 1: SQLite Cannot Drop Columns or Rename Constraints — `render_as_batch=True` Is Not a Silver Bullet

**What goes wrong:**
The existing migration env already has `render_as_batch=True` in `migrations/env.py`. This handles single-table column changes via a copy-and-rename strategy. But the rename from `projects` → `apps` is not a single-table column change — it requires:

1. Creating the new `apps` table with the new name
2. Copying all data
3. Dropping four FK constraints across `project_files`, `audit_snapshots`, `requirements`, `requirement_tc_mappings`, and `coverage_scores` that reference `projects.id`
4. Recreating those constraints pointing at `apps.id`
5. Dropping the old `projects` table

SQLite does not support `ALTER TABLE RENAME TO` for a table that is the target of foreign keys in other tables. The `render_as_batch` mode recreates the table being altered, not the tables that reference it. Each child table (`project_files`, `audit_snapshots`, `requirements`, `requirement_tc_mappings`, `coverage_scores`) must also be batch-migrated in dependency order to update their FK references.

If migrations are written naively as `op.rename_table("projects", "apps")`, Alembic will emit that DDL, SQLite will silently corrupt the FK constraint metadata, and the FK will point at a non-existent table name — only detectable after `PRAGMA foreign_key_check`.

**Why it happens:**
`render_as_batch=True` only applies to the table being modified, not to referencing tables. The rename is treated as a structural change to the parent table, but the child-table FKs are untouched.

**Consequences:**
- Silent FK corruption in SQLite (foreign_keys pragma is OFF by default in SQLite)
- Alembic `check` passes because autogenerate compares ORM metadata, not FK target names
- Production breakage only surfaces when queries cross table boundaries (joins, cascades)

**Prevention:**
Write the rename migration manually as a sequence of batch operations, not as `op.rename_table`. The order must be:
1. `op.batch_alter_table("coverage_scores")` → drop FK on `project_id`, recreate pointing at `apps`
2. `op.batch_alter_table("requirement_tc_mappings")` — same
3. `op.batch_alter_table("requirements")` — same
4. `op.batch_alter_table("audit_snapshots")` — same
5. `op.batch_alter_table("project_files")` — same (two FKs: `project_id` and `last_used_in_audit_id` which points at `audit_snapshots.id`, no change needed there)
6. Create `apps` table as copy of `projects`, copy data, drop `projects`

Run `PRAGMA foreign_key_check` at end of migration to verify.

**Detection (warning signs):**
- `alembic check` reports no drift after rename (false positive — it compares ORM, not DB)
- No FK constraint error when inserting an `audit_snapshots` row with a non-existent `project_id`
- Foreign key violations only appear at application level, not in SQLite pragma

**Phase:** Must be addressed in the entity rename phase (Phase 1 prerequisite). Do not add auth middleware until this is verified clean.

---

### Pitfall 2: Chroma Collection Names Are Hardcoded as `project_{project_id}` — Rename Does Not Propagate

**What goes wrong:**
The `ContextBuilder` class names Chroma collections using `project_id` with a hardcoded prefix:

```python
# backend/app/rag/context_builder.py
self._chroma_client = chromadb.PersistentClient(path=cfg.CHROMA_PERSIST_DIR)
```

Collection names are derived from the entity that was called "project" (now called "app"). After renaming the DB entity and API routes, the Chroma collection naming pattern must also update. But `chromadb.PersistentClient` stores collections on disk by their string name. Existing indexed data lives under the old naming scheme. A code change that renames the collection prefix without migrating existing data silently creates a new empty collection while leaving the old data unreachable.

**Why it happens:**
Chroma has no `RENAME COLLECTION` operation. Collection naming is opaque to Alembic — no migration system covers it.

**Consequences:**
- All existing RAG indexes become unreachable after the rename
- `rag_ready` check returns `False` for all apps that had M1 context built
- `context_built_at` in DB is still set (non-null), but `is_indexed()` returns `False` — this is the exact `rag_ready` isolation logic in `context.py`. Both conditions must be true; after the rename, the Chroma check fails.
- Users see "Brak kontekstu" in the UI despite having uploaded documents previously

**Prevention:**
Before renaming the code, write a one-time data migration script (not Alembic — a Python script) that iterates all existing `project_id` values, reads each Chroma collection, re-indexes data under the new naming scheme, and deletes the old collection. Alternatively, keep the collection naming using raw UUIDs (no prefix), making the prefix irrelevant. The UUID itself doesn't encode "project" or "app".

**Detection (warning signs):**
- After rename: `GET /api/context/{app_id}/status` returns `rag_ready: false` for apps that previously showed `rag_ready: true`
- Audit results show 0% coverage (no RAG context to query)
- Chroma data directory still shows old collection files on disk

**Phase:** Address in the entity rename phase, immediately after DB migration is verified. Run the Chroma rename script as part of the same deployment step.

---

### Pitfall 3: SSE Streaming Endpoints Are Incompatible With Standard FastAPI JWT Middleware Placement

**What goes wrong:**
FastAPI middleware (added via `app.add_middleware(...)`) runs for every request before the route handler. However, `StreamingResponse` with `media_type="text/event-stream"` is returned from the route handler — the response body is produced asynchronously after the handler returns. Middleware that attempts to inspect or modify the response body (e.g., to enforce auth based on response content) cannot reach the streaming body.

More practically: the existing SSE endpoints (`/api/chat/stream`, `/api/context/{project_id}/build`, `/api/requirements/{project_id}/extract`, `/api/mapping/{project_id}/run`) all return `StreamingResponse`. If JWT auth is placed in middleware that reads the request body to extract `project_id` for resource-level checks, it will consume the body before the route handler can read it. FastAPI request bodies are not re-readable after a middleware consumes them.

**Why it happens:**
Middleware in Starlette/FastAPI receives the raw `Request` object. `await request.body()` or `await request.json()` reads and consumes the stream. The route handler's Pydantic model binding then gets an empty body, causing a 422 validation error.

**Consequences:**
- Every SSE endpoint returns 422 after JWT middleware is added
- Auth is silently bypassed if middleware short-circuits on body read failure
- LLM workflows are triggered before auth is confirmed, wasting API credits on unauthenticated requests

**Prevention:**
Do not parse the request body in middleware. Use FastAPI's dependency injection system (`Depends`) for all auth. Place a reusable `get_current_user: Annotated[User, Depends(require_auth)]` dependency on each route. For SSE routes specifically, add the dependency as a route parameter:

```python
@router.post("/stream")
async def chat_stream(req: ChatRequest, current_user: User = Depends(require_auth)):
    ...
```

This is the FastAPI-canonical pattern. `Depends` runs before the handler, the body is parsed once by Pydantic for `req`, and auth is verified from the `Authorization` header (not the body).

**Detection (warning signs):**
- 422 errors on SSE endpoints after adding middleware
- Tests that mock `AsyncClient` without an `Authorization` header start failing with validation errors, not 401s

**Phase:** Phase 1 auth implementation. Define `require_auth` dependency before touching any route.

---

### Pitfall 4: The Rename Is Not Just DB and Routes — Five Additional Surfaces Will Break Silently

**What goes wrong:**
The rename from "project" to "app" touches more than ORM models and API routes. The following surfaces each have independent references that will not be caught by a search-and-replace:

1. **File system paths** — `./data/uploads/{project_id}/` and `./data/uploads/{project_id}/context/` are hardcoded in `files.py` and `context.py`. The path segment name does not need to change (the UUID is the key), but any code that constructs paths using a variable named `project_id` must still refer to the correct UUID after the rename. If the variable is renamed to `app_id` and a path construction is missed, files will be written to a different directory or a `FileNotFoundError` will be raised at runtime.

2. **Pydantic response schemas** — `ProjectOut` in `projects.py` has `project_id: str` as a field name. If the field is renamed to `app_id` in the backend but the frontend still reads `response.project_id`, all project list items will silently show `undefined` as their ID. Navigation to `/project/[projectId]` will break.

3. **Frontend routing** — `app/project/[projectId]/page.tsx` and `next.config.mjs` permanent redirects (`/chat/:id → /project/:id`) use the word "project" in the URL path. These are user-visible URLs. If the API rename changes route structure but the frontend router is not updated in sync, links will 404. The permanent redirects in `next.config.mjs` are cached by browsers — changing the destination after deployment requires cache-busting.

4. **SSE event payloads** — The audit result shape includes `"project_id"` as a key in the JSON result streamed over SSE. Frontend code that destructures `{ project_id }` from SSE events will break if the backend starts emitting `{ app_id }` without a simultaneous frontend update.

5. **Test fixtures and assertions** — Tests in `test_m1_context.py`, `test_m1_m2_integration.py`, `test_snapshots.py`, and `test_rag_ready_isolation.py` construct requests using `"project_id"` as a query param or body field. After the rename, these tests will send requests to the old route paths and fail with 404 before even testing the logic.

**Why it happens:**
Rename operations feel complete after ORM + route changes. The less-visible surfaces (SSE payloads, Pydantic field names, file paths, test fixtures) are not indexed by an IDE's refactor tool the same way Python symbols are.

**Consequences:**
- Silent data loss (files written to wrong path)
- Frontend shows `undefined` IDs, breaking all navigation
- All 65+ backend tests break with 404s
- CI passes (if tests aren't run) but production fails

**Prevention:**
Before starting the rename, enumerate every surface with a grep across the full repo:
```
grep -r "project_id" backend/ frontend/ --include="*.py" --include="*.ts" --include="*.tsx" -l
grep -r "/api/projects" backend/ frontend/ --include="*.py" --include="*.ts" --include="*.tsx" -l
```
Create a checklist. Rename in a single PR with full test run. Do not split the rename across multiple PRs.

**Detection (warning signs):**
- Any test passing `project_id` in request body or URL after the rename without updating the field name
- Frontend console errors: `Cannot read property 'projectId' of undefined`
- File upload succeeds (201) but uploaded file is not found when audit is triggered

**Phase:** Entity rename phase. The rename must be done atomically — all surfaces in one PR, tests must pass before merge.

---

### Pitfall 5: Hierarchical Permission Inheritance Has a Transitive Closure Problem

**What goes wrong:**
The planned hierarchy is Org → Project → App. The `canUser(userId, action, resourceType, resourceId)` resolver must walk up the hierarchy: if a user has `org_admin` on Org A, they can access any Project inside Org A and any App inside any of those Projects.

The naive implementation queries `user_roles` for the specific resource first, then the parent, then the grandparent — three separate DB queries per authorization check. In this codebase, the SSE endpoints trigger LlamaIndex workflows that make dozens of internal calls to retrieve files, snapshots, and RAG context. If each internal call re-authorizes via the full hierarchy walk, a single `/api/chat/stream` request triggers 20–50 auth DB queries.

A second failure mode: if the hierarchy walk is implemented recursively without a visited-set guard, a misconfigured `organization_id` cycle (Org A's project points at Org B, Org B's project points at Org A) causes infinite recursion and a stack overflow in the permission resolver.

**Why it happens:**
Hierarchy traversal is easy to prototype but hard to make safe and fast at the same time. The first-pass implementation typically does no caching and no cycle detection.

**Consequences:**
- SSE streaming requests time out under load (not from LLM latency but from auth overhead)
- Stack overflow on misconfigured org hierarchy data
- Permission checks become the database bottleneck (more queries than actual business logic)

**Prevention:**
Resolve permissions once per request and attach the result to request state. FastAPI's dependency injection makes this straightforward:

```python
async def get_current_user_permissions(
    request: Request,
    current_user: User = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
) -> PermissionContext:
    perms = await resolve_permissions(db, current_user.id)
    return perms
```

The `PermissionContext` is computed once and reused by all downstream `Depends` calls in the same request. This is request-scoped caching without Redis, which is Phase 3's Redis cache.

Add an explicit depth limit (max 5) and a visited-set in the hierarchy walker from day one — not Phase 3.

**Detection (warning signs):**
- Audit SSE requests take 5–10 seconds before the first progress event
- SQLAlchemy slow query log shows repeated identical `SELECT ... FROM user_roles WHERE ...` within a single request
- Stack overflow tracebacks mentioning `resolve_permissions` in recursive calls

**Phase:** Phase 1 RBAC core. Design the permission resolver with request-scoped memoization from the start. Do not defer caching to Phase 3 — the SSE workflow pattern makes this critical from day one.

---

### Pitfall 6: JWT Middleware Applied Globally Will Break Health Checks, Docs, and SSE Preflight

**What goes wrong:**
If `require_auth` is applied as an app-wide middleware (rather than per-route), several endpoints will break:

- `GET /docs` and `GET /openapi.json` — FastAPI's built-in Swagger UI and OpenAPI schema endpoint. These are unauthenticated by design. Blocking them with JWT middleware prevents developers from seeing the API schema and testing endpoints.
- `GET /` or `/health` — Kubernetes/Docker health check probes do not send JWT tokens. A 401 from a health endpoint causes the container to be killed and restarted in a loop.
- Browser CORS preflight (`OPTIONS` requests) — browsers send `OPTIONS` before cross-origin requests. A JWT middleware that returns 401 on `OPTIONS` (because there's no `Authorization` header) will block the preflight and cause all frontend requests to fail with a CORS error, not a 401. The browser will report a CORS failure, masking the actual auth error.

**Why it happens:**
Global middleware is the simplest place to add auth. It feels safe because "everything is protected." The edge cases (docs, health, preflight) are easy to forget.

**Consequences:**
- Swagger UI is inaccessible after JWT middleware is added — development slows significantly
- Container health probes fail, causing restart loops in production
- All frontend SSE requests fail with "CORS error" in browser console, making the real auth error invisible

**Prevention:**
Use per-route `Depends(require_auth)` everywhere. Maintain an explicit allowlist of unauthenticated routes: health, docs, OpenAPI, auth registration, and login. Never use global middleware for auth in FastAPI.

For routes that existed before auth was added (to allow a gradual rollout), use an `optional_auth` dependency that returns `None` for missing tokens instead of raising 401. This allows testing the pre-auth behavior during the transition.

**Detection (warning signs):**
- `GET /docs` returns 401 after JWT middleware is added
- Docker container repeatedly restarts (health check returning non-200)
- Browser DevTools shows "CORS error" on SSE requests that previously worked

**Phase:** Phase 1 auth implementation. Define the allowlist before enabling auth on any route.

---

## Moderate Pitfalls

Mistakes in this category cause correctness bugs or test failures that are diagnosable but time-consuming to fix.

---

### Pitfall 7: `_context_store` In-Memory Cache Becomes a Multi-User Security Hole

**What goes wrong:**
`context.py` uses `_context_store` as a module-level dict (write-through cache). Currently it stores `{project_id: context_data}` without any user association. After auth is introduced, two users from different organizations can have apps with different UUIDs — but if an app UUID is somehow guessed (UUIDs are not secret once they appear in API responses), `_context_store` will serve the cached context without re-checking authorization.

More concretely: the cache is warmed on the first `GET /api/context/{app_id}/status` call. If User A calls this and warms the cache, and then User B calls it with the same `app_id` (which they should not have access to), the current code returns from cache before hitting the DB authorization check — authorization would be in the DB query, but if the cache is checked first, the DB auth check is bypassed.

**Why it happens:**
The cache predates auth. It was designed for performance, not security. There is no TTL and no user scope.

**Consequences:**
- Cross-tenant data leakage via cache hit
- Auth guards on the route are bypassed for cached resources

**Prevention:**
After adding auth, always check authorization before touching the cache. Pattern:
1. Verify user has access to `app_id` (DB query)
2. If authorized, check cache
3. Return cache hit or DB result

Never check cache first. The cache is a performance optimization, not a data gate.

**Detection (warning signs):**
- Unit tests that mock `_context_store` skip authorization checks
- Two test users accessing the same app_id return identical cached responses

**Phase:** Phase 1 auth implementation. Audit every cache read-path in `context.py` and add auth check before cache access.

---

### Pitfall 8: `project_id` in Pydantic Request Bodies Creates an Authorization Bypass Vector

**What goes wrong:**
The current `ChatRequest` model takes `project_id: str` in the request body. After auth is added, the route handler will receive both the authenticated user's identity (from JWT) and the `project_id` from the request body. If the authorization check uses the body `project_id` directly without verifying the user has access to it, any authenticated user can pass any `project_id` and operate on any app.

This is the IDOR (Insecure Direct Object Reference) pattern. It is the most common auth mistake in REST APIs that add JWT auth after the fact.

The same vulnerability exists in: `POST /api/files/{project_id}/upload`, `POST /api/context/{project_id}/build`, `POST /api/requirements/{project_id}/extract`, `POST /api/mapping/{project_id}/run`.

**Why it happens:**
Auth middleware validates the JWT token (proves identity) but does not automatically prove resource access. Developers assume "authenticated = authorized."

**Consequences:**
- Authenticated user from Org A can trigger audits on Org B's apps by guessing UUIDs
- Chroma RAG context from another org's documents is returned to an unauthorized user
- Audit snapshots from another org's app are accessible

**Prevention:**
After extracting `current_user` from JWT, always look up the resource and verify the user's role against it before proceeding:

```python
app = await db.get(App, app_id)
if app is None:
    raise HTTPException(status_code=404)
await require_permission(db, current_user.id, "read", "app", app_id)
```

Never skip the permission check because "the app_id came from the request." The request body is attacker-controlled.

**Detection (warning signs):**
- Authorization tests only check "authenticated vs. unauthenticated," not "authenticated but wrong org"
- No test exists for: User A tries to access User B's app_id (should return 403, not 200)

**Phase:** Phase 1 RBAC core. Write cross-org access tests explicitly. They are more important than same-org tests.

---

### Pitfall 9: Alembic `autogenerate` Will Not Detect the New `users`, `roles`, and `user_roles` Tables Unless `env.py` Imports Their Models

**What goes wrong:**
`migrations/env.py` currently imports `Base` from `app.db.models` and does a `noqa` import of `app.db.requirements_models`. The `target_metadata = Base.metadata` line tells Alembic which tables to compare against the DB. If new models (`User`, `Role`, `UserRole`, `Organization`, `Project`) are defined in a new file (e.g., `app.db.auth_models`) but that file is not imported in `env.py`, Alembic will not include those tables in `autogenerate` diff — it will show no changes needed even though the tables don't exist.

This is a known Alembic footgun: `autogenerate` only sees models that have been imported before `Base.metadata` is read.

**Why it happens:**
Adding a new models file is not sufficient. `env.py` must explicitly import it. This is not enforced by any linter or test.

**Consequences:**
- `alembic revision --autogenerate` produces an empty migration
- Tables do not exist in DB
- First request to auth endpoint raises `sqlalchemy.exc.OperationalError: no such table: users`

**Prevention:**
Add a test that verifies `alembic check` passes after model changes. This test runs `alembic check` as a subprocess and asserts exit code 0. Any new models file must be added to `env.py` imports before its migration is generated.

**Detection (warning signs):**
- `alembic revision --autogenerate -m "add users"` generates an empty migration file
- `alembic check` reports "no changes" immediately after adding new ORM models

**Phase:** Phase 1 auth implementation, first migration. Check `env.py` imports as the first step.

---

### Pitfall 10: LlamaIndex Workflow `ctx.store` Is Request-Scoped — JWT Claims Cannot Be Stored There for Cross-Step Auth

**What goes wrong:**
The LlamaIndex Workflow context (`ctx.store`) is scoped to a single workflow run. It is appropriate for passing data between steps (ParsedDocsEvent → EmbeddedEvent, etc.). It is not a request-level context that persists across HTTP requests.

A tempting shortcut when adding auth to workflows is to inject the current user into `ctx.store.set("current_user", user)` and check it in each step. This works within a single workflow run. But if any workflow step spawns a sub-workflow or calls a service that makes its own DB query without the user context, that call is unauthenticated.

More importantly: the workflow steps in `audit_workflow.py`, `requirements_workflow.py`, and `mapping_workflow.py` call `ContextBuilder` methods directly. `ContextBuilder` is a module-level singleton (`_context_builder = ContextBuilder()` in `chat.py`). It has no concept of current user. After auth is added, calls from inside workflows to `ContextBuilder.build_with_sources()` will not enforce that the user is allowed to read the project's RAG context.

**Why it happens:**
Workflows were designed as stateless computation units. Adding identity to a stateless unit requires threading identity through every method signature, which is tedious and easy to forget in one place.

**Consequences:**
- Workflow steps can read RAG context for apps the user shouldn't access (if called directly with a different app_id)
- Authorization bypass is not detectable at the route level — the route is protected, but the internal service call is not

**Prevention:**
Pass `app_id` to all workflow methods and verify ownership before any DB or Chroma access. Do not use `ctx.store` as an auth context — it's a workflow data bus. Keep auth checks at the route boundary (route handler) and at service entry points (the first line of `ContextBuilder` methods and workflow entry steps).

**Detection (warning signs):**
- Workflow tests do not include a user fixture — they call workflows directly with any app_id
- `ContextBuilder.build_with_sources()` has no `user_id` parameter

**Phase:** Phase 1 RBAC core. Auth checks must exist at both the route level and the service level (ContextBuilder, workflow entry).

---

## Minor Pitfalls

---

### Pitfall 11: `compare_type=False` in Alembic Env Masks New Column Type Changes in New Auth Tables

**What goes wrong:**
`migrations/env.py` sets `compare_type=False` (documented as preventing false positives on SQLite TEXT/VARCHAR). This setting also suppresses type changes on new auth tables. If a `users.hashed_password` column is created as `String(60)` (bcrypt output is 60 chars) but later a migration changes it to `Text()`, Alembic autogenerate will not detect the type change.

This is minor because the auth tables are new (no existing data to corrupt), but it can mask type mistakes silently.

**Prevention:**
For auth-specific migrations, verify column types manually in the generated migration file before running. Do not rely on `autogenerate` to catch type changes.

**Phase:** Phase 1, all auth migrations.

---

### Pitfall 12: JWT Token Expiry Without Refresh Tokens Breaks Long-Running SSE Streams

**What goes wrong:**
PROJECT.md specifies no refresh tokens in Phase 1, with longer-lived access tokens instead. M1 context builds can run up to 30 minutes (`M1_WORKFLOW_TIMEOUT_SECONDS=1800`). If a token expires mid-stream, the backend will continue streaming (the SSE connection is already open), but the next request the frontend makes (e.g., polling `/api/context/{app_id}/status` after the build) will return 401.

The user's experience: the build appeared to succeed, but clicking "rebuild" or "view results" immediately returns an auth error. They are confused because they were "just using it."

**Why it happens:**
Token expiry is checked at connection time (the initial HTTP request). Once an SSE stream is open, the connection persists independently of the token. Token expiry only manifests on the next new request.

**Prevention:**
Set access token TTL to at least 2× the longest expected workflow duration (60+ minutes for Phase 1). Add a frontend interceptor that detects 401 responses and redirects to login. Make the 401 error message explicit: "Session expired. Please log in again."

**Detection (warning signs):**
- User completes a successful M1 build but gets 401 on the immediately following status poll
- Token TTL set to 15 minutes (a common default) with no refresh mechanism

**Phase:** Phase 1 auth, token configuration. Set TTL deliberately, document the decision.

---

### Pitfall 13: The Frontend `localStorage` Key Namespace Will Collide After Multi-User Support

**What goes wrong:**
`useAIBuddyChat.ts` uses `localStorage` to persist per-project chat history. The current key format is presumably based on `project_id` only. After multi-user auth is added, two users on the same browser (e.g., testing with two accounts) will share the same `localStorage` key and see each other's chat history.

**Prevention:**
Namespace localStorage keys by `user_id` or session token fingerprint: `ai_buddy_chat_{userId}_{appId}`.

**Phase:** Phase 1 frontend auth. Update localStorage key construction when token storage is added.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Entity rename migration | FK constraint corruption in SQLite with `render_as_batch` | Batch-migrate every child table individually; run `PRAGMA foreign_key_check` |
| Entity rename: non-DB surfaces | Silent breakage in SSE payloads, Pydantic field names, file paths, test fixtures | Full-repo grep before starting; atomic single-PR rename |
| Chroma collection naming | Existing RAG indexes unreachable after rename | One-time Python migration script to copy Chroma collections before code rename |
| JWT middleware placement | Body consumed by middleware, causing 422 on SSE endpoints | Use `Depends(require_auth)` per-route, never app-level middleware for auth |
| IDOR on resource routes | Authenticated user accessing another org's app_id | Explicit permission check after JWT validation, before any business logic |
| Permission hierarchy resolver | N+1 DB queries per SSE request, possible recursion | Request-scoped memoization from day one; depth limit in hierarchy walker |
| New ORM models for auth | Alembic autogenerate produces empty migration | Import new models file in `migrations/env.py` before running autogenerate |
| `_context_store` cache | Auth check bypassed via cache hit | Always authorize before reading from cache, not after |
| Token TTL | 401 errors mid-workflow for long M1/Faza 2 runs | Set TTL ≥ 2× `M1_WORKFLOW_TIMEOUT_SECONDS`; explicit session-expired UI message |
| Frontend localStorage | Multi-user session collision | Namespace keys by user ID from the start |

---

## Sources

- Codebase analysis: `backend/app/db/models.py`, `backend/migrations/versions/001_initial_schema.py`, `backend/migrations/env.py`, `backend/app/api/routes/chat.py`, `backend/app/api/routes/projects.py`, `backend/app/rag/context_builder.py` — confidence HIGH
- `.planning/PROJECT.md` — project requirements and constraints — confidence HIGH
- `.planning/codebase/CONCERNS.md` — existing tech debt and fragile areas — confidence HIGH
- FastAPI dependency injection for auth (established pattern, training data) — confidence HIGH
- Alembic `render_as_batch` SQLite FK behavior (established limitation, training data) — confidence HIGH
- IDOR pattern in REST APIs with added auth (established security pattern) — confidence HIGH
