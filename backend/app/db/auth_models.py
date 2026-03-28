"""
Auth ORM Models — User (Phase 2)
=================================
Defines the users table for authentication (JWT + Argon2 passwords).

Shares the same Base as models.py; engine.py imports this module as a
side-effect so all tables are registered with Base.metadata.

Tables:
  - users  — registered users with email/password credentials
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base


class User(Base):
    """
    Registered user with email/password credentials.

    is_superadmin grants platform-wide admin privileges (provisioned by
    the bootstrap endpoint or direct DB seed).
    """

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
