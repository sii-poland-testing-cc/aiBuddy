"""
Hierarchy ORM Models — Organization and Workspace (Phase 1)
===========================================================
Extends the core schema (models.py) with two hierarchy tables that sit
above the existing Project entity.

Hierarchy:  Organization  →  Workspace  →  Project

Shares the same Base as models.py; engine.py imports this module as a
side-effect so all tables are registered with Base.metadata.

Tables:
  - organizations  — top-level tenant boundary (a company or team)
  - workspaces     — optional grouping within an org
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Import Base from existing models to share the same metadata
from app.db.models import Base


# Default org/workspace IDs used by the migration to seed existing rows (D-03)
DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000002"


class Organization(Base):
    """
    Top-level tenant boundary.

    owner_id references a user, but the users table does not exist yet.
    The FK constraint is intentionally omitted here (per D-01) and will
    be added in Phase 2 once the users table is in place.
    """

    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String, nullable=False)

    # FK to users.id added in Phase 2 — omitted here to avoid circular dep
    owner_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
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
    """
    Optional grouping within an Organization.

    Projects can be placed directly under an Organization (workspace_id=NULL)
    or grouped into a Workspace for finer granularity.
    """

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

    # Relationships
    organization: Mapped["Organization"] = relationship(
        "Organization", back_populates="workspaces"
    )
    projects: Mapped[List["Project"]] = relationship(  # type: ignore[name-defined]
        "Project",
        back_populates="workspace",
        lazy="noload",
    )
