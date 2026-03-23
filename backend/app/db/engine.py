"""
Async SQLAlchemy engine, session factory, and FastAPI dependency.

Schema migrations are managed by Alembic (migrations/).
Run `alembic upgrade head` before starting the server (or on first deploy).
`init_db()` is kept only as a fallback for in-memory SQLite used in tests.
"""

from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.db.models import Base
import app.db.requirements_models  # noqa: F401 — registers Faza 2 tables with Base

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_ENV == "development",
)

AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a per-request async DB session."""
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    """
    Create all tables via create_all.

    Used ONLY for:
      - In-memory SQLite in tests (no Alembic context available)
      - First-time local dev bootstrap when Alembic hasn't been run yet

    For all other cases (staging, prod, CI with a real DB file) run:
        alembic upgrade head
    """
    url = settings.DATABASE_URL
    if url.startswith("sqlite"):
        db_path = url.split("///", 1)[-1]
        if db_path and not db_path.startswith(":"):
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
