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

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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
    mind_map: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    glossary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    context_stats: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    context_built_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    context_files: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

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
        String, nullable=True
    )
    # snapshot id of the last audit that used this file
    # null = never used in any audit → default selected

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
    files_used: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # JSON: ["file1.xlsx", "jira:PROJ-1234"]

    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # JSON: {coverage_pct, duplicates_found, requirements_total,
    #        requirements_covered, untagged_cases}

    requirements_uncovered: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # JSON: ["FR-001", "FR-005", ...]

    recommendations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # JSON: ["recommendation 1", "recommendation 2", ...]

    diff: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # JSON: {
    #   coverage_delta: +12.5,
    #   duplicates_delta: -2,
    #   new_covered: ["FR-003"],
    #   newly_uncovered: ["FR-007"],
    #   files_added: ["v17.xlsx"],
    #   files_removed: ["v16.xlsx"]
    # }
    # null on first snapshot (no previous to compare against)

    project: Mapped["Project"] = relationship("Project", back_populates="snapshots")
