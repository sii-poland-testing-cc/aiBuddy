# Phase 2: Authentication - Research

**Researched:** 2026-03-28
**Domain:** FastAPI JWT authentication with httpOnly cookies + Next.js 14 middleware auth guard
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** `User` model goes in `backend/app/db/auth_models.py` — follows `hierarchy_models.py` pattern. Imports `Base` from `models.py`. Registered in `engine.py` and `migrations/env.py` via `import app.db.auth_models  # noqa: F401`.
- **D-02:** Migration `006_add_users_table.py` with `down_revision = "005"`. Creates `users` table only; `organizations.owner_id` FK constraint (deferred from Phase 1 per D-01 in 01-CONTEXT.md) added in the same migration.
- **D-03:** `PyJWT >= 2.9.0` for JWT encode/decode. `pwdlib[argon2]` for password hashing.
- **D-04:** JWT signed with `JWT_SECRET` from settings. Payload contains only `user_id` and `exp`.
- **D-05:** JWT TTL = 86400 seconds (24 hours).
- **D-06:** Cookie config: `httpOnly=True`, `samesite="lax"`, `secure=False` in dev (`APP_ENV != "production"`), `secure=True` in prod. `max_age=86400`. Path `/`.
- **D-07:** `ENFORCE_AUTH: bool = True` added to `Settings`. When `False`, `get_current_user()` returns a mock anonymous user instead of raising 401.
- **D-08:** `get_current_user()` reads JWT from `request.cookies.get("access_token")`. Raises HTTP 401 on missing/invalid/expired token. Placed as `Depends()` per route — not global middleware.
- **D-09:** `POST /api/auth/register` is open in Phase 2 — anyone can create an account.
- **D-10:** Next.js `frontend/middleware.ts` handles unauthenticated redirects. Checks for `access_token` cookie; redirects to `(auth)/login` page if missing on protected routes. Matcher excludes `(auth)/*`, `_next/*`, and static assets.
- **D-11:** `(auth)/login` and `(auth)/register` route group directories already exist (scaffolded). Add `page.tsx` to each with minimal form UI (email + password, submit, error display). Redirect to `/` on success.
- **D-12:** Create `frontend/lib/apiFetch.ts` — thin wrapper around `fetch()` with `credentials: "include"` baked in. Migrate all hook calls to use `apiFetch`.

### Claude's Discretion

- Exact login/register form layout (minimal is fine — internal tool)
- Error message wording on 401/403
- Whether to add a `display_name` or `name` field to `users` (not in requirements — omit)
- Relationship back-populate between `User` and `Organization.owner_id`

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope.

</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AUTH-01 | `users` table created (id UUID, email unique, hashed_password, created_at, is_superadmin bool) | auth_models.py pattern + migration 006 pattern established |
| AUTH-02 | `POST /api/auth/register` — email + password; password hashed with Argon2 via pwdlib; returns 201 with user id | pwdlib[argon2] API verified; FastAPI 201 response pattern in codebase |
| AUTH-03 | `POST /api/auth/login` — validates credentials; returns JWT in httpOnly cookie (not response body) | PyJWT 2.12.1 encode/decode API verified; FastAPI Response.set_cookie pattern confirmed |
| AUTH-04 | `POST /api/auth/logout` — clears httpOnly cookie | FastAPI Response.delete_cookie pattern confirmed |
| AUTH-05 | `GET /api/auth/me` — returns current user info from JWT; 401 if not authenticated | get_current_user() Depends() pattern established |
| AUTH-06 | JWT signed with `SECRET_KEY` from config; payload contains only `user_id` and `exp`; PyJWT library | PyJWT 2.12.1 API verified; JWT_SECRET already in config.py |
| AUTH-07 | `get_current_user()` FastAPI dependency resolves JWT from cookie; raises 401 if missing or invalid | FastAPI Depends() pattern; cookie access via Request confirmed |
| AUTH-08 | `ENFORCE_AUTH` env flag (default `true`); when `false`, all routes bypass auth check | Settings pattern from config.py; mock user return established |
| AUTH-09 | Frontend login page (`/login`) and register page (`/register`); redirect to `/` on success; unauthenticated users redirected to `/login` | Next.js 14 middleware.ts pattern verified; (auth) directories exist but empty |
| AUTH-10 | All existing frontend fetch calls updated with `credentials: "include"` for cookie transport | 22 fetch() call sites identified across 12 hook files |

</phase_requirements>

---

## Summary

Phase 2 adds user identity to the system: a `users` table, email/password auth via Argon2, JWT stored in an httpOnly cookie, and a FastAPI `get_current_user()` dependency that gates protected routes. An `ENFORCE_AUTH` flag lets the existing test suite bypass auth entirely. On the frontend, Next.js middleware redirects unauthenticated users to `/login`, and a thin `apiFetch` wrapper adds `credentials: "include"` to every outbound call.

All technology choices are locked in CONTEXT.md. Both `PyJWT` (2.12.1 — latest) and `pwdlib` (0.3.0 — latest) need to be added to `pyproject.toml`; neither is currently installed. The `(auth)/login` and `(auth)/register` directories exist but are empty — only `page.tsx` files need to be created. Middleware does not exist yet; it must be created at `frontend/middleware.ts`. Twenty-two `fetch()` call sites across twelve hook files need migration to `apiFetch`.

**Primary recommendation:** Implement in four well-separated waves: (1) DB layer (auth_models, migration 006), (2) backend auth routes + dependency, (3) frontend apiFetch + middleware, (4) login/register pages + wiring.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PyJWT | 2.12.1 (latest) | JWT encode/decode | FastAPI official recommendation; python-jose has unmaintained CVE-bearing dep |
| pwdlib[argon2] | 0.3.0 (latest) | Password hashing with Argon2 | Replaces passlib (incompatible with bcrypt 4.x); Argon2 is OWASP recommended |
| FastAPI | 0.135.1 (installed) | Backend framework | Already in use |
| SQLAlchemy 2.0 | 2.0.48 (installed) | Async ORM | Already in use |
| Next.js | 14.2.35 (installed) | Frontend framework + middleware | Already in use |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| argon2-cffi | (pulled in by pwdlib[argon2]) | Argon2 C bindings | Installed automatically via pwdlib extra |
| python-multipart | 0.0.12+ (installed) | Form data parsing | Already installed; needed if login form uses application/x-www-form-urlencoded (use JSON instead per pattern) |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PyJWT | python-jose | python-jose has known CVEs in ecdsa dep; PyJWT actively maintained |
| pwdlib[argon2] | passlib[bcrypt] | passlib incompatible with bcrypt 4.x; pwdlib is the maintained successor |
| httpOnly cookie | Authorization header / localStorage | Cookie is CSRF-safe with samesite=lax; httpOnly prevents XSS token theft |

**Installation (to add to pyproject.toml):**

```bash
# From backend/
pdm add "pyjwt>=2.9.0" "pwdlib[argon2]>=0.3.0"
# or
pip install "pyjwt>=2.9.0" "pwdlib[argon2]>=0.3.0"
```

**Version verification (confirmed 2026-03-28):**
- `pyjwt`: latest is 2.12.1 (confirmed via `pip index versions pyjwt`)
- `pwdlib`: latest is 0.3.0 (confirmed via `pip index versions pwdlib`)

---

## Architecture Patterns

### Recommended Project Structure (new files only)

```
backend/app/
├── db/
│   └── auth_models.py        # User ORM model (follows hierarchy_models.py pattern)
├── api/
│   └── routes/
│       └── auth.py           # register, login, logout, me endpoints
├── core/
│   ├── config.py             # add ENFORCE_AUTH, JWT_TTL_SECONDS settings
│   └── auth.py               # get_current_user() dependency + JWT helpers
migrations/versions/
└── 006_add_users_table.py    # users table + organizations.owner_id FK

frontend/
├── middleware.ts              # Next.js auth redirect guard
├── lib/
│   └── apiFetch.ts           # thin fetch() wrapper with credentials: "include"
└── app/(auth)/
    ├── login/
    │   └── page.tsx           # login form
    └── register/
        └── page.tsx           # register form
```

### Pattern 1: auth_models.py (User ORM)

Follows `hierarchy_models.py` exactly — imports `Base` from `models.py`, uses SQLAlchemy 2.0 Mapped API.

```python
# Source: backend/app/db/hierarchy_models.py (existing pattern)
import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column
from app.db.models import Base

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
```

### Pattern 2: PyJWT encode/decode

```python
# Source: PyJWT 2.x official API
import jwt
from datetime import datetime, timedelta, timezone
from app.core.config import settings

def create_access_token(user_id: str) -> str:
    payload = {
        "user_id": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=settings.JWT_TTL_SECONDS),
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm="HS256")

def decode_access_token(token: str) -> dict:
    # Raises jwt.ExpiredSignatureError or jwt.InvalidTokenError on failure
    return jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
```

### Pattern 3: pwdlib password hashing

```python
# Source: pwdlib 0.3.0 documentation
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

password_hash = PasswordHash([Argon2Hasher()])

def hash_password(plain: str) -> str:
    return password_hash.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return password_hash.verify(plain, hashed)
```

### Pattern 4: get_current_user() FastAPI dependency

```python
# Source: FastAPI docs + D-08 from CONTEXT.md
from fastapi import Depends, HTTPException, Request, status
from app.core.config import settings

async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)):
    if not settings.ENFORCE_AUTH:
        # Return anonymous mock user — existing tests pass unchanged
        return MockUser(id="anonymous", email="anon@local", is_superadmin=False)

    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    try:
        payload = decode_access_token(token)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)

    user = await db.get(User, payload["user_id"])
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user
```

### Pattern 5: FastAPI httpOnly cookie set/clear

```python
# Source: FastAPI docs — Response as parameter to set cookie
from fastapi import Response
from app.core.config import settings

@router.post("/login")
async def login(response: Response, ...):
    # ... validate credentials ...
    token = create_access_token(user.id)
    secure = settings.APP_ENV == "production"
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=settings.JWT_TTL_SECONDS,
        path="/",
    )
    return {"message": "ok"}

@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key="access_token", path="/")
    return {"message": "ok"}
```

### Pattern 6: Migration 006 (batch_alter for SQLite FK)

Follows migration 005 pattern exactly — `render_as_batch=True` already in `env.py`.

```python
# Source: backend/migrations/versions/005_add_hierarchy_tables.py (existing pattern)
revision = "006"
down_revision = "005"

def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("is_superadmin", sa.Boolean(), default=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # Add organizations.owner_id FK (deferred from Phase 1 D-01)
    with op.batch_alter_table("organizations", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_organizations_owner_id",
            "users", ["owner_id"], ["id"],
            ondelete="SET NULL",
        )
```

### Pattern 7: apiFetch wrapper

```typescript
// frontend/lib/apiFetch.ts
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  return fetch(`${API_BASE}${path}`, {
    ...init,
    credentials: "include",
  });
}
```

### Pattern 8: Next.js 14 middleware

```typescript
// frontend/middleware.ts
import { NextRequest, NextResponse } from "next/server";

export function middleware(request: NextRequest) {
  const token = request.cookies.get("access_token");
  if (!token) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.ico|login|register).*)",
  ],
};
```

**Important:** The `(auth)` Next.js route group maps to URL paths `/login` and `/register` (the group prefix `(auth)` is invisible in the URL). The matcher must exclude `/login` and `/register`, not `(auth)/login`.

### Anti-Patterns to Avoid

- **Global FastAPI middleware for auth:** Middleware cannot conditionally inject typed path params; breaks SSE stream headers (HTTP status is committed before streaming begins). Use `Depends()` per route instead (D-08).
- **JWT in localStorage:** Vulnerable to XSS. httpOnly cookie prevents JavaScript access entirely.
- **JWT in response body:** Requirement AUTH-03 explicitly states cookie only — do not include token in JSON response.
- **Verifying password in constant-time manually:** Use `pwdlib.verify()` which handles timing-safe comparison internally.
- **`python-jose` library:** Has unmaintained `ecdsa` dependency with CVEs. PyJWT is the safe choice (D-03).
- **passlib:** Incompatible with bcrypt 4.x which is already installed in this project (bcrypt==5.0.0 per requirements.txt). Using pwdlib avoids this conflict entirely.
- **`secure=True` in dev:** Breaks localhost HTTP development. Cookie must use `secure = (APP_ENV == "production")` (D-06).

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Password hashing | Custom bcrypt wrapper | `pwdlib[argon2]` | Argon2 is memory-hard, OWASP recommended; timing-safe comparison built in |
| JWT encode/decode | Custom base64 signing | `PyJWT` | Handles exp validation, algorithm negotiation, signature verification edge cases |
| Token expiry check | Manual `datetime.now() > exp` | PyJWT raises `ExpiredSignatureError` automatically | Edge cases with timezone-naive vs aware datetimes |
| CSRF protection | Custom CSRF token system | `samesite="lax"` on cookie | Lax prevents cross-origin POST automatically for non-navigation requests |

**Key insight:** The entire auth backend is ~150 lines of code if you let PyJWT + pwdlib handle the hard parts. The complexity is in integration points, not the crypto.

---

## Common Pitfalls

### Pitfall 1: bcrypt version conflict

**What goes wrong:** Installing `passlib[bcrypt]` causes `AttributeError: module 'bcrypt' has no attribute '__about__'` because bcrypt 5.x removed the `__about__` module that passlib relied on.

**Why it happens:** passlib has not been updated to support bcrypt 4.x+. This project already has `bcrypt==5.0.0` in requirements.txt.

**How to avoid:** Use `pwdlib[argon2]` exclusively. Do not add passlib.

**Warning signs:** `AttributeError` in passlib imports during any test.

---

### Pitfall 2: organizations.owner_id FK ordering

**What goes wrong:** Migration 006 tries to add FK `organizations.owner_id → users.id`, but if `users` table is created after the FK batch_alter, SQLite may fail to resolve the reference.

**Why it happens:** `op.create_table("users", ...)` must come before `with op.batch_alter_table("organizations") as batch_op: batch_op.create_foreign_key(...)`.

**How to avoid:** In migration 006 `upgrade()`: create `users` table first, then add FK to `organizations`.

**Warning signs:** `alembic upgrade head` fails with "no such table: users".

---

### Pitfall 3: Next.js middleware matcher vs route group naming

**What goes wrong:** Matcher pattern `"/((?!_next|\\(auth\\)).*)"` does not match `/login` correctly because `(auth)` is the directory name, but `/login` is the URL.

**Why it happens:** Next.js route groups `(auth)` are invisible in the URL. The URL is `/login`, not `/(auth)/login`.

**How to avoid:** Matcher must exclude `/login` and `/register` by URL path, not by directory group name.

**Warning signs:** Login page redirects back to itself in a loop.

---

### Pitfall 4: ENFORCE_AUTH=false does not set env var in conftest

**What goes wrong:** `ENFORCE_AUTH` defaults to `True` in Settings. Existing tests call API endpoints without a cookie. After adding `get_current_user()` dependency to routes, tests get 401s and fail.

**Why it happens:** The `get_current_user()` dependency is attached to routes after Phase 2. Tests do not send a cookie. If `ENFORCE_AUTH` is not overridden to `False` in `conftest.py`, all tests fail.

**How to avoid:** Add `os.environ.setdefault("ENFORCE_AUTH", "false")` to `conftest.py` alongside the existing env overrides at the top of the file.

**Warning signs:** Tests that were passing in Phase 1 all return 401/403 after adding auth dependency to any route.

---

### Pitfall 5: Side-effect import for auth_models not added everywhere

**What goes wrong:** `User` table does not appear in `Base.metadata` → `create_all()` in tests (via `init_db()`) doesn't create `users` table → all auth tests fail with "no such table: users".

**Why it happens:** SQLAlchemy only knows about tables that have been imported before `Base.metadata.create_all()` is called.

**How to avoid:** Add `import app.db.auth_models  # noqa: F401` to BOTH `engine.py` AND `migrations/env.py`. Pattern is already established by `hierarchy_models.py` in both files.

**Warning signs:** `OperationalError: no such table: users` in auth tests.

---

### Pitfall 6: SSE endpoints and Depends() with Response parameter

**What goes wrong:** SSE streaming endpoints use `StreamingResponse`. If the handler signature includes `response: Response` (to set cookies) alongside `StreamingResponse`, FastAPI may not apply the cookie to the streamed response correctly.

**Why it happens:** Cookie-setting via `Response` parameter works by mutating the response object before returning — this is safe for regular JSON responses but incompatible with streaming.

**How to avoid:** Auth endpoints (`/login`, `/logout`) are regular JSON/204 responses, not SSE streams — no conflict. The `get_current_user()` dependency on SSE endpoints only reads cookies (does not set them), so no conflict there either.

**Warning signs:** N/A for Phase 2 — SSE endpoints in Phase 2 will not be adding `Depends(get_current_user)` (that is Phase 3). This pitfall is noted for Phase 3 awareness.

---

## Code Examples

### Complete register endpoint skeleton

```python
# backend/app/api/routes/auth.py
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.engine import get_db
from app.db.auth_models import User
from app.core.auth import hash_password, create_access_token

router = APIRouter()

class RegisterRequest(BaseModel):
    email: str
    password: str

class RegisterResponse(BaseModel):
    id: str
    email: str

@router.post("/register", response_model=RegisterResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Check uniqueness
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=body.email, hashed_password=hash_password(body.password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return RegisterResponse(id=user.id, email=user.email)
```

### Updating conftest.py for ENFORCE_AUTH

```python
# Add to top of backend/tests/conftest.py, alongside existing env overrides
os.environ.setdefault("ENFORCE_AUTH", "false")  # Must be before any app imports
```

### Migration 006 downgrade

```python
def downgrade():
    # Remove FK from organizations first (before dropping users table)
    with op.batch_alter_table("organizations", schema=None) as batch_op:
        batch_op.drop_constraint("fk_organizations_owner_id", type_="foreignkey")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
```

### Frontend hook migration example

```typescript
// Before (in useProjects.ts):
const res = await fetch(`${API_BASE}/api/projects`);

// After:
import { apiFetch } from "@/lib/apiFetch";
const res = await apiFetch("/api/projects");
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| passlib + bcrypt | pwdlib[argon2] | bcrypt 4.x / 2023 | passlib incompatible with modern bcrypt; pwdlib is the maintained successor |
| python-jose | PyJWT | 2022-2023 | python-jose's ecdsa dep has CVEs; PyJWT is the FastAPI official recommendation |
| JWT in localStorage | httpOnly cookie | Industry shift ~2020 | Eliminates XSS token theft vector |

**Deprecated/outdated:**
- `passlib`: Effectively unmaintained; incompatible with bcrypt 4.x+
- `python-jose`: ecdsa CVEs; unmaintained

---

## Open Questions

1. **`_seed_default_org` fixture needs updating for User FK**
   - What we know: conftest.py has an `autouse` fixture seeding the default org row. After migration 006, `organizations.owner_id` gets a FK constraint to `users`. The seeded org has `owner_id=NULL`, which is fine with `ondelete="SET NULL"`.
   - What's unclear: Does the FK constraint on `owner_id` (nullable) require the `users` table to exist before the org seed INSERT in tests? SQLite FK enforcement is pragma-gated — with FK ON, a NULL `owner_id` is allowed even with the FK defined.
   - Recommendation: Keep `owner_id=NULL` in the conftest fixture INSERT. The FK only fires on non-NULL values. No change needed.

2. **`apiFetch` and SSE streaming pattern**
   - What we know: `consumeSSE` takes a `ReadableStream`, not a URL. Hooks call `fetch(url, {method: "POST", ...}).then(res => consumeSSE(res.body, ...))`.
   - What's unclear: `apiFetch` must preserve the full `RequestInit` including headers and body. The wrapper signature `apiFetch(path, init?)` passes through `init` with credentials merged in — this works correctly.
   - Recommendation: `apiFetch` spreads `...init` first, then sets `credentials: "include"` after (so it cannot be accidentally overridden by caller).

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python / pip | PyJWT + pwdlib install | ✓ | Python 3.x (venv active) | — |
| PyJWT | AUTH-03, AUTH-06 | ✗ | — (must install) | — |
| pwdlib[argon2] | AUTH-02 | ✗ | — (must install) | — |
| Node.js / npm | Next.js frontend | ✓ | (already running) | — |
| SQLite | Development DB | ✓ | via aiosqlite | — |
| Alembic | Migration 006 | ✓ | 1.18.4+ (installed) | — |
| bcrypt (system) | argon2-cffi C bindings | ✓ | bcrypt==5.0.0 in requirements.txt | — |

**Missing dependencies with no fallback:**
- `PyJWT >= 2.9.0` — must be added to `pyproject.toml` and installed. Latest: 2.12.1.
- `pwdlib[argon2] >= 0.3.0` — must be added to `pyproject.toml` and installed. Latest: 0.3.0.

**Missing dependencies with fallback:**
- None.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio |
| Config file | `backend/pytest.ini` or inline (check existing) |
| Quick run command | `cd backend && pytest tests/test_auth.py -v` |
| Full suite command | `cd backend && pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AUTH-01 | `users` table exists with correct columns | unit (DB) | `pytest tests/test_auth.py::test_users_table_exists -x` | ❌ Wave 0 |
| AUTH-02 | Register creates user with hashed password, returns 201 | integration | `pytest tests/test_auth.py::test_register_creates_user -x` | ❌ Wave 0 |
| AUTH-02 | Duplicate email returns 409 | integration | `pytest tests/test_auth.py::test_register_duplicate_email -x` | ❌ Wave 0 |
| AUTH-03 | Login sets httpOnly cookie | integration | `pytest tests/test_auth.py::test_login_sets_cookie -x` | ❌ Wave 0 |
| AUTH-03 | Invalid password returns 401 | integration | `pytest tests/test_auth.py::test_login_wrong_password -x` | ❌ Wave 0 |
| AUTH-04 | Logout clears cookie | integration | `pytest tests/test_auth.py::test_logout_clears_cookie -x` | ❌ Wave 0 |
| AUTH-05 | /me returns user when authenticated | integration | `pytest tests/test_auth.py::test_me_authenticated -x` | ❌ Wave 0 |
| AUTH-05 | /me returns 401 when not authenticated | integration | `pytest tests/test_auth.py::test_me_unauthenticated -x` | ❌ Wave 0 |
| AUTH-06 | JWT payload contains user_id and exp only | unit | `pytest tests/test_auth.py::test_jwt_payload_shape -x` | ❌ Wave 0 |
| AUTH-07 | get_current_user raises 401 on missing/expired token | unit | `pytest tests/test_auth.py::test_get_current_user_no_token -x` | ❌ Wave 0 |
| AUTH-08 | Existing tests pass with ENFORCE_AUTH=false | regression | `pytest tests/ -v --ignore=tests/test_auth.py` | ✅ (existing suite) |
| AUTH-09 | Frontend pages exist (smoke) | manual | n/a — visual verification | N/A |
| AUTH-10 | apiFetch sends credentials: include | unit (frontend) | `cd frontend && npm test -- tests/apiFetch.test.ts` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `cd backend && pytest tests/test_auth.py -v`
- **Per wave merge:** `cd backend && pytest tests/ -v`
- **Phase gate:** Full suite green (backend + frontend) before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `backend/tests/test_auth.py` — all AUTH-01 through AUTH-08 tests
- [ ] `frontend/tests/apiFetch.test.ts` — covers AUTH-10 (credentials: include baked in)
- [ ] Add `os.environ.setdefault("ENFORCE_AUTH", "false")` to `backend/tests/conftest.py`

---

## Project Constraints (from CLAUDE.md)

| Constraint | Impact on Phase 2 |
|------------|-------------------|
| LlamaIndex Workflow Context API: `ctx.store.set/get` not `ctx.set/get` | N/A — no new workflows in Phase 2 |
| All async DB calls use `AsyncSession` from `get_db()` | Auth route handlers must use `Depends(get_db)` — same as all other routes |
| `render_as_batch=True` in migrations | Migration 006 must use `op.batch_alter_table()` for ALTER TABLE on SQLite |
| `compare_type=False` in Alembic env | Already set — no action needed |
| Backend run: `uvicorn app.main:app --reload` | Auth router must be added to `main.py` via `app.include_router()` |
| Frontend: `npm run dev` | Standard Next.js dev — `middleware.ts` runs automatically in dev |
| Tests: `pytest` from `backend/` | Test file must be in `backend/tests/` to be discovered |
| `init_db()` is test-only fallback (not Alembic) | Side-effect import of `auth_models` in `engine.py` ensures `users` table appears in `create_all()` for tests |
| SSE endpoints: `Depends()` per route, not global middleware | Auth guarding of SSE routes deferred to Phase 3; only `/api/auth/*` routes in Phase 2 |
| `JWT_SECRET` already in `config.py` | Add `ENFORCE_AUTH: bool = True` and `JWT_TTL_SECONDS: int = 86400` alongside it |
| CORSMiddleware has `allow_credentials=True` | Already configured — no change needed for cookie transport |

---

## Sources

### Primary (HIGH confidence)

- Codebase inspection — `backend/app/db/hierarchy_models.py`, `backend/app/db/engine.py`, `backend/migrations/env.py`, `backend/migrations/versions/005_add_hierarchy_tables.py`, `backend/app/core/config.py`, `backend/app/main.py`, `backend/tests/conftest.py` — all patterns verified directly
- `pip index versions pyjwt` — confirmed 2.12.1 latest (2026-03-28)
- `pip index versions pwdlib` — confirmed 0.3.0 latest (2026-03-28)
- `backend/pyproject.toml` — confirmed PyJWT and pwdlib not yet in dependencies
- `backend/requirements.txt` — confirmed bcrypt==5.0.0 installed (rules out passlib)
- `frontend/package.json` — confirmed Next.js 14.2.35, Vitest for frontend testing
- `frontend/lib/*.ts` grep — 22 `fetch()` call sites identified across 12 files

### Secondary (MEDIUM confidence)

- FastAPI official docs pattern for httpOnly cookie via `Response` parameter — consistent with project's existing cookie-free route patterns
- Next.js 14 middleware.ts — standard Edge Runtime middleware pattern; `(auth)` route group URL invisibility is documented Next.js behavior

### Tertiary (LOW confidence)

- None — all claims verified from codebase or package registry.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified from PyPI registry 2026-03-28
- Architecture: HIGH — patterns traced directly from existing codebase files
- Pitfalls: HIGH — bcrypt conflict traced from requirements.txt; FK ordering from migration 005 pattern; middleware matcher verified against Next.js behavior

**Research date:** 2026-03-28
**Valid until:** 2026-04-28 (stable stack; PyJWT and pwdlib version checked against registry)
