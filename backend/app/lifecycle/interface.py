"""
Lifecycle interface — shared ABC for all artifact-type adapters.

Every concrete adapter (graph_adapter, glossary_adapter, …) implements this
interface so the PromotionService can drive promotion without caring about
how each artifact type stores its data.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ArtifactType(str, Enum):
    GRAPH_NODE = "graph_node"
    GRAPH_EDGE = "graph_edge"
    GLOSSARY_TERM = "glossary_term"
    REQUIREMENT = "requirement"
    AUDIT_SNAPSHOT = "audit_snapshot"


class LifecycleStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    READY = "ready"
    PROMOTED = "promoted"
    ARCHIVED = "archived"
    CONFLICT_PENDING = "conflict_pending"


@dataclass
class ConflictItem:
    artifact_item_id: str
    incoming_value: dict[str, Any]
    existing_value: dict[str, Any]
    conflict_reason: str


class ArtifactLifecycleAdapter(ABC):
    """
    Shared interface implemented by all artifact-type adapters.
    Each implementation handles one artifact type's storage + lifecycle logic.
    """

    artifact_type: ArtifactType  # class-level constant, set by each concrete subclass

    @abstractmethod
    async def get_items_in_context(
        self,
        project_id: str,
        work_context_id: str,
    ) -> list[dict[str, Any]]:
        """Return all artifact items belonging to the given work context."""

    @abstractmethod
    async def merge_into_target(
        self,
        project_id: str,
        source_context_id: str,
        target_context_id: str,
        items: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[ConflictItem]]:
        """
        Attempt to merge items from source into target context.
        Returns (promoted_items, conflicts).
        Promoted items are clean (no conflict). Conflicts are queued separately.
        """

    @abstractmethod
    def detect_conflict(
        self,
        incoming: dict[str, Any],
        existing: dict[str, Any],
    ) -> tuple[bool, str]:
        """
        Type-specific conflict detection.
        Returns (has_conflict, reason_string).
        """

    @abstractmethod
    async def apply_resolution(
        self,
        project_id: str,
        conflict_id: str,
        resolution: str,
        resolved_value: dict[str, Any] | None,
    ) -> None:
        """Apply a human resolution to a pending conflict."""
