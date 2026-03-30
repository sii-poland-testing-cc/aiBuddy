# Phase 1: DB Foundation - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Add `organizations` and `workspaces` tables. Add `organization_id` (NOT NULL FK) and `workspace_id` (nullable FK) to the existing `projects` table. Seed all existing project rows into a default organization. All existing backend pytest tests must pass after migration. No authentication, no RBAC — purely schema and data migration.

</domain>

<decisions>
## Implementation Decisions

### owner_id on organizations
- **D-01:** `organizations.owner_id` is a nullable `String` column with **no FK constraint** in Phase 1. The FK → `users.id` is added in Phase 2 when the `users` table is created. This avoids a forward-reference dependency across phases.

### Model file organization
- **D-02:** Organization and Workspace ORM classes go in a new `backend/app/db/hierarchy_models.py`. Follows the `requirements_models.py` pattern — imports `Base` from `models.py`, is registered in `migrations/env.py` with one new import line, and in `engine.py` with a `noqa: F401` import. `models.py` stays focused on core entities (Project, ProjectFile, AuditSnapshot).

### Default organization seeding
- **D-03:** Hardcoded predictable UUID `00000000-0000-0000-0000-000000000001`, name `"Default Organization"`, `owner_id = null`. All existing project rows get `organization_id` set to this UUID; `workspace_id` left null.

### Migration structure
- **D-04:** Single migration `005_add_hierarchy_tables.py`. Steps: (1) create `organizations` table, (2) insert default org row, (3) create `workspaces` table, (4) add `organization_id` + `workspace_id` columns to `projects` with `render_as_batch`, (5) bulk UPDATE to set `organization_id` on all existing rows, (6) add FK constraints + indexes.
- **D-05:** `projects.organization_id` index added (queries will filter by org frequently). `workspaces.organization_id` index added. Composite unique index on `workspaces(organization_id, name)` — workspace names unique within an org.

### Schema decisions
- **D-06:** `Organization` table columns: `id` (String PK, UUID), `name` (String, NOT NULL), `owner_id` (String, nullable, no FK), `created_at` (DateTime tz-aware).
- **D-07:** `Workspace` table columns: `id` (String PK, UUID), `organization_id` (String, NOT NULL FK → organizations.id ON DELETE CASCADE), `name` (String, NOT NULL), `created_at` (DateTime tz-aware).
- **D-08:** `projects` gains `organization_id` (String, NOT NULL FK → organizations.id ON DELETE RESTRICT — orgs with projects cannot be deleted) and `workspace_id` (String, nullable FK → workspaces.id ON DELETE SET NULL).

### Test compatibility
- **D-09:** `ENFORCE_AUTH` env flag does not exist yet — it's Phase 2. Phase 1 adds no auth-related code. Existing test fixtures (conftest.py) create projects via `init_db()` (in-memory SQLite) — the new tables will be created by `Base.metadata.create_all` once `hierarchy_models.py` is imported in `engine.py`.

### Claude's Discretion
- Exact column order within the new tables
- Whether to add a `description` field to Organization or Workspace (not in requirements — omit for now)
- Relationship definitions (back_populates) on Organization ↔ Workspace ↔ Project ORM classes

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Schema and migrations
- `backend/app/db/models.py` — Existing ORM models (Project, ProjectFile, AuditSnapshot); new models must share the same `Base`
- `backend/app/db/requirements_models.py` — Pattern to follow for `hierarchy_models.py` (separate file, imports Base, same conventions)
- `backend/app/db/engine.py` — Registers model files via `import app.db.requirements_models` pattern; Phase 1 adds the same for `hierarchy_models`
- `backend/migrations/env.py` — Must import new `hierarchy_models` so Alembic sees the tables
- `backend/migrations/versions/004_add_project_file_fk.py` — Latest migration; Phase 1 adds `005_add_hierarchy_tables.py` with `down_revision = "004"`

### Requirements
- `.planning/REQUIREMENTS.md` §Hierarchy — HIER-01, HIER-02, HIER-03, HIER-04 define exact columns and constraints
- `.planning/ROADMAP.md` §Phase 1 — Success criteria (5 items) that verification must check

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Base` from `models.py` — shared `DeclarativeBase`; all new models import and use this same Base
- `JsonType` from `app.db.types` — available but not needed for Phase 1 (no JSON columns on new tables)
- UUID generation pattern: `default=lambda: str(uuid.uuid4())` — use same for `Organization.id` and `Workspace.id`
- DateTime pattern: `mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))` — use for `created_at`

### Established Patterns
- `render_as_batch=True` is already configured in `migrations/env.py` — SQLite ALTER TABLE works correctly
- Migration file structure: `revision = "005"`, `down_revision = "004"`, `upgrade()` / `downgrade()` with `op.batch_alter_table` for column additions to existing tables
- FK naming convention: `"fk_{table}_{column}"` (see `fk_project_files_last_audit` in 004)
- SQLite FK enforcement enabled per-connection via PRAGMA in `engine.py` — FK constraints fire in dev/tests

### Integration Points
- `engine.py` needs one new import: `import app.db.hierarchy_models  # noqa: F401`
- `migrations/env.py` needs: `import app.db.hierarchy_models  # noqa: F401`
- `Project` ORM class in `models.py` needs two new columns: `organization_id` and `workspace_id` (mapped_column additions with ForeignKey)
- `conftest.py` uses `init_db()` which calls `Base.metadata.create_all` — importing `hierarchy_models` in `engine.py` ensures new tables appear in test DB automatically

</code_context>

<specifics>
## Specific Ideas

- Default org UUID `00000000-0000-0000-0000-000000000001` — hardcoded constant, allows tests to reference a known org ID without querying
- `ON DELETE RESTRICT` on `projects.organization_id` FK — prevents orphaned projects if an org is deleted (explicit error rather than silent cascade)
- `ON DELETE SET NULL` on `projects.workspace_id` FK — removing a workspace demotes its projects to "no workspace" (they stay under the org)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope.

</deferred>

---
*Phase: 01-db-foundation*
*Context gathered: 2026-03-27*
