"""
Alembic migration environment — async SQLAlchemy edition.

Works with both:
  - sqlite+aiosqlite   (dev)
  - postgresql+asyncpg (prod)

DATABASE_URL is read from the .env file via app.core.config,
falling back to the sqlalchemy.url value in alembic.ini.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# ── Import all models so Alembic sees every table ────────────────────────────
from app.db.models import Base          # projects, project_files, audit_snapshots
import app.db.requirements_models       # noqa: F401  requirements, mappings, scores
import app.db.hierarchy_models          # noqa: F401  organizations, workspaces
import app.db.auth_models               # noqa: F401  users

# ── Alembic config object ─────────────────────────────────────────────────────
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


# ── Read DATABASE_URL from app settings (respects .env) ───────────────────────
def get_url() -> str:
    try:
        from app.core.config import settings
        return settings.DATABASE_URL
    except Exception:
        return config.get_main_option("sqlalchemy.url")


# ── Offline mode ──────────────────────────────────────────────────────────────

def run_migrations_offline() -> None:
    """Generate SQL without a live DB connection."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ── Online mode ───────────────────────────────────────────────────────────────

def do_run_migrations(connection: Connection) -> None:
    # compare_type=False: SQLite uses dynamic typing — TEXT/VARCHAR/String are
    # all the same affinity. Enabling type comparison causes false positives on
    # SQLite and is only meaningful for strongly-typed DBs (PostgreSQL).
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        compare_type=False,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    url = get_url()
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = url

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ── Entry point ───────────────────────────────────────────────────────────────

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
