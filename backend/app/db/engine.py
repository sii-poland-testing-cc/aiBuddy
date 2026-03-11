"""
Async SQLAlchemy engine, session factory, and FastAPI dependency.
"""

from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.db.models import Base

engine = create_async_engine(
    settings.DATABASE_URL,
    # echo=True in dev is useful; keep False to avoid log noise in prod
    echo=settings.APP_ENV == "development",
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a per-request async DB session."""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """
    Create all tables that don't yet exist and apply any missing column migrations.
    Safe to call on every startup (idempotent).
    schema v4 — ProjectFile.source_type
    """
    url = settings.DATABASE_URL
    if url.startswith("sqlite"):
        # Strip driver prefix to get the file path, e.g. "./data/ai_buddy.db"
        db_path = url.split("///", 1)[-1]
        if db_path and not db_path.startswith(":"):   # skip ":memory:"
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Idempotent migrations for SQLite (ALTER TABLE is additive-only)
        if url.startswith("sqlite"):
            proj_cols = {
                row[1] for row in
                (await conn.execute(text("PRAGMA table_info(projects)"))).fetchall()
            }
            if "context_files" not in proj_cols:
                await conn.execute(
                    text("ALTER TABLE projects ADD COLUMN context_files TEXT")
                )
            pf_cols = {
                row[1] for row in
                (await conn.execute(text("PRAGMA table_info(project_files)"))).fetchall()
            }
            if "last_used_in_audit_id" not in pf_cols:
                await conn.execute(
                    text("ALTER TABLE project_files ADD COLUMN last_used_in_audit_id TEXT")
                )
            if "source_type" not in pf_cols:
                await conn.execute(
                    text("ALTER TABLE project_files ADD COLUMN source_type TEXT NOT NULL DEFAULT 'file'")
                )
