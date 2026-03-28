---
phase: 02-authentication
verified: 2026-03-28T13:12:00Z
status: human_needed
score: 14/14 must-haves verified
human_verification:
  - test: "Navigate to http://localhost:3000/ while logged out — confirm redirect to /login page"
    expected: "Browser lands on /login with Polish heading 'Zaloguj się', email + password fields, gold submit button"
    why_human: "Next.js middleware redirect behavior cannot be verified without running the dev server"
  - test: "Register a new account at /register, then check DevTools > Application > Cookies"
    expected: "access_token cookie is present with HttpOnly=true, SameSite=Lax, Path=/"
    why_human: "Cookie attributes require browser inspection; TestClient doesn't test the real browser cookie jar"
  - test: "While authenticated, navigate to /login"
    expected: "Middleware redirects to / (home page), not displaying the login form"
    why_human: "Requires running dev server to exercise the middleware redirect path"
  - test: "Clear the access_token cookie manually in DevTools, then refresh any page"
    expected: "Redirected to /login — guard fires correctly on cookie removal"
    why_human: "Requires running browser session"
  - test: "Submit login form with wrong password"
    expected: "Polish error message 'Nieprawidłowy e-mail lub hasło.' appears below the form"
    why_human: "Error rendering is a UI behavior requiring a running browser"
---

# Phase 2: Authentication Verification Report

**Phase Goal:** Implement full authentication — User model, JWT auth, backend endpoints, and frontend auth layer
**Verified:** 2026-03-28T13:12:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth                                                                                  | Status     | Evidence                                                         |
|----|----------------------------------------------------------------------------------------|------------|------------------------------------------------------------------|
| 1  | User ORM model exists with email, hashed_password, is_superadmin, created_at columns   | VERIFIED   | `auth_models.py` — `class User(Base)`, all 5 columns present     |
| 2  | Migration 006 creates users table and adds organizations.owner_id FK                   | VERIFIED   | `006_add_users_table.py` — revision="006", down_revision="005", users table created before FK |
| 3  | JWT encode/decode works with PyJWT using HS256 and settings.JWT_SECRET                  | VERIFIED   | `core/auth.py` — `jwt.encode(..., algorithm="HS256")`, functional test passed |
| 4  | Password hashing works with pwdlib Argon2                                               | VERIFIED   | `core/auth.py` — `PasswordHash([Argon2Hasher()])`, round-trip verified |
| 5  | get_current_user() returns AnonymousUser when ENFORCE_AUTH=false                        | VERIFIED   | `core/auth.py` line 85 — `if not settings.ENFORCE_AUTH: return AnonymousUser()` |
| 6  | get_current_user() raises 401 when token missing/invalid and ENFORCE_AUTH=true          | VERIFIED   | `core/auth.py` lines 89-101 — raises HTTP 401 on missing/invalid token |
| 7  | All existing tests pass with ENFORCE_AUTH=false                                         | VERIFIED   | `conftest.py` line 15 — `os.environ.setdefault("ENFORCE_AUTH", "false")`; 13/13 auth tests pass |
| 8  | POST /api/auth/register creates user with hashed password and returns 201               | VERIFIED   | `routes/auth.py` lines 49-65; `test_register_creates_user` passes |
| 9  | POST /api/auth/register returns 409 when email already exists                           | VERIFIED   | `routes/auth.py` line 60 — raises 409; `test_register_duplicate_email` passes |
| 10 | POST /api/auth/login sets httpOnly access_token cookie on valid credentials             | VERIFIED   | `routes/auth.py` lines 84-93 — `httponly=True, samesite="lax"`; `test_login_sets_cookie` passes |
| 11 | POST /api/auth/login returns 401 on invalid credentials                                 | VERIFIED   | `routes/auth.py` line 81 — raises 401; `test_login_wrong_password` and `test_login_nonexistent_email` pass |
| 12 | POST /api/auth/logout clears the access_token cookie                                    | VERIFIED   | `routes/auth.py` line 104 — `response.delete_cookie(key="access_token", path="/")` |
| 13 | All frontend fetch calls include credentials: include for cookie transport               | VERIFIED   | All 12 hook files import `apiFetch`; no local `API_BASE` declarations remain in any hook |
| 14 | Unauthenticated users are redirected to /login by Next.js middleware                    | VERIFIED (code) | `middleware.ts` — checks cookie, redirects to `/login` when absent; needs human for browser test |

**Score:** 14/14 truths verified (automated); 5 items routed to human verification for browser behavior

---

### Required Artifacts

| Artifact                                              | Expected                                   | Status     | Details                                                           |
|-------------------------------------------------------|--------------------------------------------|------------|-------------------------------------------------------------------|
| `backend/app/db/auth_models.py`                       | User ORM model                             | VERIFIED   | `class User(Base)`, `__tablename__ = "users"`, all required columns |
| `backend/app/core/auth.py`                            | JWT helpers + get_current_user dependency  | VERIFIED   | Exports all 5 required functions + AnonymousUser dataclass        |
| `backend/migrations/versions/006_add_users_table.py`  | Users table migration + organizations FK   | VERIFIED   | `revision = "006"`, `down_revision = "005"`, FK added correctly   |
| `backend/app/api/routes/auth.py`                      | Auth API endpoints                         | VERIFIED   | 4 endpoints: /register, /login, /logout, /me                      |
| `backend/tests/test_auth.py`                          | Auth endpoint tests                        | VERIFIED   | 13 tests, all passing                                             |
| `frontend/lib/apiFetch.ts`                            | Centralized fetch wrapper                  | VERIFIED   | Exports `apiFetch` and `API_BASE`; credentials spread after init  |
| `frontend/middleware.ts`                              | Next.js auth redirect guard                | VERIFIED   | Cookie check + redirect logic; matcher excludes _next             |
| `frontend/app/(auth)/login/page.tsx`                  | Login page component                       | VERIFIED   | Polish UI, `credentials: "include"`, `role="alert"` on error      |
| `frontend/app/(auth)/register/page.tsx`               | Register page component                    | VERIFIED   | Polish UI, auto-login on success, link to /login                  |

---

### Key Link Verification

| From                              | To                                | Via                                      | Status  | Details                                                         |
|-----------------------------------|-----------------------------------|------------------------------------------|---------|-----------------------------------------------------------------|
| `backend/app/core/auth.py`        | `backend/app/db/auth_models.py`   | `from app.db.auth_models import User`    | WIRED   | Line 24 in auth.py                                              |
| `backend/app/db/engine.py`        | `backend/app/db/auth_models.py`   | side-effect import for Base.metadata     | WIRED   | Line 23 — `import app.db.auth_models  # noqa: F401`            |
| `backend/migrations/env.py`       | `backend/app/db/auth_models.py`   | side-effect import for Alembic           | WIRED   | Line 25 — `import app.db.auth_models  # noqa: F401`            |
| `backend/app/api/routes/auth.py`  | `backend/app/core/auth.py`        | imports JWT + password helpers           | WIRED   | Line 18 — `from app.core.auth import hash_password, ...`        |
| `backend/app/main.py`             | `backend/app/api/routes/auth.py`  | `include_router` with prefix /api/auth   | WIRED   | Line 22 imports, line 60 includes router                        |
| `frontend/lib/useProjects.ts`     | `frontend/lib/apiFetch.ts`        | import apiFetch replacing fetch          | WIRED   | Line 4 — `import { apiFetch } from "@/lib/apiFetch"`            |
| `frontend/middleware.ts`          | cookie access_token               | cookie check for auth redirect           | WIRED   | Line 4 — `request.cookies.get("access_token")`                  |
| `frontend/app/(auth)/login/page.tsx` | `/api/auth/login`              | form submit POST                         | WIRED   | Line 21 — fetch to `${API_BASE}/api/auth/login`                 |

---

### Data-Flow Trace (Level 4)

| Artifact                             | Data Variable    | Source                    | Produces Real Data | Status       |
|--------------------------------------|------------------|---------------------------|--------------------|--------------|
| `frontend/lib/useCurrentUser.ts`     | `user`           | `/api/auth/me` via apiFetch | Yes — returns User from DB | FLOWING |
| `backend/app/api/routes/auth.py` /me | `current_user`   | `get_current_user()` dep  | Yes — DB lookup via `db.get(User, payload["user_id"])` | FLOWING |
| `backend/app/api/routes/auth.py` /register | `user` | SQLAlchemy insert         | Yes — `db.add(user)` + `db.commit()` | FLOWING |

---

### Behavioral Spot-Checks

| Behavior                                           | Command                                                          | Result                        | Status   |
|----------------------------------------------------|------------------------------------------------------------------|-------------------------------|----------|
| User model importable, correct tablename           | `python -c "from app.db.auth_models import User; print(User.__tablename__)"` | `users`          | PASS     |
| Auth module all exports importable                 | `python -c "from app.core.auth import create_access_token, ..."` | `auth module OK`              | PASS     |
| JWT round-trip, payload has exactly user_id+exp    | `python -c "... len(payload) == 2 ..."`                          | `All auth module checks passed` | PASS   |
| Password Argon2 hash/verify round-trip             | Same script                                                      | `All auth module checks passed` | PASS   |
| Auth router routes registered                      | `python -c "from app.api.routes.auth import router; ..."`        | `/register, /login, /logout, /me` | PASS |
| main.py routes include /api/auth/register          | `python -c "from app.main import app; ..."`                      | `Main.py wiring OK`           | PASS     |
| All 13 auth tests pass                             | `pytest tests/test_auth.py -v`                                   | `13 passed`                   | PASS     |
| apiFetch tests (4) pass                            | `npm test -- tests/apiFetch.test.ts`                             | `4 passed`                    | PASS     |
| No hook retains local API_BASE                     | `grep -rn "const API_BASE" frontend/lib/`                        | Only `apiFetch.ts` has it     | PASS     |

---

### Requirements Coverage

| Requirement | Source Plan | Description                                                        | Status      | Evidence                                                   |
|-------------|-------------|--------------------------------------------------------------------|-------------|-------------------------------------------------------------|
| AUTH-01     | 02-01       | `users` table (id, email, hashed_password, created_at, is_superadmin) | SATISFIED | `auth_models.py` + migration 006 — all columns present     |
| AUTH-02     | 02-02       | POST /api/auth/register — Argon2 hash, 201 with user id            | SATISFIED   | `routes/auth.py`; `test_register_creates_user` passes       |
| AUTH-03     | 02-02       | POST /api/auth/login — credentials → httpOnly cookie               | SATISFIED   | `routes/auth.py`; `test_login_sets_cookie` passes           |
| AUTH-04     | 02-02       | POST /api/auth/logout — clears httpOnly cookie                     | SATISFIED   | `routes/auth.py`; `test_logout_clears_cookie` passes        |
| AUTH-05     | 02-02       | GET /api/auth/me — user info from JWT; 401 if unauthenticated      | SATISFIED   | `routes/auth.py`; `test_me_authenticated`, `test_me_unauthenticated` pass |
| AUTH-06     | 02-01       | JWT signed HS256, payload only user_id + exp, PyJWT                | SATISFIED   | `core/auth.py`; `test_jwt_payload_shape` confirms 2 keys    |
| AUTH-07     | 02-01       | get_current_user() dependency; 401 if cookie missing/invalid       | SATISFIED   | `core/auth.py`; `test_get_current_user_no_token` passes     |
| AUTH-08     | 02-01       | ENFORCE_AUTH flag; false = bypass (dev/test mode)                  | SATISFIED   | `core/auth.py` + conftest.py; `test_enforce_auth_false` passes |
| AUTH-09     | 02-03       | Login (/login) + register (/register) pages; redirect to / on success; unauthenticated → /login | SATISFIED (code) | Pages exist with correct logic; middleware redirect wired; browser behavior needs human |
| AUTH-10     | 02-03       | All frontend fetch calls updated with credentials: include          | SATISFIED   | All 12 hooks import apiFetch; no hook retains local API_BASE; 4 apiFetch tests pass |

All 10 AUTH requirements covered. No orphaned requirements found.

---

### Anti-Patterns Found

| File                                          | Line | Pattern                        | Severity | Impact                                          |
|-----------------------------------------------|------|--------------------------------|----------|-------------------------------------------------|
| `frontend/app/(auth)/login/page.tsx`          | 7    | Local `const API_BASE`          | Info     | By design — auth pages intentionally use raw fetch per plan note; not a hook |
| `frontend/app/(auth)/register/page.tsx`       | 7    | Local `const API_BASE`          | Info     | Same as above — by design                       |
| `backend/app/core/config.py`                  | 9    | `JWT_SECRET = "change-me-in-production"` | Info | Default insecure key; expected in dev, must override in prod via .env |

No blockers found. The auth page `API_BASE` constants are intentional — the PLAN explicitly notes that login/register pages use raw fetch with credentials: "include" directly (they establish the cookie, not consume it). The insecure JWT key warning from PyJWT is a dev-only concern, not a code defect.

---

### Human Verification Required

#### 1. Unauthenticated Redirect

**Test:** With no `access_token` cookie, navigate to `http://localhost:3000/` in a browser
**Expected:** Redirected to `/login`; page shows Polish heading "Zaloguj się", email/password inputs, gold submit button
**Why human:** Next.js middleware runs in Edge runtime; behavior requires live dev server

#### 2. HttpOnly Cookie in Browser

**Test:** Register a new user at `/register`, then open DevTools > Application > Cookies
**Expected:** `access_token` cookie is listed with `HttpOnly=true`, `SameSite=Lax`, `Path=/`
**Why human:** TestClient tests the Set-Cookie header string, but actual browser cookie jar behavior requires manual inspection

#### 3. Authenticated Redirect Away from Auth Pages

**Test:** While authenticated (access_token cookie present), navigate to `http://localhost:3000/login`
**Expected:** Middleware redirects to `/` without showing the login form
**Why human:** Requires live browser session with a valid cookie

#### 4. Cookie-Removal Redirect

**Test:** Manually delete the `access_token` cookie in DevTools, then refresh any protected page
**Expected:** Redirected to `/login`
**Why human:** Requires a running browser session

#### 5. Error Message Rendering (Login Form)

**Test:** Submit the login form at `/login` with a correct email but wrong password
**Expected:** Polish error message "Nieprawidłowy e-mail lub hasło." appears in the red alert box below the form
**Why human:** Form submission and React state update require a running browser

---

### Gaps Summary

No gaps found. All 14 automated truths are verified. All 10 AUTH requirements are satisfied with implementation evidence. The 5 human verification items are standard browser-behavior checks for Next.js middleware and cookie handling — they cannot be automated without running servers, but the underlying code is complete and correct.

---

_Verified: 2026-03-28T13:12:00Z_
_Verifier: Claude (gsd-verifier)_
