# Feature Landscape

**Domain:** Multi-tenant RBAC for internal QA tooling platform (FastAPI + Next.js)
**Researched:** 2026-03-27
**Confidence:** HIGH (mature domain, well-established patterns; no WebSearch available — training data sufficient for RBAC feature taxonomy)

---

## Context

The existing AI Buddy platform has zero authentication. All endpoints are open. This milestone introduces:
- Org → Project → App three-tier hierarchy (App = renamed existing "Project")
- Email/password + JWT authentication from scratch
- Hierarchical RBAC: roles scoped to any level, inheriting downward
- Internal tooling only — no public registration, no SaaS-style self-service

Feature categorization below is calibrated for **internal enterprise tooling**, not public SaaS. This changes the table-stakes threshold significantly: many features that are table stakes for SaaS (email invites, self-service org signup, password reset flows) are explicitly anti-features here.

---

## Table Stakes

Features that must exist or the system is unusable / insecure for its stated purpose.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Email + password authentication | Every protected system needs identity | Low | bcrypt hashing; `python-jose` or `PyJWT` for tokens |
| JWT access tokens | Stateless auth for FastAPI SSE endpoints | Low | No refresh tokens needed in Phase 1; longer expiry (8–24h) acceptable for internal tool |
| Login + logout UI | Users must be able to authenticate from the browser | Low | Login page + token storage in `localStorage` or `httpOnly` cookie |
| JWT middleware on all API routes | Closing the zero-auth gap is the core security requirement | Low-Med | FastAPI `Depends(get_current_user)` pattern; must not break SSE streaming |
| "Current user" endpoint (`GET /api/auth/me`) | Frontend needs to know who is logged in | Low | Returns user id, email, roles |
| User model (id, email, hashed_password, created_at) | Foundational identity record | Low | Alembic migration |
| Three-tier entity model (Org → Project → App) | The hierarchy is the product; without it nothing else makes sense | Med | Three tables, FK chain, Alembic migrations |
| Role assignments scoped to hierarchy levels | Roles must be attachable at Org, Project, or App granularity | Med | `user_roles(user_id, role_id, resource_type, resource_id)` pattern |
| Three built-in roles (org_admin, project_member, app_user) | Covers all realistic internal access patterns without UI role management | Low | Seeded via migration or startup; no dynamic role creation in Phase 1 |
| Downward inheritance of roles | Org admin automatically has access to all Projects and Apps under that Org | Med | Resolver must walk hierarchy upward: "does user have access at any ancestor level?" |
| Permission guards on existing endpoints | All M1/M2/Faza2/5/6 routes must enforce ownership before executing | Med | Each route checks `canUser(user_id, action, resource_type, resource_id)`; wrong project_id returns 403 |
| Superadmin can create orgs + assign org owners | Someone must bootstrap the system; internal tooling bootstraps via admin | Low | Can be a seeded DB record or a protected `/admin` endpoint; no UI required in Phase 1 |
| Tenant isolation: Org boundary cannot be crossed | User in Org A must never see Org B's data, even with a valid JWT | Med | All DB queries must filter by org_id resolved from the authenticated user's context |

---

## Differentiators

Features beyond the minimum that add real value for this internal QA platform specifically.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Audit log (who accessed/changed what, when) | Compliance for internal tooling; "who ran the audit on App X?" is a real question | Med | Append-only `audit_events` table; log auth events + role changes + resource mutations |
| Role management UI (assign/revoke per org/project/app) | Reduces admin toil; avoids needing DB access for every role change | Med | Simple table UI in UtilityPanel or dedicated `/admin` page; only org_admin sees it |
| Request-scoped permission cache | Avoids N+1 DB queries per SSE stream step; measurable perf impact for long M1/M2 workflows | Low-Med | Dict keyed on `(user_id, resource_type, resource_id)` stored in request state; cleared after request |
| Per-request context propagation (user injected into workflow) | LLM workflows can log "triggered by user X"; audit trail is richer | Low | Pass `user_id` into workflow as metadata, not as access control |
| "My Apps" default view | Users see only the Apps they have access to, pre-filtered | Low | `WHERE app.project_id IN (projects user can see)` — project list page already exists, just needs auth filter |
| App-level ownership (creator = initial app_user) | The user who creates an App implicitly gets app_user role on it | Low | On `POST /api/apps/` success, auto-assign `app_user` role to creator |
| Graceful 401/403 error UX | Users see "You don't have access to this resource" rather than a blank screen or a JS crash | Low | Standardized error responses + frontend error boundary handling |
| DB-driven permissions (RolePermissions table) | Enables future role customization without code changes | Med | Phase 2 upgrade from hardcoded map; table: `role_permissions(role_id, permission_id)` |

---

## Anti-Features

Features to deliberately NOT build for internal tooling. Building these wastes time and adds complexity without value.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Public self-service registration | No public users; orgs are provisioned by admins | Superadmin creates orgs + users via seeded data or `/admin` API; no public signup page |
| Email-based org invitations | Requires SMTP infra, email templating, token expiry flows — significant complexity for zero benefit | Admin assigns roles directly via API or admin UI |
| Password reset / forgot-password email flow | Same SMTP infra problem; internal tools can use admin password reset | Admin can directly update `hashed_password` in DB or via admin endpoint |
| OAuth / social login (Google, GitHub, etc.) | Internal tooling behind a corporate network doesn't need consumer OAuth | Email/password + JWT is sufficient; add OAuth only if SSO requirement emerges |
| Refresh tokens (Phase 1) | Doubles token management complexity (rotation, revocation, storage) | Longer-lived access tokens (8–24h) are acceptable for internal tooling |
| JWT token revocation / blacklist | Requires Redis or DB lookup on every request, eliminating the stateless JWT benefit | Short-enough expiry (hours not days) makes revocation irrelevant for this use case |
| Custom roles per org (Phase 1) | Three built-in roles cover all internal use cases; dynamic roles add UI + DB complexity | Hardcode three roles; add custom roles only in Phase 4 if demand is proven |
| ABAC (attribute-based access control) hybrid | Adds rule engine complexity before simpler RBAC is even working | RBAC first; ABAC is Phase 4 only if concrete use cases justify it |
| Row-level security in PostgreSQL | Powerful but complex; RLS enforcement is invisible and hard to test | Enforce org isolation in application layer (query filters); RLS is overkill for internal tooling |
| SSO / SAML / LDAP integration | Enterprise SSO is a separate product requirement; not needed for this team | Plain email/password; add SSO only if the organization's IT policy requires it |
| MFA / 2FA | Adds UI + secret storage complexity; internal tool on a private network doesn't need it | Not in scope; add only if security audit requires it |
| Permission management UI for end users | Users managing their own permissions is confusing and a security risk | Org admins manage permissions; regular users don't see role assignment UI |
| Hierarchical group membership (users in groups, groups have roles) | RBAC without groups is simpler and sufficient for a small internal team | Direct user-to-role assignment; add groups only if org size makes it necessary (50+ users) |
| Fine-grained action logging on LLM outputs | The LLM responses themselves shouldn't be audit-logged (size, privacy) | Log that an audit was triggered and by whom, not the full response payload |

---

## Feature Dependencies

```
Registration/Login UI
  → JWT access token (depends on: User model + bcrypt + JWT signing)

JWT middleware (all routes protected)
  → Login endpoint (depends on: User model + token generation)

Three-tier entity model (Org → Project → App)
  → Role assignments (depends on: entities to scope roles against)

Role assignments
  → Permission resolver canUser() (depends on: roles + entities)

Permission resolver canUser()
  → Route-level permission guards (depends on: resolver working correctly)
  → Downward inheritance (depends on: resolver walking hierarchy)

Downward inheritance
  → Tenant isolation (depends on: hierarchy being correctly scoped)

All above
  → Audit log (depends on: knowing who triggered what)
  → Role management UI (depends on: role assignment API existing)

DB-driven permissions (Phase 2)
  → Hardcoded permissions (Phase 1) (replaces, does not depend on)

Request-scoped permission cache
  → Permission resolver (wraps, depends on)
```

---

## MVP Recommendation

Minimum viable auth + RBAC that makes the platform usable and secure for internal teams:

**Prioritize (Phase 1):**
1. User model + email/password registration + login endpoint (JWT)
2. JWT middleware protecting all existing routes
3. Three-tier entity hierarchy (Org → Project → App) with FK chain
4. Three built-in roles + UserRoles scoped assignments
5. `canUser()` resolver with downward inheritance
6. Route guards on all M1/M2/Faza2/5/6 endpoints
7. Login page in frontend + token storage
8. "My Apps" pre-filtered view (natural consequence of auth filter)

**Defer to Phase 2:**
- DB-driven RolePermissions table (hardcoded map ships first)
- Role management UI (API-only in Phase 1)
- Audit log table

**Defer to Phase 3:**
- Request-scoped permission cache (profile first, optimize when proven necessary)
- Redis permission cache (only if SQLite/PostgreSQL query latency is a problem)

**Never build (for this context):**
- All anti-features listed above

---

## Sources

- Domain knowledge: OWASP RBAC guidelines, NIST SP 800-162 (ABAC/RBAC), FastAPI security docs patterns
- Confidence: HIGH for feature taxonomy (RBAC is a 30-year-old field with well-established patterns)
- Specific technology choices (PyJWT vs python-jose, token storage strategy) are covered in STACK.md
