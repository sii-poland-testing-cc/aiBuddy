# Technology Stack — JWT Auth + RBAC

**Project:** AI Buddy — Multi-Tenant RBAC Extension
**Researched:** 2026-03-27
**Scope:** Auth and RBAC additions only. Existing LLM/RAG stack (LlamaIndex, Chroma, Bedrock, etc.) is unchanged.

---

## Recommended Stack

### JWT Token Library (Backend)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `PyJWT` | `>=2.9.0` | JWT encode/decode | Official FastAPI recommendation as of 2025. Replaced `python-jose` in the FastAPI docs. Actively maintained, minimal dependencies, no cryptography extras needed for HS256. |

**Do NOT use `python-jose`.**
It was the FastAPI tutorial recommendation until ~2024 but has been replaced. It has an unmaintained transitive dependency (`ecdsa`) with known security advisories, and the upstream project has had infrequent releases. The official FastAPI docs now import directly from `jwt` (PyJWT). Confidence: HIGH — verified from official FastAPI docs.

```bash
pdm add pyjwt
```

Algorithm: HS256 (HMAC + SHA-256). Use a 256-bit secret (`openssl rand -hex 32`). Store in `SECRET_KEY` env var — one already exists in `config.py` with a placeholder.

---

### Password Hashing (Backend)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `pwdlib[argon2]` | `>=0.2.0` | Hash and verify passwords | Official FastAPI recommendation replacing `passlib`. Supports Argon2 (winner of the Password Hashing Competition). `passlib` is effectively unmaintained (last release 2022, incompatible with recent Python/bcrypt). |

**Do NOT use `passlib`.**
The FastAPI docs explicitly moved away from it. It emits deprecation warnings with bcrypt 4.x and has no active maintainer. Confidence: HIGH — verified from official FastAPI docs.

```bash
pdm add "pwdlib[argon2]"
```

Usage pattern from official docs:
```python
from pwdlib import PasswordHash
password_hash = PasswordHash.recommended()  # Argon2 by default

def get_password_hash(password: str) -> str:
    return password_hash.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return password_hash.verify(plain, hashed)
```

---

### Auth Pattern (Backend)

**Use FastAPI dependency injection, not middleware.**

The FastAPI docs explicitly recommend using `Depends()` over middleware for JWT validation. Reasons:
- Middleware runs on every request (including SSE streams, static routes, public endpoints)
- Dependencies are per-route — apply only where needed
- Dependencies integrate with OpenAPI docs (Swagger shows lock icons automatically)
- Middleware execution order clashes with `yield` dependencies

Pattern:

```python
from fastapi.security import OAuth2PasswordBearer
from fastapi import Depends, HTTPException, status
import jwt
from jwt.exceptions import InvalidTokenError

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except InvalidTokenError:
        raise credentials_exception
    # DB lookup omitted for brevity
```

No new libraries needed — `fastapi.security.OAuth2PasswordBearer` is already in the installed FastAPI package.

---

### RBAC Implementation (Backend)

**Do NOT use a third-party RBAC library.**

Libraries like `fastapi-permissions`, `casbin`, or `oso` are either:
- Too opinionated for hierarchical scoped roles (they assume flat or simple tree structures)
- Add significant complexity for a system that can be built cleanly in ~200 lines
- Have inconsistent async support with SQLAlchemy 2.0

The PROJECT.md requirement is explicit: RBAC is in-process, not a microservice. The permission model (3 roles, inheritance chain, scoped UserRoles table) is simple enough to implement directly.

**Recommended pattern:** Custom `canUser()` resolver as a FastAPI dependency.

```python
# Phase 1 — hardcoded permission map
ROLE_PERMISSIONS = {
    "org_admin":       {"read", "write", "delete", "manage_users"},
    "project_member":  {"read", "write"},
    "app_user":        {"read"},
}

async def require_permission(
    action: str,
    resource_type: str,
    resource_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    # Walk inheritance: App → Project → Org
    # Check UserRoles for user + resource, then parent resources
    ...
```

This stays entirely in `backend/app/auth/` — no new dependencies.

---

### New ORM Models (Backend)

No new ORM libraries needed. The existing SQLAlchemy 2.0 async `Mapped` API is sufficient.

New tables to add (via Alembic migrations, following existing patterns in `models.py`):

| Table | Columns (key) | Notes |
|-------|--------------|-------|
| `users` | id (UUID str PK), email (unique), hashed_password, is_active, created_at | Same UUID-string PK pattern as existing models |
| `organizations` | id, name, owner_id (FK users.id), created_at | Top of hierarchy |
| `projects` | id, organization_id (FK), name, created_at | Middle tier (currently `projects` is being renamed to `apps`) |
| `roles` | id, name (unique) | Seed: org_admin, project_member, app_user |
| `user_roles` | id, user_id, role_id, resource_type, resource_id | Scoped assignment; resource_type = "org"\|"project"\|"app" |

Note: The current `projects` table becomes `apps` as part of this milestone. The new `projects` table is a different entity (middle tier). Migration sequencing must handle this rename before adding the hierarchy tables.

---

### Token Storage (Frontend)

**Use httpOnly cookies, not localStorage.**

The official Next.js 14 auth docs (verified 2026-03-25, docs version 16.2.1) recommend:
- Store JWT in a cookie with `httpOnly: true`, `secure: true`, `sameSite: "lax"`
- Never store tokens in `localStorage` — XSS vulnerable
- Cookies are automatically sent with every fetch request from Server Components and Route Handlers

For this app (internal tooling, Next.js 14 App Router with existing `fetch` calls to `/api/*`):
- The frontend calls the FastAPI backend directly (not via Next.js API routes)
- Cookie-based storage means fetch calls need `credentials: "include"`
- Alternative: store in memory + Zustand for SPA-style; simpler but lost on page reload

**Recommendation:** httpOnly cookie. Matches Next.js official guidance. Requires updating existing `fetch` calls to include `credentials: "include"`.

No new npm packages needed for cookie management — `document.cookie` is sufficient for setting cookies from the FastAPI response, or use the FastAPI `Set-Cookie` response header pattern.

---

### Frontend Auth State

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| React Context (built-in) | — | Auth state (user object, isAuthenticated) | Already have `ProjectOperationsContext` pattern; same approach. No new library needed. |

Do NOT add NextAuth.js, Clerk, Auth0, or similar. They are designed for full auth provider flows (OAuth, magic links, social login). This project uses a custom FastAPI JWT backend with a simple email/password flow. External auth libraries would fight against the existing architecture.

---

### Password Validation (Frontend)

No new library. Use native HTML5 `pattern` attributes + minimal inline validation.

The Next.js docs show Zod for server-side form validation, but this project's validation runs on the FastAPI backend (Pydantic already installed). Frontend validation is optimistic/UX-only.

---

## Complete Dependency Changes

### Backend — Add to pyproject.toml

```toml
[project]
dependencies = [
    # --- existing deps ---
    # ... unchanged ...

    # Auth additions
    "pyjwt>=2.9.0",
    "pwdlib[argon2]>=0.2.0",
]
```

```bash
pdm add pyjwt "pwdlib[argon2]"
```

### Frontend — No new packages required

The existing stack handles auth:
- `fetch` with `credentials: "include"` for cookie-based auth
- React Context for auth state
- Next.js App Router for protected route redirects (middleware.ts)

---

## What NOT to Use

| Library | Why Not |
|---------|---------|
| `python-jose` | Replaced by PyJWT in official FastAPI docs. Unmaintained `ecdsa` dependency with CVEs. |
| `passlib` | Last release 2022, incompatible with bcrypt 4.x, no active maintainer. |
| `fastapi-users` | Opinionated auth framework that takes over User model, session management, and router structure. Too heavy for a custom RBAC system; the User model it generates conflicts with the custom hierarchy tables. |
| `casbin` | General-purpose RBAC/ABAC engine. Powerful but adds config overhead (policy files, adapter layer). Overkill for 3 hardcoded roles in Phase 1. Revisit if custom roles per org (Phase 4) become complex. |
| `fastapi-permissions` | Last updated 2021, no async support, does not model scoped resources. |
| `oso` (Polar) | Requires learning a custom policy language. Large dependency. Overkill for this scale. |
| `NextAuth.js` / `Auth0` / `Clerk` | OAuth-centric. The auth backend is a custom FastAPI JWT endpoint, not a supported provider. Would require wrapping or bypassing the library's assumptions. |
| `jose` (npm) | The Next.js docs use it for cookie encryption. Not needed here — the JWT is issued and verified by FastAPI, not Next.js. |
| `localStorage` for tokens | XSS vulnerable. httpOnly cookies are the correct choice per Next.js official guidance. |
| `SQLModel` | The FastAPI docs recommend it for new projects, but the existing codebase uses raw SQLAlchemy 2.0 Mapped API with Alembic. Mixing SQLModel and raw SQLAlchemy in the same project causes metaclass conflicts and migration confusion. Stick with the existing pattern. |

---

## Existing Dependencies (No Change Needed)

These existing packages already cover what auth needs:

| Package | Version (current) | Covers |
|---------|--------------------|--------|
| `fastapi>=0.115.0` | >=0.115.0 | `OAuth2PasswordBearer`, `HTTPException`, `Depends`, `Security` |
| `pydantic>=2.9.0` | >=2.9.0 | Request/response schema for login, token, user |
| `pydantic-settings>=2.6.0` | >=2.6.0 | `SECRET_KEY`, `ACCESS_TOKEN_EXPIRE_MINUTES` in `Settings` |
| `sqlalchemy>=2.0.0` | >=2.0.0 | New auth tables (User, Role, UserRole) |
| `alembic>=1.18.4` | >=1.18.4 | Migrations for all new tables |
| `aiosqlite>=0.20.0` | >=0.20.0 | Async SQLite for dev |

`SECRET_KEY` is already defined in `config.py` with a placeholder value — just needs a real 256-bit value in `.env`.

---

## Confidence Assessment

| Area | Confidence | Source | Notes |
|------|------------|--------|-------|
| PyJWT recommendation | HIGH | Official FastAPI docs (fastapi.tiangolo.com, verified 2026-03-27) | Explicit replacement of python-jose |
| pwdlib[argon2] recommendation | HIGH | Official FastAPI docs | Explicit replacement of passlib |
| Dependency injection over middleware | HIGH | Official FastAPI docs | Explicitly recommended pattern |
| No RBAC library needed | HIGH | PROJECT.md constraints + ecosystem survey | Custom resolver is standard for simple 3-role systems |
| httpOnly cookie storage | HIGH | Official Next.js docs (nextjs.org/docs, docs v16.2.1, verified 2026-03-27) | Explicitly recommended over localStorage |
| python-jose abandonment | MEDIUM | FastAPI docs dropped it; training data on CVEs | Could not verify CVE details via web fetch, but replacement is confirmed |
| pwdlib version number | MEDIUM | PyPI page inaccessible during research | ">=0.2.0" is training data; verify `pdm add "pwdlib[argon2]"` resolves correctly |
| casbin/oso verdict | MEDIUM | Training data + known ecosystem | Correct for Phase 1; may need revisiting for Phase 4 custom roles |

---

## Sources

- FastAPI Security Tutorial (JWT): https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/ (verified 2026-03-27)
- FastAPI Middleware docs: https://fastapi.tiangolo.com/tutorial/middleware/ (verified 2026-03-27)
- Next.js Authentication Guide: https://nextjs.org/docs/app/guides/authentication (docs v16.2.1, verified 2026-03-27)
- Existing codebase: `backend/pyproject.toml`, `backend/app/core/config.py`, `backend/app/db/models.py`, `backend/app/db/engine.py`
- Project requirements: `.planning/PROJECT.md`
