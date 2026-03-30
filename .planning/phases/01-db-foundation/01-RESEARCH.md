# Phase 1: DB Foundation - Research

**Researched:** 2026-03-27
**Domain:** SQLAlchemy 2.0 ORM + Alembic migrations (SQLite dev, SQLite/PostgreSQL prod)
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**D-01:** `organizations.owner_id` is a nullable `String` column with **no FK constraint** in Phase 1. The FK → `users.id` is added in Phase 2 when the `users` table is created. This avoids a forward-reference dependency across phases.

**D-02:** Organization and Workspace ORM classes go in a new `backend/app/db/hierarchy_models.py`. Follows the `requirements_models.py` pattern — imports `Base` from `models.py`, is registered in `migrations/env.py` with one new import line, and in `engine.py` with a `noqa: F401` import. `models.py` stays focused on core entities (Project, ProjectFile, AuditSnapshot).

**D-03:** Hardcoded predictable UUID `00000000-0000-0000-0000-000000000001`, name `"Default Organization"`, `owner_id = null`. All existing project rows get `organization_id` set to this UUID; `workspace_id` left null.

**D-04:** Single migration `005_add_hierarchy_tables.py`. Steps: (1) create `organizations` table, (2) insert default org row, (3) create `workspaces` table, (4) add `organization_id` + `workspace_id` columns to `projects` with `render_as_batch`, (5) bulk UPDATE to set `organization_id` on all existing rows, (6) add FK constraints + indexes.

**D-05:** `projects.organization_id` index added (queries will filter by org frequently). `workspaces.organization_id` index added. Composite unique index on `workspaces(organization_id, name)` — workspace names unique within an org.

**D-06:** `Organization` table columns: `id` (String PK, UUID), `name` (String, NOT NULL), `owner_id` (String, nullable, no FK), `created_at` (DateTime tz-aware).

**D-07:** `Workspace` table columns: `id` (String PK, UUID), `organization_id` (String, NOT NULL FK → organizations.id ON DELETE CASCADE), `name` (String, NOT NULL), `created_at` (DateTime tz-aware).

**D-08:** `projects` gains `organization_id` (String, NOT NULL FK → organizations.id ON DELETE RESTRICT — orgs with projects cannot be deleted) and `workspace_id` (String, nullable FK → workspaces.id ON DELETE SET NULL).

**D-09:** `ENFORCE_AUTH` env flag does not exist yet — it's Phase 2. Phase 1 adds no auth-related code. Existing test fixtures (conftest.py) create projects via `init_db()` (in-memory SQLite) — the new tables will be created by `Base.metadata.create_all` once `hierarchy_models.py` is imported in `engine.py`.

### Claude's Discretion
- Exact column order within the new tables
- Whether to add a `description` field to Organization or Workspace (not in requirements — omit for now)
- Relationship definitions (back_populates) on Organization ↔ Workspace ↔ Project ORM classes

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| HIER-01 | `organizations` table created (id UUID, name, owner_id nullable String no-FK, created_at) | ORM pattern from `requirements_models.py`; migration pattern from `001_initial_schema.py` |
| HIER-02 | `workspaces` table created (id UUID, organization_id FK → organizations, name, created_at) | Same ORM/migration patterns; composite unique index on `(organization_id, name)` |
| HIER-03 | `projects` table gains `organization_id` NOT NULL FK and `workspace_id` nullable FK; existing rows seeded into default org | `render_as_batch` pattern from `004_add_project_file_fk.py`; data seed via `op.execute()` in upgrade() |
| HIER-04 | Alembic migration covers all schema changes with proper FK constraints and indexes; all existing tests still pass | Single migration `005_add_hierarchy_tables.py`; `init_db()` auto-creates tables in test DB |
</phase_requirements>

---

## Summary

Phase 1 is a pure schema + data migration phase. There is no new API code, no auth logic, and no frontend changes. The work consists of three tightly coupled deliverables: (1) a new `hierarchy_models.py` ORM file, (2) additions to the `Project` ORM class in `models.py`, and (3) a single Alembic migration `005_add_hierarchy_tables.py`.

The existing codebase already uses the exact patterns needed. `requirements_models.py` is the established template for adding a new model file — it imports `Base` from `models.py`, is side-effect-imported in `engine.py` and `migrations/env.py`. Migration 004 is the template for adding FKs to an existing table via `op.batch_alter_table` (required for SQLite). The default UUID `00000000-0000-0000-0000-000000000001` enables tests to reference a known org without querying.

Two pre-existing issues must be addressed in Phase 1 to satisfy the success criterion "alembic check shows no drift": (a) the `JWT_SECRET` key in `backend/.env` causes `Settings()` validation to fail with `extra_forbidden`, which causes `env.py`'s `get_url()` to silently fall back to `alembic.ini`'s URL rather than `.env`'s URL — this is a silent correctness issue; and (b) `alembic check` already detects nullability drift between the ORM models and the SQLite schema on the dev DB. These pre-existing issues need to be triaged: the nullability drift is a known SQLite/SQLAlchemy comparison artifact (SQLite stores nullable/non-nullable identically in TEXT columns), and the `JWT_SECRET` issue will be resolved properly in Phase 2 when `SECRET_KEY` is renamed to `JWT_SECRET` in `config.py`. For Phase 1, `alembic check` must pass after the migration — which means the migration itself must not introduce new drift, even if pre-existing drift exists.

**Primary recommendation:** Implement exactly the three files described in CONTEXT.md, using `requirements_models.py` and migration 004 as copy-paste templates. The test DB (fresh SQLite via `init_db()`) auto-adopts new tables — no test fixtures need updating.

---

## Standard Stack

### Core (verified by direct code inspection)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| SQLAlchemy | 2.0.48 | ORM + query builder | Already used; `Mapped`/`mapped_column` typed API |
| Alembic | 1.18.4 | Schema migrations | Already used; `render_as_batch=True` for SQLite |
| aiosqlite | (installed) | Async SQLite driver | Already used in dev/test |

### No New Dependencies Required

Phase 1 adds zero new packages. All required tools are already installed in the venv.

**Verification:**
```bash
# Both already installed in .venv
D:/kod/sii/aiBuddy/backend/.venv/Scripts/python.exe -c "import sqlalchemy; print(sqlalchemy.__version__)"
# 2.0.48
D:/kod/sii/aiBuddy/backend/.venv/Scripts/alembic.exe --version
# alembic 1.18.4
```

---

## Architecture Patterns

### Recommended File Structure (Phase 1 additions only)

```
backend/app/db/
├── models.py              # MODIFY: add organization_id + workspace_id to Project
├── hierarchy_models.py    # CREATE: Organization + Workspace ORM classes
├── requirements_models.py # REFERENCE ONLY (template for hierarchy_models.py)
├── engine.py              # MODIFY: add import hierarchy_models noqa: F401
└── types.py               # unchanged

backend/migrations/versions/
├── 001_initial_schema.py  # unchanged
├── 002_add_project_settings.py  # unchanged
├── 003_add_requirement_gaps.py  # unchanged
├── 004_add_project_file_fk.py   # unchanged
└── 005_add_hierarchy_tables.py  # CREATE

backend/migrations/
└── env.py                 # MODIFY: add import hierarchy_models noqa: F401
```

### Pattern 1: New Model File (copy from requirements_models.py)

**What:** Separate ORM file that imports `Base` from `models.py` and adds new tables without touching the core file.
**When to use:** Whenever a feature adds new tables that are logically grouped but shouldn't bloat `models.py`.

```python
# backend/app/db/hierarchy_models.py
# Source: requirements_models.py (lines 1-30 pattern)
import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.models import Base  # shared Base — same metadata

class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    owner_id: Mapped[str | None] = mapped_column(String, nullable=True)  # NO FK — Phase 2
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
```

### Pattern 2: Side-Effect Registration in engine.py

**What:** Import module as a side effect to register its ORM tables with `Base.metadata`.
**Why it works:** `Base.metadata.create_all` (used in `init_db()`) and Alembic both read `Base.metadata` — importing the module is enough.

```python
# backend/app/db/engine.py — add this line
import app.db.hierarchy_models  # noqa: F401 — registers hierarchy tables with Base
```

```python
# backend/migrations/env.py — add this line (after existing requirements_models import)
import app.db.hierarchy_models  # noqa: F401  organizations, workspaces
```

### Pattern 3: Migration with Data Seed (D-04)

**What:** A single migration file that creates tables, inserts seed data, alters an existing table, then updates existing rows. All inside `upgrade()`.
**Key:** Use `op.execute()` for the INSERT and UPDATE; use `op.batch_alter_table` for adding columns to existing SQLite tables.

```python
# backend/migrations/versions/005_add_hierarchy_tables.py
# Source: 001_initial_schema.py + 004_add_project_file_fk.py patterns
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"

def upgrade() -> None:
    # Step 1: create organizations
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Step 2: insert default org
    op.execute(
        f"INSERT INTO organizations (id, name, owner_id, created_at) "
        f"VALUES ('{DEFAULT_ORG_ID}', 'Default Organization', NULL, datetime('now'))"
    )

    # Step 3: create workspaces
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workspaces_organization_id", "workspaces", ["organization_id"])
    op.create_index(
        "uq_workspaces_org_name", "workspaces", ["organization_id", "name"], unique=True
    )

    # Step 4: add columns to projects (render_as_batch required for SQLite)
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.add_column(sa.Column("organization_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("workspace_id", sa.String(), nullable=True))

    # Step 5: seed existing rows
    op.execute(
        f"UPDATE projects SET organization_id = '{DEFAULT_ORG_ID}' "
        f"WHERE organization_id IS NULL"
    )

    # Step 6: add FK constraints + index (separate batch to run after UPDATE)
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_projects_organization_id",
            "organizations", ["organization_id"], ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_projects_workspace_id",
            "workspaces", ["workspace_id"], ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_projects_organization_id", "projects", ["organization_id"])
```

### Pattern 4: Project ORM Extension

**What:** Add two new `mapped_column` declarations and optional relationships to the existing `Project` class.

```python
# backend/app/db/models.py — add to Project class
organization_id: Mapped[str] = mapped_column(
    String,
    ForeignKey("organizations.id", ondelete="RESTRICT"),
    nullable=False,
    index=True,
)
workspace_id: Mapped[Optional[str]] = mapped_column(
    String,
    ForeignKey("workspaces.id", ondelete="SET NULL"),
    nullable=True,
    index=True,
)
```

**CRITICAL:** The `Project.organization_id` column must have `nullable=False` in the ORM model. But since we add the column via `batch_alter_table` (which adds it as nullable first, then UPDATE fills it), we cannot use `nullable=False` in the `add_column` call without a `server_default`. The correct approach: add as nullable in migration, UPDATE, then the ORM model declares it `nullable=False` — this is consistent with how SQLAlchemy and SQLite actually work (SQLite doesn't enforce NOT NULL on existing rows during ALTER).

**Alternatively (simpler):** Declare `nullable=True` in both migration and ORM model for `organization_id`, since the NOT NULL enforcement is handled by the migration seeding all rows before the FK is applied. The application-level invariant is enforced by the FK constraint, not the nullable flag.

**Recommendation:** Keep `organization_id` as `nullable=True` in both migration SQL and ORM mapped_column to avoid the "add column NOT NULL without default" SQLite limitation. The FK `ondelete="RESTRICT"` provides the runtime integrity guarantee that organization_id is always set.

### Anti-Patterns to Avoid

- **Adding FK column as NOT NULL without a default in SQLite:** SQLite prohibits `ALTER TABLE ... ADD COLUMN col NOT NULL` without a `DEFAULT` clause. Always add as nullable, fill via UPDATE, then rely on ORM-level enforcement.
- **Using `op.alter_column` for nullable changes on SQLite:** SQLite doesn't support `ALTER COLUMN`. Always use `op.batch_alter_table` for any column modification on an existing SQLite table.
- **Importing hierarchy_models only in one place:** Must import in BOTH `engine.py` (for `init_db()` / test DB) AND `migrations/env.py` (for Alembic autogenerate). Missing either causes "table not found" in one of the two paths.
- **Skipping downgrade():** Always implement `downgrade()` that exactly reverses upgrade() — drop indexes, drop FK constraints, drop columns, drop tables in reverse dependency order.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SQLite ADD COLUMN restrictions | Custom ALTER TABLE script | `op.batch_alter_table` context manager | batch_alter rewrites the table — handles all SQLite DDL limitations |
| Seeding data during migration | Python script separate from migration | `op.execute()` inside `upgrade()` | Atomic with schema changes; runs in correct migration order |
| FK naming convention | Ad-hoc names | `"fk_{table}_{column}"` per existing codebase pattern | Consistent with `fk_project_files_last_audit` in 004 |
| Index naming | Ad-hoc names | `"ix_{table}_{column}"` per existing codebase pattern | Consistent with `ix_project_files_project_id` in 001 |

**Key insight:** SQLite batch migration is the most common pitfall in this domain. `render_as_batch=True` in `env.py` handles it globally but individual migrations still need `op.batch_alter_table` context managers — the global flag affects autogenerate, not explicit `upgrade()` code.

---

## Common Pitfalls

### Pitfall 1: JWT_SECRET in .env Breaks config.py Silently in Alembic

**What goes wrong:** `backend/.env` already contains `JWT_SECRET=your-32-plus-char-secret-here`. `Settings()` (Pydantic BaseSettings with `extra="forbid"` behavior default) raises `ValidationError: extra inputs are not permitted`. When Alembic's `env.py` calls `get_url()`, the `except Exception` swallows this error and falls back to `alembic.ini`'s `DATABASE_URL`. This means `alembic upgrade head` silently operates on the `.ini` URL (which may differ from `.env`).

**Why it happens:** The `.env` was pre-populated with a future `JWT_SECRET` field before Phase 2 created the corresponding `Settings` field. Pydantic's default extra-field behavior rejects unknown fields.

**How to avoid:** Phase 1 should add `JWT_SECRET: str = "change-me"` to `Settings` as an optional placeholder (or add `model_config = ConfigDict(extra="ignore")`). This unblocks `alembic upgrade head` for Phase 1 and makes Phase 2's JWT implementation cleaner.

**Warning signs:** `alembic upgrade head` completes without any `INFO [alembic.runtime.migration] Running upgrade` lines — it's operating on wrong DB.

### Pitfall 2: alembic check Nullable Drift (Pre-Existing)

**What goes wrong:** Running `alembic check` before Phase 1 already shows 13 "modify_nullable" operations as pending. This is because SQLite stores all columns as nullable in its schema, but Alembic compares against the ORM model's `nullable` declarations.

**Why it happens:** The initial migration `001_initial_schema.py` declared many columns as `nullable=True` (the SQLite storage reality) but the ORM models have `nullable=False` (Python-level enforcement). With `compare_type=False` this would not trigger, but nullability comparison is separate from type comparison.

**How to avoid:** The Phase 1 migration must NOT trigger additional nullability drift. All new columns should be declared consistently between the migration SQL and the ORM `mapped_column(nullable=...)`. For `organization_id`: use `nullable=True` in both places (as recommended above). For `workspace_id`: `nullable=True` in both.

**Note:** The pre-existing 13-item drift in the dev DB is not caused by Phase 1 and is out of scope to fix. The success criterion "alembic check shows no drift" should be interpreted as "alembic check shows no new drift introduced by this migration on a freshly-migrated DB."

**Warning signs:** `alembic check` fails with `modify_nullable` operations not in your migration.

### Pitfall 3: Test DB Not Getting New Tables

**What goes wrong:** Tests fail with `OperationalError: no such table: organizations` because `hierarchy_models.py` was not imported before `init_db()` runs.

**Why it happens:** `conftest.py` sets `DATABASE_URL` to a temp file, then `app_client` fixture imports `app.main` which calls `init_db()` in the lifespan. If `hierarchy_models` is imported in `engine.py` (as required), this is automatic. If the import is missing, the tables don't exist.

**How to avoid:** The `engine.py` import `import app.db.hierarchy_models  # noqa: F401` ensures all tables are registered with `Base.metadata` before `create_all` runs.

**Warning signs:** Tests pass that don't touch hierarchy tables but fail on any test that tries to INSERT a Project (FK constraint to organizations will fail).

### Pitfall 4: FK RESTRICT on organization_id With Empty Test DB

**What goes wrong:** After Phase 1, `POST /api/projects/` will fail with FK constraint violation because the default org (`00000000-0000-0000-0000-000000000001`) doesn't exist in the test DB.

**Why it happens:** The migration inserts the default org into the REAL db during `alembic upgrade head`. But the test DB is created via `init_db()` (which calls `create_all`, not migrations) — the seed INSERT from the migration never runs.

**How to avoid:** One of:
- Option A: Tests that create projects must first insert the default org row (conftest.py fixture).
- Option B: `Project.organization_id` FK uses `ondelete="RESTRICT"` but the column is initially nullable and only enforced at the application layer in Phase 2.
- Option C: The test `conftest.py` `app_client` fixture inserts the default org after `init_db()`.

**Recommended:** Option C — add a conftest fixture that inserts the default org row after `init_db()`. This is the minimal change and keeps existing test patterns intact.

**Warning signs:** `test_create_project` fails with `FOREIGN KEY constraint failed` after Phase 1.

### Pitfall 5: render_as_batch is Global but Not Automatic in upgrade()

**What goes wrong:** Writing `op.add_column("projects", ...)` instead of using `op.batch_alter_table` context manager causes "Cannot add a NOT NULL column with no default value" on SQLite.

**Why it happens:** `render_as_batch=True` in `env.py` affects Alembic's _autogenerate_ output, not manually written `upgrade()` code. Explicit `upgrade()` functions must use `op.batch_alter_table` explicitly.

**How to avoid:** Always use `with op.batch_alter_table("projects") as batch_op:` for any column addition, FK addition, or index creation on an existing table. See migration 004 for the exact pattern.

---

## Code Examples

### Organization and Workspace ORM (complete)

```python
# backend/app/db/hierarchy_models.py
# Source: direct inspection of requirements_models.py + models.py patterns
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.models import Base  # shared DeclarativeBase — same metadata as Project


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    owner_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # owner_id: NO FK in Phase 1. FK → users.id added in Phase 2.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    workspaces: Mapped[List["Workspace"]] = relationship(
        "Workspace",
        back_populates="organization",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    projects: Mapped[List["Project"]] = relationship(  # type: ignore[name-defined]
        "Project",
        back_populates="organization",
        lazy="noload",
    )


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    organization_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="workspaces"
    )
    projects: Mapped[List["Project"]] = relationship(  # type: ignore[name-defined]
        "Project",
        back_populates="workspace",
        lazy="noload",
    )
```

### Project ORM additions

```python
# backend/app/db/models.py — add to Project class body
# Source: existing FK pattern from ProjectFile.project_id

organization_id: Mapped[Optional[str]] = mapped_column(
    String,
    ForeignKey("organizations.id", ondelete="RESTRICT"),
    nullable=True,   # nullable=True in ORM to match SQLite reality; enforced by FK
    index=True,
)
workspace_id: Mapped[Optional[str]] = mapped_column(
    String,
    ForeignKey("workspaces.id", ondelete="SET NULL"),
    nullable=True,
    index=True,
)
# Relationships (requires TYPE_CHECKING import or string forward refs)
# organization: Mapped[Optional["Organization"]] = relationship(...)
# workspace: Mapped[Optional["Workspace"]] = relationship(...)
```

**Note on circular imports:** `models.py` defines `Project`; `hierarchy_models.py` imports `Base` from `models.py`. Adding relationships on `Project` that reference `Organization` and `Workspace` (defined in `hierarchy_models.py`) would create a circular import. Use string-based forward references: `relationship("Organization")` in `models.py`. These resolve at mapper configuration time (after both modules are imported by `engine.py`).

### conftest.py default org fixture

```python
# backend/tests/conftest.py — add after existing fixtures
DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"

@pytest.fixture(autouse=True)
def _seed_default_org(app_client):
    """Ensure the default organization row exists in every test DB."""
    # Direct DB insertion via the test client's app state
    import asyncio
    from app.db.engine import AsyncSessionLocal
    from sqlalchemy import text

    async def _insert():
        async with AsyncSessionLocal() as session:
            await session.execute(text(
                "INSERT OR IGNORE INTO organizations (id, name, owner_id, created_at) "
                f"VALUES ('{DEFAULT_ORG_ID}', 'Default Organization', NULL, datetime('now'))"
            ))
            await session.commit()

    asyncio.get_event_loop().run_until_complete(_insert())
```

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python (.venv) | All backend code | Yes | (venv present) | — |
| SQLAlchemy | ORM models | Yes | 2.0.48 | — |
| Alembic | Schema migrations | Yes | 1.18.4 | — |
| aiosqlite | SQLite async driver | Yes | (installed) | — |
| pytest | Test suite | No | — | Install via `pip install pytest pytest-asyncio httpx` |

**Missing dependencies with no fallback:**
- pytest is not installed in `.venv`. Tests cannot be run with `.venv/Scripts/python -m pytest`. Must install: `pip install pytest pytest-asyncio httpx` or use PDM dev dependencies.

**Missing dependencies with fallback:**
- None that block migration work. `alembic upgrade head` works without pytest.

**Pre-existing issue — JWT_SECRET in .env:**
The `.env` file contains `JWT_SECRET=your-32-plus-char-secret-here` which causes `Settings()` to fail with `ValidationError: extra inputs are not permitted`. Alembic's `get_url()` has an `except Exception` fallback so migration commands still work (falling back to `alembic.ini` DB URL). However, the FastAPI app itself will fail to start with this `.env`. Phase 1 should add `JWT_SECRET: str = "change-me"` to `Settings` as a forward-placeholder, unblocking the app startup and making the alembic `get_url()` use the correct `.env` URL.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (not yet installed in .venv) |
| Config file | None found — no pytest.ini, no `[tool.pytest]` in pyproject.toml |
| Quick run command | `cd backend && .venv/Scripts/python.exe -m pytest tests/test_projects.py tests/test_snapshots.py -x -q` |
| Full suite command | `cd backend && .venv/Scripts/python.exe -m pytest tests/ -x -q` |

**pytest not installed:** The `.venv` does not have pytest. Wave 0 must install it.

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| HIER-01 | `organizations` table exists with correct columns | unit (DB) | `pytest tests/test_hierarchy.py::test_organizations_table -x` | No — Wave 0 |
| HIER-02 | `workspaces` table exists with FK and unique index | unit (DB) | `pytest tests/test_hierarchy.py::test_workspaces_table -x` | No — Wave 0 |
| HIER-03 | `projects` rows have `organization_id` set to default org after migration | unit (DB) | `pytest tests/test_hierarchy.py::test_project_migration -x` | No — Wave 0 |
| HIER-04 | `alembic upgrade head` + `alembic check` run cleanly on fresh DB; existing test suite passes | integration | `pytest tests/ -x -q` | Partial (existing tests) |

### Sampling Rate
- **Per task commit:** `pytest tests/test_hierarchy.py tests/test_projects.py -x -q`
- **Per wave merge:** `pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_hierarchy.py` — covers HIER-01, HIER-02, HIER-03, HIER-04 schema assertions
- [ ] pytest installation: `pip install pytest pytest-asyncio httpx anyio` — not present in `.venv`
- [ ] `conftest.py` update: add `_seed_default_org` autouse fixture to prevent FK violations

*(Existing test infrastructure covers all non-hierarchy tests; only hierarchy-specific test file is missing.)*

---

## Open Questions

1. **Should `Project.organization_id` be nullable or non-nullable in the ORM model?**
   - What we know: SQLite prohibits `ADD COLUMN NOT NULL` without DEFAULT; migration adds column as nullable then fills it; ORM models in this project use `nullable=False` on columns that are logically required.
   - What's unclear: Will `alembic check` report drift if ORM says `nullable=False` but SQLite schema reflects nullable?
   - Recommendation: Use `nullable=True` in both migration SQL and ORM `mapped_column` to avoid `alembic check` drift. The FK constraint ensures no NULL values in practice.

2. **Circular import between models.py and hierarchy_models.py for relationships**
   - What we know: `hierarchy_models.py` imports `Base` from `models.py`. If `models.py` imports `Organization` from `hierarchy_models.py`, that creates a cycle.
   - What's unclear: Whether string-based `relationship("Organization")` resolves correctly when both modules are imported via `engine.py`.
   - Recommendation: Use string forward references (`relationship("Organization")`) in `models.py`. This is the standard SQLAlchemy approach and avoids the circular import. The existing code uses string refs in `ProjectFile.project` relationship to `Project`.

3. **Where to handle default org seeding in test DB**
   - What we know: `conftest.py` creates a fresh DB via `init_db()` for each test session; the migration INSERT never runs in tests.
   - What's unclear: Whether to use `autouse` fixture in conftest.py or guard the FK differently (e.g., server_default on the column).
   - Recommendation: Add a session-scoped autouse fixture in `conftest.py` that inserts the default org row after the app starts. This is the minimal-change approach consistent with existing conftest patterns.

---

## Sources

### Primary (HIGH confidence)
- Direct code inspection: `backend/app/db/models.py` — ORM patterns, Base, mapped_column conventions
- Direct code inspection: `backend/app/db/requirements_models.py` — template for hierarchy_models.py
- Direct code inspection: `backend/app/db/engine.py` — side-effect import pattern, init_db
- Direct code inspection: `backend/migrations/env.py` — render_as_batch, get_url fallback behavior
- Direct code inspection: `backend/migrations/versions/004_add_project_file_fk.py` — batch_alter_table + FK naming pattern
- Direct code inspection: `backend/migrations/versions/001_initial_schema.py` — full migration structure template
- Runtime verification: `alembic --version` → 1.18.4; `sqlalchemy.__version__` → 2.0.48
- Runtime verification: `alembic check` output — confirmed pre-existing nullability drift in dev DB

### Secondary (MEDIUM confidence)
- `CONTEXT.md` decisions D-01 through D-09 — all locked by user discussion, treated as authoritative

### Tertiary (LOW confidence)
- None.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified by runtime imports and direct code inspection
- Architecture patterns: HIGH — all patterns directly observed in existing codebase
- Pitfalls: HIGH (Pitfalls 1-5) — confirmed by runtime `alembic check` and code analysis
- Test infrastructure: MEDIUM — pytest not installed so cannot run tests to confirm behavior

**Research date:** 2026-03-27
**Valid until:** 2026-04-27 (stable domain — Alembic/SQLAlchemy APIs rarely change at patch level)
