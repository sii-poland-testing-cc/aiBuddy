"""
Async SQLAlchemy engine, session factory, and FastAPI dependency.

Schema migrations are managed by Alembic (migrations/).
Run `alembic upgrade head` before starting the server (or on first deploy).
`init_db()` is kept only as a fallback for in-memory SQLite used in tests.
"""

from collections.abc import AsyncGenerator
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.db.models import Base
import app.db.requirements_models  # noqa: F401 — registers Faza 2 tables with Base
import app.db.hierarchy_models  # noqa: F401 — registers hierarchy tables with Base
import app.db.auth_models           # noqa: F401 — registers User table with Base

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.APP_ENV == "development",
)

# SQLite does not enforce FK constraints by default. Enable them per-connection
# so that ondelete="CASCADE" / "SET NULL" rules fire reliably in dev and tests.
if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_fk_pragma(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

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
