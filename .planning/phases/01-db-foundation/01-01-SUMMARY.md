---
phase: 01-db-foundation
plan: "01-01"
subsystem: database
tags: [sqlalchemy, alembic, sqlite, orm, hierarchy, multi-tenant]

# Dependency graph
requires: []
provides:
  - Organization ORM model (organizations table) with owner_id nullable, no FK to users yet
  - Workspace ORM model (workspaces table) with FK to organizations (CASCADE)
  - Project.organization_id and Project.workspace_id FK columns (nullable, RESTRICT/SET NULL)
  - DEFAULT_ORG_ID constant for migration seeding
  - hierarchy_models registered in engine.py and migrations/env.py for Alembic autogenerate
  - Settings.JWT_SECRET placeholder to prevent .env ValidationError
affects: [02-db-migration, 03-auth-backend, 04-rbac-core]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Hierarchy ORM modules share Base from models.py via `from app.db.models import Base`"
    - "Side-effect imports in engine.py and migrations/env.py register tables with Base.metadata"
    - "String forward references (\"Organization\", \"Workspace\") in Project relationships to avoid circular imports"
    - "nullable=True on hierarchy FK columns to avoid SQLite ADD COLUMN NOT NULL drift with Alembic"

key-files:
  created:
    - backend/app/db/hierarchy_models.py
  modified:
    - backend/app/db/models.py
    - backend/app/db/engine.py
    - backend/migrations/env.py
    - backend/app/core/config.py

key-decisions:
  - "organization_id on Project is nullable=True in ORM (diverges from D-08 NOT NULL) — SQLite prohibits ADD COLUMN NOT NULL without DEFAULT; FK RESTRICT provides runtime integrity; NOT NULL can be tightened post-PostgreSQL migration"
  - "owner_id on Organization has no ForeignKey constraint — users table does not exist yet; FK added in Phase 2 per D-01"
  - "DEFAULT_ORG_ID exported from hierarchy_models.py as a constant for use by migration and tests"
  - "JWT_SECRET added to Settings as forward-placeholder to prevent ValidationError when .env contains JWT_SECRET before Phase 2 auth implementation"

patterns-established:
  - "New ORM module pattern: import Base from app.db.models, add side-effect import in engine.py and migrations/env.py"
  - "Hierarchy FK columns: nullable, indexed, use RESTRICT for parent (Organization) and SET NULL for optional (Workspace)"

requirements-completed: [HIER-01, HIER-02]

# Metrics
duration: 2min
completed: 2026-03-27
---

# Phase 01 Plan 01: ORM Foundation for Organization-Workspace-Project Hierarchy

**SQLAlchemy 2.0 Organization and Workspace ORM models added to the hierarchy above Project, with FK columns on Project and JWT_SECRET config fix**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-27T22:14:48Z
- **Completed:** 2026-03-27T22:16:30Z
- **Tasks:** 2
- **Files modified:** 5 (1 created, 4 modified)

## Accomplishments

- Organization and Workspace ORM classes created in hierarchy_models.py, sharing Base with existing models
- Project extended with organization_id (RESTRICT FK) and workspace_id (SET NULL FK) columns plus relationships
- hierarchy_models registered as side-effect import in both engine.py and migrations/env.py so Alembic autogenerate will see all 8 tables
- Settings.JWT_SECRET placeholder added to prevent ValidationError when .env already contains JWT_SECRET

## Task Commits

Each task was committed atomically:

1. **Task 1: Create hierarchy_models.py with Organization and Workspace ORM classes** - `935fd50` (feat)
2. **Task 2: Extend Project model, register hierarchy_models, fix JWT_SECRET config** - `1bae80f` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `backend/app/db/hierarchy_models.py` - Organization and Workspace ORM models, DEFAULT_ORG_ID constant
- `backend/app/db/models.py` - Added organization_id/workspace_id FK columns and organization/workspace relationships to Project
- `backend/app/db/engine.py` - Added `import app.db.hierarchy_models` side-effect to register tables
- `backend/migrations/env.py` - Added `import app.db.hierarchy_models` for Alembic autogenerate
- `backend/app/core/config.py` - Added JWT_SECRET field with default to prevent .env parse crash

## Decisions Made

- organization_id is nullable=True in ORM (not NOT NULL as D-08 suggests) — SQLite's ADD COLUMN restriction prevents adding NOT NULL without DEFAULT; runtime integrity is provided by the RESTRICT FK; aligns with Research Pitfall 2 to prevent alembic check drift
- owner_id on Organization has no ForeignKey — users table does not exist yet; FK constraint deferred to Phase 2 per D-01
- Used string forward references ("Organization", "Workspace") in Project relationships to avoid circular imports (hierarchy_models.py imports Base from models.py)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- ORM foundation is complete; Plan 02 (Alembic migration) can now run `alembic revision --autogenerate` and will see organizations + workspaces tables
- All 8 tables confirmed registered: audit_snapshots, coverage_scores, organizations, project_files, projects, requirement_tc_mappings, requirements, workspaces
- No circular import errors confirmed by import verification

---
*Phase: 01-db-foundation*
*Completed: 2026-03-27*
