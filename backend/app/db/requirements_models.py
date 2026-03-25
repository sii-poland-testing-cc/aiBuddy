"""
Requirements Registry — ORM Models (Faza 2)
=============================================
Extends the core schema (models.py) with three Faza 2/5/6 tables.
Shares the same Base; engine.py imports this module as a side-effect
so all tables are registered with Base.metadata.

Tables:
  - requirements             — hierarchical requirement registry
  - requirement_tc_mappings  — requirement ↔ test case semantic mappings
  - coverage_scores          — multi-dimensional scoring per requirement
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

_log = logging.getLogger("ai_buddy.models")

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

# Import Base from existing models to share the same metadata
from app.db.models import Base
from app.db.types import JsonType


class Requirement(Base):
    """
    A single requirement at any level of the hierarchy.

    Hierarchy:  domain_concept → feature → functional_req → acceptance_criterion
    Each level can have a parent_id pointing to the level above.
    """
    __tablename__ = "requirements"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[str] = mapped_column(
        String, ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    parent_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("requirements.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    # Hierarchy level
    level: Mapped[str] = mapped_column(
        String, nullable=False, default="functional_req"
    )
    # "domain_concept" | "feature" | "functional_req" | "acceptance_criterion"

    # Original ID from source docs (e.g. "FR-017", "US-042"), nullable if reconstructed
    external_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # How was this requirement discovered?
    source_type: Mapped[str] = mapped_column(
        String, nullable=False, default="formal"
    )
    # "formal"        — extracted from SRS/BRD with explicit FR-IDs
    # "implicit"      — derived from Jira stories / acceptance criteria
    # "reconstructed" — reverse-engineered from code/tests (lowest confidence)

    # List of source filenames or references
    source_references: Mapped[Optional[list]] = mapped_column(JsonType(), nullable=True)
    # e.g. ["srs_v2.docx", "PROJ-1234"]

    # Taxonomy tags
    taxonomy: Mapped[Optional[dict]] = mapped_column(JsonType(), nullable=True)
    # e.g. {"module": "payments", "risk_level": "high", "business_domain": "compliance"}

    # Quality metrics
    completeness_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # 0.0–1.0: how complete is this requirement's definition?

    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # 0.0–1.0: how confident is the system that this requirement is real/correct?

    human_reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    # Set to True when a human has confirmed/corrected this requirement

    # Flags for human review
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # e.g. "Low confidence (0.45) — reconstructed from test names only"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Relationships
    children: Mapped[List["Requirement"]] = relationship(
        "Requirement",
        back_populates="parent",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    parent: Mapped[Optional["Requirement"]] = relationship(
        "Requirement",
        back_populates="children",
        remote_side="Requirement.id",
        lazy="noload",
    )
    tc_mappings: Mapped[List["RequirementTCMapping"]] = relationship(
        "RequirementTCMapping",
        back_populates="requirement",
        cascade="all, delete-orphan",
        lazy="noload",
    )


class RequirementTCMapping(Base):
    """
    Semantic mapping between a Requirement and a test case.

    The test case is identified by a composite key:
      - source_file: which file the TC comes from
      - tc_identifier: original ID or title within that file

    This avoids requiring a separate normalized TC table in the MVP.
    """
    __tablename__ = "requirement_tc_mappings"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    requirement_id: Mapped[str] = mapped_column(
        String, ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    project_id: Mapped[str] = mapped_column(
        String, ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Test case reference (no separate TC table in MVP)
    tc_source_file: Mapped[str] = mapped_column(String, nullable=False)
    tc_identifier: Mapped[str] = mapped_column(String, nullable=False)
    # tc_identifier = original TC ID, name, or title

    # Mapping quality
    mapping_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # 0.0–1.0: how confident is the system in this mapping?

    mapping_method: Mapped[str] = mapped_column(
        String, nullable=False, default="embedding"
    )
    # "pattern"   — regex/keyword match (e.g. TC references FR-017 explicitly)
    # "embedding" — cosine similarity above threshold
    # "llm"       — LLM-confirmed semantic match
    # "human"     — manually confirmed by user

    # What aspects of the requirement does this TC cover?
    coverage_aspects: Mapped[Optional[list]] = mapped_column(JsonType(), nullable=True)
    # e.g. ["happy_path", "negative", "boundary", "integration", "edge_case"]

    human_verified: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    requirement: Mapped["Requirement"] = relationship(
        "Requirement", back_populates="tc_mappings"
    )


class CoverageScore(Base):
    """
    Multi-dimensional coverage score per requirement per audit snapshot.

    Scoring model (0–100 total):
      base_coverage      (0–40)  — is the happy path covered?
      depth_coverage      (0–30)  — negative, boundary, edge cases
      quality_weight      (0–20)  — quality of matched TCs
      confidence_penalty  (-10–0) — penalty for low-confidence mappings
      crossref_bonus      (0–10)  — covered by both manual + automated tests
    """
    __tablename__ = "coverage_scores"

    id: Mapped[str] = mapped_column(
        String, primary_key=True, default=lambda: str(uuid.uuid4())
    )
    requirement_id: Mapped[str] = mapped_column(
        String, ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    snapshot_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("audit_snapshots.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    project_id: Mapped[str] = mapped_column(
        String, ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Score components
    total_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    base_coverage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    depth_coverage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    quality_weight: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence_penalty: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    crossref_bonus: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Context
    matched_tc_count: Mapped[int] = mapped_column(Integer, default=0)
    coverage_aspects_present: Mapped[Optional[list]] = mapped_column(JsonType(), nullable=True)
    # e.g. ["happy_path", "negative"]
    coverage_aspects_missing: Mapped[Optional[list]] = mapped_column(JsonType(), nullable=True)
    # e.g. ["boundary", "edge_case", "integration"]

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # ── Score range validators ─────────────────────────────────────────────────
    # Clamp on assignment; out-of-range values from the LLM are logged as warnings.

    @validates("total_score")
    def _clamp_total(self, _key: str, v: float) -> float:
        clamped = max(0.0, min(100.0, float(v)))
        if clamped != float(v):
            _log.warning("total_score %s clamped to %s", v, clamped)
        return clamped

    @validates("base_coverage")
    def _clamp_base(self, _key: str, v: float) -> float:
        clamped = max(0.0, min(40.0, float(v)))
        if clamped != float(v):
            _log.warning("base_coverage %s clamped to %s", v, clamped)
        return clamped

    @validates("depth_coverage")
    def _clamp_depth(self, _key: str, v: float) -> float:
        clamped = max(0.0, min(30.0, float(v)))
        if clamped != float(v):
            _log.warning("depth_coverage %s clamped to %s", v, clamped)
        return clamped

    @validates("quality_weight")
    def _clamp_quality(self, _key: str, v: float) -> float:
        clamped = max(0.0, min(20.0, float(v)))
        if clamped != float(v):
            _log.warning("quality_weight %s clamped to %s", v, clamped)
        return clamped

    @validates("confidence_penalty")
    def _clamp_penalty(self, _key: str, v: float) -> float:
        clamped = max(-10.0, min(0.0, float(v)))
        if clamped != float(v):
            _log.warning("confidence_penalty %s clamped to %s", v, clamped)
        return clamped

    @validates("crossref_bonus")
    def _clamp_crossref(self, _key: str, v: float) -> float:
        clamped = max(0.0, min(10.0, float(v)))
        if clamped != float(v):
            _log.warning("crossref_bonus %s clamped to %s", v, clamped)
        return clamped
