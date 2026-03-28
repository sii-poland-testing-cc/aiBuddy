---
phase: 02-authentication
plan: 03
subsystem: frontend-auth
tags: [nextjs, middleware, tailwind, apifetch, login, register, credentials-include]

# Dependency graph
requires:
  - phase: 02-authentication
    plan: 01
    provides: "core/auth.py JWT helpers"
  - phase: 02-authentication
    plan: 02
    provides: "POST /api/auth/register, POST /api/auth/login, GET /api/auth/me endpoints"
provides:
  - "frontend/lib/apiFetch.ts — centralized fetch wrapper with credentials: include"
  - "frontend/middleware.ts — Next.js auth redirect guard (unauthenticated → /login, authenticated on auth page → /)"
  - "frontend/app/(auth)/login/page.tsx — Login page with Polish UI and buddy design tokens"
  - "frontend/app/(auth)/register/page.tsx — Register page with auto-login on success"
  - "All 12 frontend hook files migrated from raw fetch() to apiFetch()"
affects: [03-rbac-core]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "apiFetch wrapper: spreads init first then credentials: include — caller cannot override credentials"
    - "Middleware: pathname check inside function (not matcher) because (auth) route group is invisible in URL"
    - "Login/register pages use raw fetch + credentials: include — auth pages establish the cookie"
    - "Register page auto-logs-in after 201 by calling /api/auth/login with same credentials"

key-files:
  created:
    - "frontend/lib/apiFetch.ts — thin fetch wrapper exporting apiFetch() and API_BASE"
    - "frontend/tests/apiFetch.test.ts — 4 unit tests for apiFetch"
    - "frontend/middleware.ts — Next.js auth redirect middleware"
    - "frontend/app/(auth)/login/page.tsx — Login page"
    - "frontend/app/(auth)/register/page.tsx — Register page"
  modified:
    - "frontend/lib/useAIBuddyChat.ts — migrated to apiFetch, removed apiBase parameter from formatResult"
    - "frontend/lib/useAuditPipeline.ts — migrated to apiFetch"
    - "frontend/lib/useContextBuilder.ts — migrated to apiFetch, GlossaryTerm.source/related_terms made optional"
    - "frontend/lib/useContextStatuses.ts — migrated to apiFetch"
    - "frontend/lib/useHeatmap.ts — migrated to apiFetch"
    - "frontend/lib/useMapping.ts — migrated to apiFetch"
    - "frontend/lib/usePanelFiles.ts — migrated to apiFetch"
    - "frontend/lib/useProjectFiles.ts — migrated to apiFetch"
    - "frontend/lib/useProjects.ts — migrated to apiFetch"
    - "frontend/lib/useRequirements.ts — migrated to apiFetch"
    - "frontend/lib/useSnapshots.ts — migrated to apiFetch"
    - "frontend/tsconfig.json — added mockups to exclude list"
    - "frontend/mockups/01-unified-project-page.tsx — fixed pre-existing type error (mode: string)"

key-decisions:
  - "apiFetch spreads ...init first then overrides credentials: include so no caller can accidentally omit it"
  - "Auth pages use raw fetch (not apiFetch) — login/register are the ones that establish the cookie; the pattern is identical but explicit"
  - "formatResult's apiBase parameter removed — now uses apiFetch() directly, keeping the helper pure"
  - "GlossaryTerm.source/related_terms made optional to fix pre-existing type mismatch between useContextBuilder and Glossary component"

requirements-completed: [AUTH-09, AUTH-10]

# Metrics
duration: 15min
completed: 2026-03-28
---

# Phase 2 Plan 03: Frontend Auth Layer Summary

**apiFetch wrapper with credentials: include, Next.js auth middleware, Polish login/register pages, and migration of all 22 fetch() calls across 12 hook files**

## Performance

- **Duration:** ~15 min
- **Started:** 2026-03-28T10:03:11Z
- **Completed:** 2026-03-28T10:18:00Z
- **Tasks:** 2 of 3 completed (Task 3 is a checkpoint:human-verify)
- **Files modified:** 13 modified, 5 created

## Accomplishments

- `apiFetch.ts` wrapper centralizes `credentials: "include"` — spread order ensures caller cannot accidentally omit it
- 4 unit tests for apiFetch pass (prepend API_BASE, always credentials: include, merges init, cannot be overridden)
- All 12 hook files migrated: no file retains a local `const API_BASE = process.env...` declaration
- `middleware.ts` redirects unauthenticated users to `/login` and already-authenticated users away from `/login` and `/register`
- Login page: email/password form, Polish copy per UI-SPEC, buddy design tokens, role="alert" on error div, credentials: include
- Register page: same layout, auto-login after 201 response, 409/422 error handling, link to /login
- Frontend builds without TypeScript errors

## Task Commits

Each task was committed atomically:

1. **Task 1: Create apiFetch wrapper and migrate all hook fetch() calls** — `a12dc63` (feat)
2. **Task 2: Create Next.js middleware and login/register pages** — `8f9739b` (feat)

## Files Created/Modified

- `frontend/lib/apiFetch.ts` — exports `apiFetch(path, init)` and `API_BASE`
- `frontend/tests/apiFetch.test.ts` — 4 tests, all passing
- `frontend/middleware.ts` — auth redirect guard with `/((?!_next/static|_next/image|favicon\\.ico).*)` matcher
- `frontend/app/(auth)/login/page.tsx` — login form with Polish copy
- `frontend/app/(auth)/register/page.tsx` — register form with auto-login
- All 12 `frontend/lib/use*.ts` files migrated

## Decisions Made

- **apiFetch spread order:** `...init` first, then `credentials: "include"` last — this means the credentials override is always applied regardless of what the caller passes (even if they accidentally pass `credentials: "omit"`).
- **formatResult cleanup:** The `apiBase: string` parameter was removed from the private `formatResult` function since the function now calls `apiFetch()` directly. This simplifies the function signature without changing the external contract (`formatResult` is not exported).
- **GlossaryTerm optional fields:** `source` and `related_terms` were made optional in `useContextBuilder.ts`'s `GlossaryTerm` interface to resolve a pre-existing TypeScript type mismatch between `ContextGlossaryTerm` and `Glossary.GlossaryTerm` used in `MessageList`'s callback signature.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed pre-existing TypeScript build error: ContextGlossaryTerm callback mismatch**
- **Found during:** Task 2 build verification
- **Issue:** `handleTermClick` in `page.tsx` typed as `(term: ContextGlossaryTerm) => void` but passed to `MessageList.onTermClick?: (term: GlossaryTerm) => void`. `ContextGlossaryTerm` had required `source: string` and `related_terms: string[]` while `Glossary.GlossaryTerm` had optional `related_terms?: string[]` and no `source` field — TypeScript rejects this as function parameter types are contravariant.
- **Fix:** Made `source` and `related_terms` optional in `useContextBuilder.ts`'s `GlossaryTerm` interface. The API always returns these fields; making them optional in the type only widens the interface without affecting runtime behavior.
- **Files modified:** `frontend/lib/useContextBuilder.ts`
- **Commit:** `8f9739b`

**2. [Rule 1 - Bug] Fixed pre-existing TypeScript error: mockup mode literal comparison**
- **Found during:** Task 2 build verification
- **Issue:** `frontend/mockups/01-unified-project-page.tsx` had `const mode = "context"` (inferred literal type `"context"`) then later `mode === "requirements"` — TypeScript strict mode flags this as a comparison with no overlap.
- **Fix:** Changed to `const mode: string = "context"` — the mockup is UI design reference code, not runtime code, so widening to `string` is appropriate.
- **Files modified:** `frontend/mockups/01-unified-project-page.tsx`, `frontend/tsconfig.json` (attempted exclude; Next.js still type-checks all files, but the in-file fix was sufficient)
- **Commit:** `8f9739b`

---

**Total deviations:** 2 auto-fixed (both pre-existing build errors unrelated to our task changes)
**Impact on plan:** Both necessary to achieve the `npm run build exits 0` acceptance criterion.

## Known Stubs

None — login/register pages are fully wired to `/api/auth/login` and `/api/auth/register` endpoints (implemented in plan 02-02).

## Checkpoint: Task 3 Awaiting

Task 3 is a `checkpoint:human-verify` — visual verification of the complete auth flow. The automated portion (Tasks 1 and 2) is complete.

**What to verify:**
1. Navigate to `http://localhost:3000/` — should redirect to `/login`
2. Login page shows heading "Zaloguj się", email + password fields, gold submit button
3. Click register link — navigates to `/register`
4. Register page shows heading "Utwórz konto", same field layout
5. Fill in email + password, submit — should redirect to `/`
6. Navigate to `/login` while authenticated — should redirect to `/`
7. Navigate to `/` — project list page loads (no redirect loop)
8. Open DevTools > Application > Cookies — `access_token` cookie present, httpOnly=true
9. Clear the `access_token` cookie manually — refresh page, redirected to `/login`
10. Try logging in with wrong password — error "Nieprawidłowy e-mail lub hasło." appears

**Prerequisites:** Backend running (`cd backend && uvicorn app.main:app --reload`), frontend running (`cd frontend && npm run dev`).

---
*Phase: 02-authentication*
*Completed: 2026-03-28 (Tasks 1-2); Task 3 awaiting human verification*

## Self-Check: PASSED

- FOUND: frontend/lib/apiFetch.ts
- FOUND: frontend/tests/apiFetch.test.ts
- FOUND: frontend/middleware.ts
- FOUND: frontend/app/(auth)/login/page.tsx
- FOUND: frontend/app/(auth)/register/page.tsx
- FOUND commit a12dc63 (Task 1)
- FOUND commit 8f9739b (Task 2)
