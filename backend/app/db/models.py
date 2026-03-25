"""
SQLAlchemy 2.0 ORM models
=========================
Uses the mapped_column / Mapped API (type-annotated style).
Both models are compatible with SQLite (dev) and PostgreSQL (prod);
the only dialect-specific setting is DateTime(timezone=True), which
aiosqlite stores as a TEXT ISO string and reads back transparently.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.db.types import JsonType


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    # M1 Context Builder artefacts — persisted after /build
    mind_map: Mapped[Optional[dict]] = mapped_column(JsonType(), nullable=True)
    glossary: Mapped[Optional[list]] = mapped_column(JsonType(), nullable=True)
    context_stats: Mapped[Optional[dict]] = mapped_column(JsonType(), nullable=True)
    context_built_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    context_files: Mapped[Optional[list]] = mapped_column(JsonType(), nullable=True)

    # Faza 2 requirement gaps — separate from context_stats to avoid M1 rebuild collision
    requirement_gaps: Mapped[Optional[list]] = mapped_column(JsonType(), nullable=True)

    settings: Mapped[Optional[dict]] = mapped_column(JsonType(), nullable=True)
    # JSON: arbitrary project-level settings object

    files: Mapped[List["ProjectFile"]] = relationship(
        "ProjectFile",
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    snapshots: Mapped[List["AuditSnapshot"]] = relationship(
        "AuditSnapshot",
        back_populates="project",
        order_by="AuditSnapshot.created_at.desc()",
        cascade="all, delete-orphan",
    )


class ProjectFile(Base):
    __tablename__ = "project_files"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename: Mapped[str] = mapped_column(String, nullable=False)
    file_path: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    indexed: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    last_used_in_audit_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("audit_snapshots.id", ondelete="SET NULL"), nullable=True
    )
    # snapshot id of the last audit that used this file
    # null = never used in any audit → default selected

    source_type: Mapped[str] = mapped_column(String, nullable=False, default="file")
    # "file" | "url" | "jira" | "confluence"

    project: Mapped["Project"] = relationship("Project", back_populates="files")


class AuditSnapshot(Base):
    __tablename__ = "audit_snapshots"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    files_used: Mapped[Optional[list]] = mapped_column(JsonType(), nullable=True)
    # ["file1.xlsx", "jira:PROJ-1234"]

    summary: Mapped[Optional[dict]] = mapped_column(JsonType(), nullable=True)
    # {coverage_pct, duplicates_found, requirements_total,
    #  requirements_covered, untagged_cases}

    requirements_uncovered: Mapped[Optional[list]] = mapped_column(JsonType(), nullable=True)
    # ["FR-001", "FR-005", ...]

    recommendations: Mapped[Optional[list]] = mapped_column(JsonType(), nullable=True)
    # ["recommendation 1", "recommendation 2", ...]

    diff: Mapped[Optional[dict]] = mapped_column(JsonType(), nullable=True)
    # {coverage_delta, duplicates_delta, new_covered, newly_uncovered,
    #  files_added, files_removed}; null on first snapshot

    project: Mapped["Project"] = relationship("Project", back_populates="snapshots")
