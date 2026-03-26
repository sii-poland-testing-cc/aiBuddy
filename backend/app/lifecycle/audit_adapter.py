"""
Audit snapshot adapter stub — Phase 2 (not yet implemented).

Note (per D7 / §2.6.1): AuditSnapshot IS wrapped in the lifecycle model.
Conflict rule (Phase 3/4 will implement):
  coverage_pct regresses >10pp vs. Domain's latest promoted snapshot,
  OR requirements_uncovered set grows (newly uncovered items) → conflict.
  Content is never merged — snapshots are immutable timestamped records.
"""

from typing import Any

from app.lifecycle.interface import (
    ArtifactLifecycleAdapter,
    ArtifactType,
    ConflictItem,
)


class AuditSnapshotAdapter(ArtifactLifecycleAdapter):
    """
    Lifecycle adapter for audit snapshots.
    Snapshots are never merged (immutable records); 'promotion' means
    the snapshot is acknowledged as Domain-level knowledge.
    """

    artifact_type = ArtifactType.AUDIT_SNAPSHOT

    async def get_items_in_context(
        self, project_id: str, work_context_id: str
    ) -> list[dict[str, Any]]:
        raise NotImplementedError("AuditSnapshotAdapter.get_items_in_context — Phase 3")

    async def merge_into_target(
        self,
        project_id: str,
        source_context_id: str,
        target_context_id: str,
        items: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[ConflictItem]]:
        raise NotImplementedError("AuditSnapshotAdapter.merge_into_target — Phase 5")

    def detect_conflict(
        self, incoming: dict[str, Any], existing: dict[str, Any]
    ) -> tuple[bool, str]:
        raise NotImplementedError("AuditSnapshotAdapter.detect_conflict — Phase 3")

    async def apply_resolution(
        self,
        project_id: str,
        conflict_id: str,
        resolution: str,
        resolved_value: dict[str, Any] | None,
    ) -> None:
        raise NotImplementedError("AuditSnapshotAdapter.apply_resolution — Phase 6")
