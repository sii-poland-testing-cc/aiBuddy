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

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
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
    work_contexts: Mapped[List["WorkContext"]] = relationship(
        "WorkContext",
        back_populates="project",
        cascade="all, delete-orphan",
        lazy="noload",
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

    # Lifecycle fields (Phase 1) — null until Phase 3 wires save_snapshot()
    work_context_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("work_contexts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    lifecycle_status: Mapped[str] = mapped_column(
        String, nullable=False, default="promoted"
    )
    # "draft" | "active" | "ready" | "promoted" | "archived" | "conflict_pending"

    project: Mapped["Project"] = relationship("Project", back_populates="snapshots")


# ─── Lifecycle Models (Phase 1) ───────────────────────────────────────────────


class WorkContext(Base):
    """
    Represents a scoped unit of work: Domain, Epic, or Story.

    Hierarchy:
      Domain (no parent)
        └── Epic  (parent = Domain)
              └── Story (parent = Epic)

    Multiple Domains per project are allowed. One named "Default Domain"
    is auto-created on project creation (Phase 2).
    """
    __tablename__ = "work_contexts"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("work_contexts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    level: Mapped[str] = mapped_column(String, nullable=False)
    # "domain" | "epic" | "story"

    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String, nullable=False, default="draft")
    # "draft" | "active" | "ready" | "promoted" | "archived"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    promoted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    project: Mapped["Project"] = relationship("Project", back_populates="work_contexts")

    children: Mapped[List["WorkContext"]] = relationship(
        "WorkContext",
        back_populates="parent",
        lazy="noload",
    )
    parent: Mapped[Optional["WorkContext"]] = relationship(
        "WorkContext",
        back_populates="children",
        remote_side="WorkContext.id",
        lazy="noload",
    )


class ArtifactAuditLog(Base):
    """
    Append-only event log for every lifecycle state change on any artifact item.
    Never updated or deleted — replay events to reconstruct item history.
    """
    __tablename__ = "artifact_audit_log"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    artifact_type: Mapped[str] = mapped_column(String, nullable=False)
    # "graph_node" | "graph_edge" | "glossary_term" | "requirement" | "audit_snapshot"

    artifact_item_id: Mapped[str] = mapped_column(String, nullable=False)
    # node.id / edge "{src}→{tgt}" / term normalized_name / req id / snapshot id

    event_type: Mapped[str] = mapped_column(String, nullable=False)
    # "created" | "updated" | "status_changed" | "promoted"
    # | "conflict_detected" | "conflict_resolved" | "archived"

    work_context_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("work_contexts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    old_value: Mapped[Optional[dict]] = mapped_column(JsonType(), nullable=True)
    new_value: Mapped[Optional[dict]] = mapped_column(JsonType(), nullable=True)

    actor: Mapped[str] = mapped_column(String, nullable=False, default="system")
    # "system" | "human"

    actor_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # user identifier; null until auth is introduced

    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class PromotionConflict(Base):
    """
    Queue of items that require human resolution before promotion can complete.
    AI detects conflicts; humans resolve them.
    """
    __tablename__ = "promotion_conflicts"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    artifact_type: Mapped[str] = mapped_column(String, nullable=False)
    # "graph_node" | "graph_edge" | "glossary_term" | "requirement" | "audit_snapshot"

    artifact_item_id: Mapped[str] = mapped_column(String, nullable=False)
    # identifier of the incoming item (node id, term name, req id, …)

    source_context_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("work_contexts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # the Story / Epic being promoted

    target_context_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("work_contexts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # the Epic / Domain being promoted INTO

    incoming_value: Mapped[dict] = mapped_column(JsonType(), nullable=False)
    existing_value: Mapped[dict] = mapped_column(JsonType(), nullable=False)
    conflict_reason: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    # "pending" | "resolved_accept_new" | "resolved_keep_old"
    # | "resolved_edited" | "deferred"

    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    resolution_value: Mapped[Optional[dict]] = mapped_column(JsonType(), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class ArtifactLifecycle(Base):
    """
    Lifecycle manifest for JSON-stored artifact items (graph nodes, edges, glossary terms).
    One row per item. The JSON blob on Project remains the content source of truth;
    this table is the lifecycle source of truth.
    """
    __tablename__ = "artifact_lifecycle"

    __table_args__ = (
        UniqueConstraint(
            "project_id", "artifact_type", "artifact_item_id",
            name="uq_artifact_lifecycle_item",
        ),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    artifact_type: Mapped[str] = mapped_column(String, nullable=False)
    # "graph_node" | "graph_edge" | "glossary_term"

    artifact_item_id: Mapped[str] = mapped_column(String, nullable=False)
    # graph node.id / edge "{source}→{target}" / term normalized name

    work_context_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("work_contexts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    lifecycle_status: Mapped[str] = mapped_column(
        String, nullable=False, default="promoted"
    )
    # "draft" | "active" | "ready" | "promoted" | "archived" | "conflict_pending"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PromotionLock(Base):
    """
    Application-level promotion lock for SQLite (no SELECT … FOR UPDATE).

    One row per (project_id, target_context_id) while a promotion is in progress.
    INSERT fails on unique constraint if another promotion is already running.
    The row is deleted when the promotion completes or fails.
    PostgreSQL deployments use SELECT … FOR UPDATE instead.
    """
    __tablename__ = "promotion_locks"

    __table_args__ = (
        UniqueConstraint(
            "project_id", "target_context_id",
            name="uq_promotion_lock_project_target",
        ),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_context_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("work_contexts.id", ondelete="CASCADE"),
        nullable=False,
    )
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    acquired_by: Mapped[str] = mapped_column(
        String, nullable=False, default="system"
    )


class ArtifactVersion(Base):
    """
    Immutable version history for artifact items.

    Every edit creates a new version — never overwrites.  Visibility rows point
    to a specific version, pinning the exact state that was promoted.  Subsequent
    edits in the source context create new versions that are NOT automatically
    visible at promoted levels — they require a new promotion cycle.  This
    guarantees Domain stability (Design Decision D12).
    """
    __tablename__ = "artifact_versions"

    __table_args__ = (
        UniqueConstraint(
            "project_id", "artifact_type", "artifact_item_id", "version_number",
            name="uq_artifact_version_item_ver",
        ),
        Index(
            "ix_artifact_ver_item_version_desc",
            "project_id", "artifact_type", "artifact_item_id", "version_number",
        ),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    artifact_type: Mapped[str] = mapped_column(String, nullable=False)
    # "graph_node" | "graph_edge" | "glossary_term" | "requirement" | "audit_snapshot"

    artifact_item_id: Mapped[str] = mapped_column(String, nullable=False)
    # stable item identity (same as artifact_visibility.artifact_item_id)

    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # monotonic per item: 1, 2, 3…

    content_snapshot: Mapped[Optional[dict]] = mapped_column(JsonType(), nullable=True)
    # complete serialized state at this version

    created_in_context_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("work_contexts.id", ondelete="SET NULL"),
        nullable=True,
    )

    change_summary: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # e.g. "initial version", "title updated", "merged from Story-42"

    created_by: Mapped[str] = mapped_column(
        String, nullable=False, default="system"
    )
    # "system" | "human" | "ai"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class ArtifactVisibility(Base):
    """
    Visibility manifest for all artifact items (graph nodes, edges, glossary terms,
    requirements, audit snapshots).

    One row per (item × context where visible).  The same item may appear in
    multiple contexts — that is the foundation of the reference-based promotion
    model (Decision D10, "Copy Up, Not Move Up").

    Semantics:
      - When an item is CREATED in Story-107:
        INSERT one row: source_context_id=Story-107, visible_in_context_id=Story-107
      - When that item is PROMOTED to Epic-12:
        INSERT second row: source_context_id=Story-107, visible_in_context_id=Epic-12,
        lifecycle_status="promoted"
        The original row stays unchanged.
      - When later promoted to Domain:
        INSERT third row: source_context_id=Story-107, visible_in_context_id=Domain-1
        The item now has 3 visibility rows but ONE canonical data location.
      - On CONFLICT RESOLUTION with "Edit & Merge":
        A NEW item is created in the target context (sibling_of=original_item_id).
        It gets its own visibility row in the target context.
        The original item's visibility is NOT extended (it lost the merge).

    The JSON blob on Project / Requirement table remains the content source of truth;
    this table is the visibility and lifecycle source of truth.
    """
    __tablename__ = "artifact_visibility"

    __table_args__ = (
        UniqueConstraint(
            "project_id", "artifact_type", "artifact_item_id", "visible_in_context_id",
            name="uq_artifact_visibility_item_ctx",
        ),
        # Primary query path: "show me everything visible in context X"
        Index(
            "ix_artifact_vis_project_visible_type",
            "project_id", "visible_in_context_id", "artifact_type",
        ),
        # "What was created in this context?"
        Index(
            "ix_artifact_vis_project_source_type",
            "project_id", "source_context_id", "artifact_type",
        ),
        # Item history across all contexts
        Index(
            "ix_artifact_vis_project_type_item",
            "project_id", "artifact_type", "artifact_item_id",
        ),
        # "Find everything from this source file/URL"
        Index(
            "ix_artifact_vis_project_origin",
            "project_id", "source_origin",
        ),
    )

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )

    artifact_type: Mapped[str] = mapped_column(String, nullable=False)
    # "graph_node" | "graph_edge" | "glossary_term" | "requirement" | "audit_snapshot"

    artifact_item_id: Mapped[str] = mapped_column(String, nullable=False)
    # canonical identifier: node.id / edge "{src}→{tgt}" /
    # normalized term / requirement.id / snapshot.id

    source_context_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("work_contexts.id", ondelete="SET NULL"),
        nullable=True,
    )
    # the context where this item was CREATED (canonical home)

    visible_in_context_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("work_contexts.id", ondelete="SET NULL"),
        nullable=True,
    )
    # the context where this item is VISIBLE
    # when source_context_id == visible_in_context_id: item is in its home
    # when they differ: this is a promotion visibility reference

    lifecycle_status: Mapped[str] = mapped_column(
        String, nullable=False, default="draft"
    )
    # "draft" | "active" | "ready" | "promoted" | "archived" | "conflict_pending"

    sibling_of: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # if this item was created by "Edit & Merge" conflict resolution,
    # points to the original artifact_item_id it was derived from
    # NULL for all regular items

    artifact_version_id: Mapped[Optional[str]] = mapped_column(
        String,
        ForeignKey("artifact_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    # points to the specific version of this item that is visible in this context
    # NULL for legacy rows not yet backfilled; D12 guarantees non-NULL going forward

    source_origin: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # where did the knowledge come from: file path, URL, "manual"

    source_origin_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # "file" | "url" | "manual" | "system"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
