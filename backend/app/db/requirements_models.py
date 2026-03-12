"""
Requirements Registry — ORM Models (Faza 2)
=============================================
New tables extending the existing AI Buddy schema (models.py).

Add this import to your existing models.py or keep as a separate file
and import Base from the main models module.

Tables:
  - requirements          — hierarchical requirement registry
  - requirement_tc_mappings — requirement ↔ test case semantic mappings
  - coverage_scores        — multi-dimensional scoring per requirement per snapshot
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Import Base from existing models to share the same metadata
from app.db.models import Base


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

    # JSON: list of source filenames or references
    source_references: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # e.g. '["srs_v2.docx", "PROJ-1234"]'

    # Taxonomy tags (JSON)
    taxonomy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # e.g. '{"module": "payments", "risk_level": "high", "business_domain": "compliance"}'

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
    coverage_aspects: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # JSON: ["happy_path", "negative", "boundary", "integration", "edge_case"]

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
    coverage_aspects_present: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # JSON: ["happy_path", "negative"]
    coverage_aspects_missing: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # JSON: ["boundary", "edge_case", "integration"]

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
