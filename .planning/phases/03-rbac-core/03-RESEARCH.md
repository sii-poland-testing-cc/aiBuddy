# Phase 3: RBAC Core - Research

**Researched:** 2026-03-30
**Domain:** FastAPI dependency injection, SQLAlchemy async ORM, permission resolver pattern, SSE guards, Alembic migration
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Permission Action Vocabulary**
- D-01: `can_user()` uses 3 action strings: `read`, `write`, `delete`. Mapping: GET endpoints → `read`; POST/PATCH → `write`; DELETE → `delete`.
- D-02: Hardcoded permission map for 3 built-in roles:
  - `org_admin`: read + write + delete on all resources in their org
  - `workspace_member`: read + write on workspace and all its projects
  - `project_viewer`: read only on specific project
- D-03: Phase 5 adds `manage_users` action to the `permissions` table — the 3-action vocab here does not conflict.

**Route Guarding Pattern**
- D-04: Router-level auth: each route file uses `router = APIRouter(dependencies=[Depends(get_current_user)])`. This ensures all routes in a file require authentication without repeating `Depends(get_current_user)` on every handler.
- D-05: Per-handler permission: `require_permission('action', 'resource_type')` factory returns a Depends callable added to each handler signature. FastAPI's dependency cache ensures `get_current_user` runs once per request.
- D-06: Routes without a `project_id` path param (e.g. `GET /api/projects/`, `POST /api/projects/`) use org-scoped permission: `require_permission('read', 'organization')` and `require_permission('write', 'organization')` respectively.

**SSE Guards**
- D-07: SSE route handlers add `_: None = Depends(require_permission('write', 'project'))` in the handler signature. FastAPI resolves all Depends before executing the generator — 403 is raised before any streaming begins.
- D-08: The `_context_store` cache in `context.py` is correctly guarded because `require_permission` fires via Depends before the route body executes.

**ENFORCE_AUTH=false Behavior**
- D-09: When `ENFORCE_AUTH=false`, `get_current_user()` returns `AnonymousUser`. `require_permission()` must also bypass its check when `ENFORCE_AUTH=false` — returns `None` without querying the DB. Preserves existing test suite with zero modifications.

**Superadmin Bootstrap (moved from Phase 4)**
- D-10: `POST /api/auth/bootstrap` added to auth router in Phase 3. Creates first superadmin when `users` table is empty. Returns 409 if any user already exists. Open endpoint (no auth required).

**ORM Model File**
- D-11: `Role` and `UserRole` ORM models go in new `backend/app/db/rbac_models.py`. Imported in `engine.py` and `migrations/env.py` as side-effect imports.

**Migration**
- D-12: Single Alembic migration `007_add_rbac_tables.py` with `down_revision = "006"`. Steps: (1) create `roles` table, (2) seed 3 built-in roles, (3) create `user_roles` table with composite index on `(user_id, resource_type, resource_id)`.

**Permission Memoization**
- D-13: Request-scoped memoization via `request.state` dict: `can_user()` stores results keyed by `(user_id, action, resource_type, resource_id)` in `request.state.rbac_cache`. Second call for the same tuple skips DB query.

**Test Strategy**
- D-14: Two new test files:
  - `backend/tests/test_rbac_unit.py` — Direct unit tests for `can_user()` with seeded DB data.
  - `backend/tests/test_rbac_integration.py` — HTTP integration tests with `ENFORCE_AUTH=true` and seeded users+roles.

### Claude's Discretion
- Exact SQL for the composite index on `user_roles` (name, column order within index)
- Whether `can_user()` lives in `app.core.rbac` or `app.core.auth` (new module preferred for separation)
- Error message wording for 401 vs 403 responses (defined in UI-SPEC: "Nieautoryzowany dostęp. Zaloguj się, aby kontynuować." / "Brak uprawnień do tego zasobu." / "Brak uprawnień do uruchomienia tej operacji.")
- Whether to add a `description` field to `roles` table (omit)

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| RBAC-01 | `roles` table seeded with: `org_admin`, `workspace_member`, `project_viewer` | Migration 007 creates table + seeds 3 rows via `op.bulk_insert` |
| RBAC-02 | `user_roles` table (user_id FK, role_id FK, resource_type ENUM, resource_id UUID); composite index on `(user_id, resource_type, resource_id)` | Migration 007 step 3; `rbac_models.py` ORM |
| RBAC-03 | `can_user(user_id, action, resource_type, resource_id)` implementing inheritance chain | `app/core/rbac.py` new module; DB queries using `AsyncSession` |
| RBAC-04 | Request-scoped permission memoization | `request.state.rbac_cache` dict; `can_user()` checks before DB query |
| RBAC-05 | Hardcoded permission map for 3 built-in roles | Python dict constant in `app/core/rbac.py` |
| RBAC-06 | `require_permission(action, resource_type)` FastAPI `Depends()` callable; raises 403 on denial | Factory function returning an async Depends callable |
| RBAC-07 | All existing API routes guarded (8 route files) | `router = APIRouter(dependencies=[Depends(get_current_user)])` in each file |
| RBAC-08 | SSE route guards placed in `Depends` chain before stream generator | `_: None = Depends(require_permission(...))` in handler signature |
| RBAC-09 | IDOR protection — `project_id` in route params checked against user's accessible resources | `can_user()` with `resource_type='project'` and `resource_id=project_id` returns False → 403 |
</phase_requirements>

---

## Summary

Phase 3 is a pure backend phase: no frontend changes, no new UI pages. The work falls into four interlocking areas: (1) ORM + migration for the RBAC tables, (2) the `can_user()` permission resolver with hierarchy traversal, (3) `require_permission()` FastAPI dependency wired onto all 8 route files, and (4) the superadmin bootstrap endpoint.

The codebase already has all the scaffolding this phase needs. Phase 2 delivered `get_current_user()` with `ENFORCE_AUTH` bypass, `AnonymousUser` dataclass, `User` ORM model, and the `auth.py` route file. Phase 1 delivered `Organization`, `Workspace`, `DEFAULT_ORG_ID`, `Project.organization_id`, and `Project.workspace_id`. The established patterns for model files (`hierarchy_models.py`, `auth_models.py`), migration files (`005_`, `006_`), and engine side-effect imports are all present and must be replicated for `rbac_models.py` + migration `007_`.

The trickiest part is the SSE guard: FastAPI resolves all `Depends()` in the handler signature *before* the response generator is invoked, so placing `_: None = Depends(require_permission('write', 'project'))` in the handler signature (not inside the generator) guarantees 403 fires before any LLM tokens are consumed. This is the correct and verified pattern.

**Primary recommendation:** Implement `can_user()` in a new `app/core/rbac.py` module. Keep the DB query path minimal (one `SELECT` per (user_id, resource_type, resource_id) tuple, memoized on `request.state`). Guard SSE routes by adding the `Depends` to the handler signature — never inside the async generator.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | Already installed | Dependency injection via `Depends()` | Project standard |
| SQLAlchemy async | Already installed | Async ORM for `roles` / `user_roles` queries | Project standard |
| Alembic | Already installed | Migration `007_add_rbac_tables.py` | Established in Phase 1+2 |
| PyJWT | Already installed | JWT decode in `get_current_user()` | Phase 2 |
| pwdlib/argon2 | Already installed | Password hash for bootstrap endpoint | Phase 2 |

### Supporting

No new packages required. All dependencies are already in the project.

**Version verification:** No new packages — skip npm/pip version checks.

---

## Architecture Patterns

### Recommended Project Structure (new files only)

```
backend/
├── app/
│   ├── core/
│   │   └── rbac.py          # can_user() + require_permission() factory
│   └── db/
│       └── rbac_models.py   # Role + UserRole ORM models
└── migrations/versions/
    └── 007_add_rbac_tables.py
```

### Pattern 1: ORM Model File (`rbac_models.py`)

**What:** Follows the established `hierarchy_models.py` / `auth_models.py` pattern. Two classes: `Role` (static seed data) and `UserRole` (junction table).

**When to use:** Any new set of related DB tables.

```python
# backend/app/db/rbac_models.py  (pattern from auth_models.py)
import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.db.models import Base

class Role(Base):
    __tablename__ = "roles"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

class UserRole(Base):
    __tablename__ = "user_roles"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(
        String, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[str] = mapped_column(
        String, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    resource_type: Mapped[str] = mapped_column(String, nullable=False)  # organization|workspace|project
    resource_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    __table_args__ = (
        Index("ix_user_roles_lookup", "user_id", "resource_type", "resource_id"),
    )
```

Source: Verified against `backend/app/db/auth_models.py` and `hierarchy_models.py` patterns.

### Pattern 2: Permission Resolver (`app/core/rbac.py`)

**What:** `can_user()` async function performs DB lookup with hierarchy traversal. `require_permission()` is a factory returning a `Depends`-compatible async callable. Both respect `ENFORCE_AUTH=false` by returning early.

**When to use:** Called from all route handlers via FastAPI's dependency injection.

```python
# backend/app/core/rbac.py
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import get_current_user, AnonymousUser
from app.core.config import settings
from app.db.engine import get_db
from app.db.models import Project
from app.db.rbac_models import Role, UserRole

# Hardcoded permission map (replaced by DB-driven in Phase 5)
ROLE_PERMISSIONS: dict[str, set[str]] = {
    "org_admin":         {"read", "write", "delete"},
    "workspace_member":  {"read", "write"},
    "project_viewer":    {"read"},
}

async def can_user(
    user_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    db: AsyncSession,
    request: Request,
) -> bool:
    """
    Permission resolver with hierarchy traversal.
    Checks: project role → workspace role → org role → superadmin.
    Results are memoized on request.state.rbac_cache for the lifetime of the request.
    """
    if not settings.ENFORCE_AUTH:
        return True

    # Superadmin bypass (check User.is_superadmin before DB query)
    # user object is already resolved by get_current_user; pass it in or re-fetch

    cache_key = (user_id, action, resource_type, resource_id)
    if not hasattr(request.state, "rbac_cache"):
        request.state.rbac_cache = {}
    if cache_key in request.state.rbac_cache:
        return request.state.rbac_cache[cache_key]

    # ... DB query + hierarchy traversal ...
    result = await _resolve(user_id, action, resource_type, resource_id, db)
    request.state.rbac_cache[cache_key] = result
    return result

def require_permission(action: str, resource_type: str):
    """
    Factory returning a FastAPI Depends callable.
    Usage: _: None = Depends(require_permission('write', 'project'))
    """
    async def _check(
        request: Request,
        project_id: str | None = None,   # path param, may be absent
        current_user=Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> None:
        if not settings.ENFORCE_AUTH:
            return None
        # Determine resource_id from path param or org-level default
        # ...
        allowed = await can_user(current_user.id, action, resource_type, resource_id, db, request)
        if not allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                detail="Brak uprawnień do tego zasobu.")
    return _check
```

Source: Verified against FastAPI Depends documentation patterns and `app/core/auth.py` ENFORCE_AUTH bypass pattern.

### Pattern 3: Router-Level Auth Guard

**What:** Each of the 8 route files adds `dependencies=[Depends(get_current_user)]` to the `APIRouter` constructor. This ensures 401 fires for all routes in the file without modifying each handler.

**When to use:** When all routes in a file require authentication (all 8 route files in this project).

```python
# Before (Phase 2 state):
router = APIRouter()

# After (Phase 3):
from fastapi import APIRouter, Depends
from app.core.auth import get_current_user

router = APIRouter(dependencies=[Depends(get_current_user)])
```

**Critical:** `auth.py` routes (`register`, `login`, `logout`, `bootstrap`) must NOT get the auth dependency — they are open endpoints. `me` endpoint already uses `Depends(get_current_user)` in the handler signature, which is fine to keep. Only the 7 non-auth route files get the router-level guard.

Source: FastAPI docs on router-level dependencies; verified against `app/api/routes/auth.py` which must stay unguarded.

### Pattern 4: SSE Guard via Handler Signature Depends

**What:** SSE endpoints return `StreamingResponse` wrapping an async generator. Once `StreamingResponse` is returned and the HTTP response begins, you cannot change the status code. Therefore, permission must be checked *before* the generator is invoked. FastAPI resolves all `Depends()` in the handler signature before calling the handler body — including before returning `StreamingResponse`.

**When to use:** All 4 SSE endpoints: `POST /api/context/{project_id}/build`, `POST /api/chat/stream`, `POST /api/requirements/{project_id}/extract`, `POST /api/mapping/{project_id}/run`.

```python
# backend/app/api/routes/context.py (SSE guard pattern)
@router.post("/{project_id}/build")
async def build_context(
    project_id: str,
    files: List[UploadFile] = File(...),
    mode: str = Query("append", pattern="^(append|rebuild)$"),
    _: None = Depends(require_permission("write", "project")),  # <-- resolves BEFORE generator
):
    # Permission already verified by Depends chain
    return StreamingResponse(_run_m1(project_id, file_paths, mode), ...)
```

**Why it works:** FastAPI's dependency resolution is synchronous with handler invocation. The generator `_run_m1(...)` is not called until the handler returns `StreamingResponse(...)`. If `require_permission` raises `HTTPException(403)` in the `Depends` chain, the handler body never executes and no `StreamingResponse` is created.

Source: Verified against FastAPI source and `app/api/routes/context.py` existing handler signature patterns.

### Pattern 5: Hierarchy Traversal in `can_user()`

**What:** When `resource_type='project'`, fetch the project row to get `organization_id` and `workspace_id`. Check role chain: project → workspace (if not null) → org → superadmin.

**When to use:** Anytime `resource_type='project'` is checked. `workspace` and `organization` resource types only need to traverse upward (workspace → org).

```python
async def _resolve(user_id, action, resource_type, resource_id, db) -> bool:
    # 1. Direct role on this resource
    if await _has_role_with_action(user_id, action, resource_type, resource_id, db):
        return True

    if resource_type == "project":
        project = await db.get(Project, resource_id)
        if not project:
            return False  # unknown project → deny (IDOR protection)
        # 2. Workspace role (if project has workspace)
        if project.workspace_id:
            if await _has_role_with_action(user_id, action, "workspace", project.workspace_id, db):
                return True
        # 3. Org role
        if project.organization_id:
            if await _has_role_with_action(user_id, action, "organization", project.organization_id, db):
                return True

    elif resource_type == "workspace":
        workspace = await db.get(Workspace, resource_id)
        if workspace and await _has_role_with_action(user_id, action, "organization", workspace.organization_id, db):
            return True

    return False

async def _has_role_with_action(user_id, action, resource_type, resource_id, db) -> bool:
    stmt = (
        select(UserRole)
        .join(Role, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == user_id,
            UserRole.resource_type == resource_type,
            UserRole.resource_id == resource_id,
        )
    )
    rows = (await db.execute(stmt)).scalars().all()
    for ur in rows:
        role = await db.get(Role, ur.role_id)
        if role and action in ROLE_PERMISSIONS.get(role.name, set()):
            return True
    return False
```

Source: Derived from CONTEXT.md D-02/D-03 and `hierarchy_models.py` `Project.organization_id`/`workspace_id` columns verified in `models.py`.

### Pattern 6: Alembic Migration with Data Seeding

**What:** Migration 007 creates `roles` and `user_roles` tables, then seeds the 3 built-in role rows. Follows the established pattern from `005_` and `006_`.

```python
# backend/migrations/versions/007_add_rbac_tables.py
revision = "007"
down_revision = "006"

def upgrade() -> None:
    # Step 1: Create roles table
    op.create_table("roles", ...)

    # Step 2: Seed 3 built-in roles (data seed in migration — established pattern)
    op.bulk_insert(
        sa.table("roles",
            sa.column("id", sa.String()),
            sa.column("name", sa.String()),
            sa.column("created_at", sa.DateTime(timezone=True)),
        ),
        [
            {"id": "...", "name": "org_admin", "created_at": datetime.utcnow()},
            {"id": "...", "name": "workspace_member", "created_at": datetime.utcnow()},
            {"id": "...", "name": "project_viewer", "created_at": datetime.utcnow()},
        ]
    )

    # Step 3: Create user_roles table
    op.create_table("user_roles", ...)
    op.create_index("ix_user_roles_lookup", "user_roles",
                    ["user_id", "resource_type", "resource_id"])
```

Source: Verified against `006_add_users_table.py` migration pattern.

### Pattern 7: Bootstrap Endpoint

**What:** `POST /api/auth/bootstrap` is open (no auth), checks users table is empty, creates superadmin. Added to `auth.py` router WITHOUT the router-level auth guard (auth router stays unguarded).

**Idempotency guard:** `SELECT COUNT(*) FROM users` — if > 0, return 409.

```python
@router.post("/bootstrap", status_code=201)
async def bootstrap_superadmin(body: BootstrapRequest, db: AsyncSession = Depends(get_db)):
    count = (await db.execute(select(func.count(User.id)))).scalar_one()
    if count > 0:
        raise HTTPException(409, detail="Konto superadmina już istnieje.")
    user = User(email=body.email, hashed_password=hash_password(body.password), is_superadmin=True)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"user_id": user.id, "email": user.email, "message": "Konto superadmina zostało utworzone."}
```

Source: UI-SPEC `03-UI-SPEC.md` copywriting contract; `auth.py` existing patterns.

### Anti-Patterns to Avoid

- **Placing permission check inside the SSE generator:** If `require_permission()` is called inside `_run_workflow()` (the async generator), the HTTP 200 response may already have been sent with `media_type="text/event-stream"` before the check runs. The status code cannot be changed after streaming begins.
- **Using middleware for auth instead of `Depends`:** Middleware runs before FastAPI's dependency resolution but cannot access route path parameters. Per-route `Depends` is the correct pattern for project-scoped permission checks. This is also why Phase 2 chose `Depends` over middleware.
- **Forgetting `ENFORCE_AUTH` bypass in `require_permission()`:** `get_current_user()` already bypasses when `ENFORCE_AUTH=false`, but `require_permission()` must also bypass independently — otherwise an `AnonymousUser` (id="anonymous") would hit the DB lookup and fail.
- **Shared `AnonymousUser` id in memoization cache:** The `request.state.rbac_cache` key includes `user_id`. When `ENFORCE_AUTH=false`, the bypass fires before any cache logic, so "anonymous" never gets stored. This is correct behavior.
- **Adding auth dependency to `auth.py` router:** `register`, `login`, `logout`, and `bootstrap` are open endpoints. Adding `dependencies=[Depends(get_current_user)]` to the auth router would break login (chicken-and-egg). Auth router stays at `router = APIRouter()` with no router-level dependency.
- **`op.bulk_insert` with timezone-aware datetime in SQLite:** SQLite stores DateTime as TEXT. Use `datetime.utcnow()` (naive) for migration seed data; the ORM `DateTime(timezone=True)` handles conversion at read time. Match existing migration `006_` behavior.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Request-scoped cache | Custom middleware cache class | `request.state` dict (FastAPI built-in) | Zero deps, correct lifetime — `request.state` is garbage collected with the request |
| Dependency caching | Manually checking if user was already fetched | FastAPI's built-in Depends caching | FastAPI caches Depends by identity within a request automatically |
| Permission hierarchy | Custom graph traversal library | Direct async SQLAlchemy SELECT with 2-3 queries | The hierarchy is at most 3 levels deep (project → workspace → org); a graph library adds complexity without benefit |
| Role seeding | Separate seed script / management command | Alembic migration data seed | Keeps schema + seed data co-located; already the project pattern (see migration 005 for org seed) |

**Key insight:** FastAPI's `Depends` is the right abstraction for both authentication and authorization. Attempting to move permission checks to middleware or a separate interceptor loses access to path parameters and FastAPI's dependency caching.

---

## Runtime State Inventory

> Skipped — Phase 3 is a greenfield addition of new tables and a new module. No rename or migration of existing runtime state is involved.

---

## Common Pitfalls

### Pitfall 1: SSE Status Code Lock-In

**What goes wrong:** Permission check runs inside the async generator after `StreamingResponse` is already returned. The first `yield` from the generator causes FastAPI to flush the HTTP headers (200 OK + `text/event-stream`). Any `HTTPException(403)` raised after that is swallowed — the client sees a 200 with a garbled SSE body.

**Why it happens:** `StreamingResponse` starts the HTTP response immediately when the handler returns it, before the generator yields anything. But if the generator contains the permission check, it's already "inside" the 200 response.

**How to avoid:** Always place `_: None = Depends(require_permission(...))` in the **handler function signature**, never inside `_run_workflow()` or any generator.

**Warning signs:** Tests that expect a 403 on an SSE endpoint instead get a 200 with error SSE events in the body.

### Pitfall 2: FastAPI Dependency Caching Identity

**What goes wrong:** `require_permission('write', 'project')` is called twice in different places (router-level + handler-level). If they resolve different `Depends(get_current_user)` instances, FastAPI may call `get_current_user()` twice per request.

**Why it happens:** FastAPI caches `Depends` by the exact callable object identity. Two separate `Depends(get_current_user)` with the same function reference share one cached result per request.

**How to avoid:** Import `get_current_user` from `app.core.auth` in `rbac.py` and use it directly — do not create a local wrapper. FastAPI will recognize it as the same callable and reuse the cached result from the router-level dependency.

**Warning signs:** DB logs showing two `SELECT users WHERE id = ?` per request.

### Pitfall 3: Alembic Autogenerate Misses ORM Model

**What goes wrong:** Running `alembic autogenerate` produces an empty migration because `rbac_models.py` was not imported in `migrations/env.py`.

**Why it happens:** Alembic's `autogenerate` only sees tables that are registered with `Base.metadata` at import time. Side-effect imports in `env.py` are the established mechanism.

**How to avoid:** Add `import app.db.rbac_models  # noqa: F401` to both `migrations/env.py` and `backend/app/db/engine.py` before running any migration operations.

**Warning signs:** `alembic check` reports no drift even though roles/user_roles tables don't exist.

### Pitfall 4: `require_permission` Without `project_id` on Org-Scoped Routes

**What goes wrong:** `require_permission('read', 'project')` used on `GET /api/projects/` (which has no `project_id` path param). The resolver cannot determine `resource_id` — it defaults to a nonsensical value or throws an error.

**Why it happens:** The factory function attempts to read a path param that doesn't exist.

**How to avoid:** Per D-06, list/create project routes use `require_permission('read', 'organization')` with `DEFAULT_ORG_ID` as the `resource_id` for Phase 3 (before per-org project ownership is enforced). The `require_permission` factory must distinguish org-scoped vs project-scoped calls.

**Warning signs:** `GET /api/projects/` returns 422 or 500 because `project_id` is missing.

### Pitfall 5: Test Isolation with ENFORCE_AUTH=true

**What goes wrong:** Integration tests with `ENFORCE_AUTH=true` share the same SQLite test DB across tests. A seeded user+role from test A affects test B.

**Why it happens:** The `app_client` fixture reuses a single in-memory SQLite DB for the session. Tests that add users/roles pollute subsequent tests.

**How to avoid:** Use function-scoped fixtures for user/role seeding in `test_rbac_integration.py`. Clean up with `DELETE FROM user_roles` / `DELETE FROM users` at teardown. Or use a separate DB per test (more expensive). Alternatively, make each test self-contained with unique emails.

**Warning signs:** Tests pass in isolation but fail in full suite runs.

### Pitfall 6: IDOR via Workspace-level Traversal

**What goes wrong:** User A has `workspace_member` role on Workspace X. Project P is in Workspace X but belongs to a *different* org. User A can read Project P even though they have no relationship to that org.

**Why it happens:** If `can_user()` only checks workspace membership without verifying the workspace belongs to an org the user has access to, cross-org access is possible.

**How to avoid:** In Phase 3 with a single default org, this is not a risk (all resources are in `DEFAULT_ORG_ID`). Document it as a Phase 6 concern (`ADV-04`). The `project → workspace → org` chain naturally prevents this when org-level isolation is enforced at the query level in Phase 6.

**Warning signs:** `test_rbac_integration.py` IDOR test: User A in Org A with project_viewer role on Project P in Org A can access Project Q in Org B by guessing its UUID.

---

## Code Examples

Verified patterns from existing codebase:

### Engine Side-Effect Import Pattern
```python
# backend/app/db/engine.py (existing pattern — add rbac_models here)
import app.db.requirements_models  # noqa: F401
import app.db.hierarchy_models     # noqa: F401
import app.db.auth_models          # noqa: F401
# ADD:
import app.db.rbac_models          # noqa: F401
```
Source: `backend/app/db/engine.py` lines 21-23 (verified).

### conftest.py ENFORCE_AUTH Pattern
```python
# backend/tests/conftest.py (existing)
os.environ.setdefault("ENFORCE_AUTH", "false")
```
Phase 3 `test_rbac_integration.py` will need to temporarily override this to `"true"` for auth tests. Use `monkeypatch.setenv("ENFORCE_AUTH", "true")` or a separate fixture that patches `settings.ENFORCE_AUTH = True`.

Source: `backend/tests/conftest.py` line 15 (verified).

### auth.py test patching pattern (Phase 2 lesson)
```python
# From STATE.md decision: "auth_enabled test fixture must patch auth_mod.settings directly"
# When testing with ENFORCE_AUTH=true, patch the settings object in the module that imports it
import app.core.auth as auth_mod
monkeypatch.setattr(auth_mod, "settings", FakeSettings(ENFORCE_AUTH=True, ...))
```
Source: `.planning/STATE.md` accumulated decisions (Phase 2 auth plan 02).

### Existing chat_stream handler — target for SSE guard
```python
# backend/app/api/routes/chat.py (current state — no auth)
@router.post("/stream")
async def chat_stream(req: ChatRequest):
    return StreamingResponse(_run_workflow(req), media_type="text/event-stream", ...)
```
After Phase 3:
```python
@router.post("/stream")
async def chat_stream(
    req: ChatRequest,
    _: None = Depends(require_permission("write", "project")),
):
    return StreamingResponse(_run_workflow(req), media_type="text/event-stream", ...)
```
Note: `chat_stream` takes `project_id` from `req.project_id` (request body), not a path param. The `require_permission` factory must handle this case — extract `project_id` from the request body OR make `chat_stream` pass `project_id` explicitly.

Source: `backend/app/api/routes/chat.py` lines 51-65 (verified). This is the **only** SSE route where `project_id` comes from the request body rather than a path parameter — the `require_permission` factory needs to handle this or `chat_stream` passes resource_id explicitly.

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Global middleware auth | Per-route `Depends(get_current_user)` | Phase 2 decision | SSE compatibility; path params accessible |
| Hard-coded permission logic per route | Centralized `can_user()` resolver | Phase 3 (this phase) | Single place to audit/change permission logic |
| DB-driven permissions | Hardcoded dict (Phase 3) → DB-driven (Phase 5) | Phase 3 design | Ships working auth fast; upgradeable without route changes |

---

## Open Questions

1. **`chat.py` SSE: `project_id` in request body, not path param**
   - What we know: `POST /api/chat/stream` takes a `ChatRequest` body with `project_id: str`. The `require_permission` factory reads path params by default. This route has no `{project_id}` in the URL path.
   - What's unclear: The factory signature needs to handle body-based resource IDs. Options: (a) `require_permission` accepts an optional `project_id_source: Literal["path", "body"]` parameter; (b) `chat_stream` extracts `project_id` from the validated body and passes it to a direct `can_user()` call inside the handler (before the `StreamingResponse` is created); (c) keep `require_permission` path-only and add a manual `can_user()` call in `chat_stream` body.
   - Recommendation: Option (b) — call `can_user()` directly inside `chat_stream` before `return StreamingResponse(...)`. This is simpler than overloading the factory. The guard fires before the generator starts because the `StreamingResponse` constructor is not yet called. This is consistent with D-07's intent (403 before stream) even if the mechanism is slightly different from the other SSE routes.

2. **Seeded role IDs: static UUIDs vs generated**
   - What we know: Migration must insert 3 role rows. The `role_id` FK in `user_roles` must reference these rows. Future code may hardcode role lookup by name (not ID).
   - What's unclear: Whether to use static predictable UUIDs (like `DEFAULT_ORG_ID = "00000000-..."`) or generated UUIDs.
   - Recommendation: Use static deterministic UUIDs for the 3 built-in roles (e.g., `"role-org-admin-000000000001"`, etc.), consistent with `DEFAULT_ORG_ID` pattern. This allows `can_user()` and test fixtures to reference roles by ID without an extra SELECT.

3. **`conftest.py` seeding for RBAC integration tests**
   - What we know: `conftest.py` uses `INSERT OR IGNORE` to seed the default org. Integration tests with `ENFORCE_AUTH=true` need seeded users with known passwords and role assignments.
   - What's unclear: Whether to extend conftest with RBAC-specific fixtures or keep them local to `test_rbac_integration.py`.
   - Recommendation: Keep RBAC seeding local to `test_rbac_integration.py` with function-scoped fixtures. The global `conftest.py` should not be RBAC-aware to preserve separation of concerns.

---

## Environment Availability

> Step 2.6: SKIPPED — Phase 3 is purely backend code/config with no new external dependencies. All required tools (Python, pytest, Alembic, SQLite) are already verified present from Phases 1 and 2.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | `backend/pytest.ini` or `pyproject.toml` (existing) |
| Quick run command | `pytest tests/test_rbac_unit.py -v` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| RBAC-01 | `roles` table exists with 3 seeded rows | unit | `pytest tests/test_rbac_unit.py::test_roles_seeded -x` | Wave 0 |
| RBAC-02 | `user_roles` table exists with composite index | unit | `pytest tests/test_rbac_unit.py::test_user_roles_schema -x` | Wave 0 |
| RBAC-03 | `can_user()` returns True for org_admin on all actions | unit | `pytest tests/test_rbac_unit.py::test_can_user_org_admin -x` | Wave 0 |
| RBAC-03 | `can_user()` traverses hierarchy: project → workspace → org | unit | `pytest tests/test_rbac_unit.py::test_can_user_hierarchy -x` | Wave 0 |
| RBAC-04 | Memoization skips second DB call | unit | `pytest tests/test_rbac_unit.py::test_memoization -x` | Wave 0 |
| RBAC-05 | `project_viewer` denied on write action | unit | `pytest tests/test_rbac_unit.py::test_project_viewer_deny_write -x` | Wave 0 |
| RBAC-06 | `require_permission` raises 403 on denial | integration | `pytest tests/test_rbac_integration.py::test_403_no_role -x` | Wave 0 |
| RBAC-07 | Unauthenticated request to guarded route → 401 | integration | `pytest tests/test_rbac_integration.py::test_401_no_token -x` | Wave 0 |
| RBAC-07 | All existing tests pass with ENFORCE_AUTH=false | regression | `pytest tests/ -v` (conftest sets ENFORCE_AUTH=false) | Existing |
| RBAC-08 | SSE endpoint returns 403 before stream starts | integration | `pytest tests/test_rbac_integration.py::test_sse_403_before_stream -x` | Wave 0 |
| RBAC-09 | IDOR: User A cannot access User B's project | integration | `pytest tests/test_rbac_integration.py::test_idor_403 -x` | Wave 0 |
| D-10 | Bootstrap creates superadmin when empty | integration | `pytest tests/test_rbac_integration.py::test_bootstrap_success -x` | Wave 0 |
| D-10 | Bootstrap returns 409 when users exist | integration | `pytest tests/test_rbac_integration.py::test_bootstrap_409 -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_rbac_unit.py -v`
- **Per wave merge:** `pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_rbac_unit.py` — covers RBAC-01 through RBAC-05
- [ ] `tests/test_rbac_integration.py` — covers RBAC-06 through RBAC-09 + bootstrap

*(Existing test infrastructure: pytest, conftest.py, app_client fixture — all in place)*

---

## Project Constraints (from CLAUDE.md)

| Constraint | Source | Impact on Phase 3 |
|------------|--------|-------------------|
| SQLAlchemy 2.0 Mapped API | CLAUDE.md architecture | `Role` and `UserRole` models use `Mapped[str]`, `mapped_column` |
| LlamaIndex Workflow Context API: `ctx.store.set/get` (not `ctx.set/get`) | CLAUDE.md LlamaIndex section | No new workflows in Phase 3 — N/A |
| Alembic for all schema changes | CLAUDE.md DB schema section | Migration `007_add_rbac_tables.py` required |
| `render_as_batch=True` in env.py | CLAUDE.md migrations/env.py | Already configured; any `batch_alter_table` calls will work |
| `ENFORCE_AUTH` env flag (default true) | CLAUDE.md / REQUIREMENTS.md | `require_permission()` must bypass when `ENFORCE_AUTH=false` |
| Backend tests use `ENFORCE_AUTH=false` via conftest | CLAUDE.md tests section | Existing test suite must pass unchanged; new RBAC tests set `ENFORCE_AUTH=true` explicitly |
| `AsyncSessionLocal` available for direct DB use | CLAUDE.md key files | `can_user()` uses injected `AsyncSession` from `Depends(get_db)` |
| All route files follow `router = APIRouter()` pattern | CLAUDE.md key files | Phase 3 changes these to `APIRouter(dependencies=[...])` |

---

## Sources

### Primary (HIGH confidence)
- `backend/app/core/auth.py` — `get_current_user()`, `AnonymousUser`, ENFORCE_AUTH pattern (verified directly)
- `backend/app/db/auth_models.py`, `hierarchy_models.py` — ORM model patterns (verified directly)
- `backend/app/db/engine.py` — side-effect import pattern (verified directly)
- `backend/migrations/env.py` — migration environment, `render_as_batch=True` (verified directly)
- `backend/migrations/versions/006_add_users_table.py` — migration structure and `down_revision` chain (verified directly)
- `backend/app/api/routes/context.py`, `chat.py` — SSE handler patterns (verified directly)
- `backend/app/main.py` — router registration, no main.py changes needed (verified directly)
- `backend/tests/conftest.py` — ENFORCE_AUTH bypass, app_client fixture (verified directly)
- `.planning/phases/03-rbac-core/03-CONTEXT.md` — locked decisions D-01 through D-14 (verified directly)
- `.planning/phases/03-rbac-core/03-UI-SPEC.md` — error message copywriting contract (verified directly)

### Secondary (MEDIUM confidence)
- FastAPI documentation on router-level `dependencies=` parameter — well-established pattern; CONTEXT.md D-04 confirms this is the chosen approach
- FastAPI SSE + Depends resolution order — confirmed by D-07 in CONTEXT.md and consistent with FastAPI behavior where Depends are resolved before handler body executes

### Tertiary (LOW confidence)
- None

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages; all tools verified in prior phases
- Architecture: HIGH — patterns verified directly against existing codebase; locked decisions from CONTEXT.md are precise
- Pitfalls: HIGH — SSE pitfall and ENFORCE_AUTH bypass are documented in STATE.md and CONTEXT.md; others derived from direct code inspection
- Open questions: MEDIUM — body-based project_id in chat.py is a real implementation ambiguity requiring a decision

**Research date:** 2026-03-30
**Valid until:** 2026-06-30 (stable stack — no fast-moving dependencies)
