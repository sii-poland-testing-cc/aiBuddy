# Phase 2: Authentication - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions captured in CONTEXT.md — this log preserves the discussion.

**Date:** 2026-03-28
**Phase:** 02-authentication
**Mode:** discuss
**Areas discussed:** JWT session length, Register endpoint access, credentials:include strategy

---

## Gray Areas Identified

After codebase scout (codebase maps + key files read), 3 genuine gray areas were surfaced. All other Phase 2 decisions were already locked in PROJECT.md, REQUIREMENTS.md, or prior phase context.

**Pre-locked (not discussed):**
- PyJWT + pwdlib/argon2 — from PROJECT.md Key Decisions
- httpOnly cookie — from PROJECT.md Key Decisions
- ENFORCE_AUTH env flag — from REQUIREMENTS.md AUTH-08
- Depends() per route, not global middleware — from PROJECT.md Key Decisions
- No refresh tokens — from PROJECT.md Out of Scope
- auth_models.py pattern — obvious from Phase 1 hierarchy_models.py precedent
- Next.js middleware.ts for auth redirect — no middleware existed, clear best practice

---

## Discussion

### JWT Session Length

**Question:** JWT TTL value? (minimum 3600s per STATE.md pitfall)

| Option | Value |
|--------|-------|
| 8 hours | 28800s |
| **24 hours (selected)** | **86400s** |
| 7 days | 604800s |

**User chose:** 24 hours (86400s)
**Rationale:** Comfortable for full workday; low login friction for internal tool; safely above 3600s floor.

---

### Register Endpoint Access

**Question:** Should POST /api/auth/register be open or gated in Phase 2?

| Option | Description |
|--------|-------------|
| **Open in Phase 2 (selected)** | Anyone can register; RBAC (Phase 3) enforces what they can access |
| REGISTRATION_SECRET env var | Gated by secret header |
| Superadmin-only | Requires existing authenticated superadmin |

**User chose:** Open in Phase 2
**Rationale:** No practical risk — without a role assignment (Phase 3), a new registered user has no access to any org/workspace/project. RBAC closes the enforcement gap in Phase 3.

---

### credentials: include Strategy

**Question:** How to add credentials: include to ~10+ hook files?

| Option | Description |
|--------|-------------|
| **apiFetch() wrapper (selected)** | Centralized wrapper in frontend/lib/apiFetch.ts |
| Per-hook individual updates | Scattered but simpler |

**User chose:** apiFetch() wrapper
**Rationale:** Single migration pass, consistent going forward, natural place to add future auth headers.

---

## No Corrections / Deferred Ideas

All recommendations accepted. No scope creep surfaced.
