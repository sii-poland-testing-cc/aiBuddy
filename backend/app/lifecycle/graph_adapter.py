"""
Graph lifecycle adapters — Phase 4 implementation.

Conflict rules:
  GraphNode:  same node.id with different label or type → conflict
  GraphEdge:  same "{source}→{target}" with different label → conflict

Both adapters read from / write to the Project.mind_map JSON blob and
the ArtifactLifecycle manifest table.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ArtifactAuditLog, ArtifactLifecycle, Project, PromotionConflict
from app.lifecycle.interface import (
    ArtifactLifecycleAdapter,
    ArtifactType,
    ConflictItem,
)


class GraphNodeAdapter(ArtifactLifecycleAdapter):
    """Lifecycle adapter for knowledge-graph nodes (stored in Project.mind_map JSON)."""

    artifact_type = ArtifactType.GRAPH_NODE

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_items_in_context(
        self, project_id: str, work_context_id: str
    ) -> list[dict[str, Any]]:
        """Return all graph nodes belonging to the given work context."""
        stmt = select(ArtifactLifecycle).where(
            ArtifactLifecycle.project_id == project_id,
            ArtifactLifecycle.artifact_type == "graph_node",
            ArtifactLifecycle.work_context_id == work_context_id,
        )
        manifest_rows = (await self.db.execute(stmt)).scalars().all()
        item_ids = {r.artifact_item_id for r in manifest_rows}

        project = await self.db.get(Project, project_id)
        if not project or not project.mind_map:
            return []
        nodes = project.mind_map.get("nodes", [])
        return [n for n in nodes if str(n.get("id", "")) in item_ids]

    def detect_conflict(
        self, incoming: dict[str, Any], existing: dict[str, Any]
    ) -> tuple[bool, str]:
        """
        Conflict when same node id has different label or type.
        Items with different ids cannot conflict by definition.
        """
        if incoming.get("id") != existing.get("id"):
            return False, ""

        inc_label = (incoming.get("label") or "").strip()
        ex_label = (existing.get("label") or "").strip()
        if inc_label and ex_label and inc_label != ex_label:
            return True, f"label_mismatch: {ex_label!r} → {inc_label!r}"

        inc_type = (incoming.get("type") or "").strip()
        ex_type = (existing.get("type") or "").strip()
        if inc_type and ex_type and inc_type != ex_type:
            return True, f"type_mismatch: {ex_type!r} → {inc_type!r}"

        return False, ""

    async def merge_into_target(
        self,
        project_id: str,
        source_context_id: str,
        target_context_id: str,
        items: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[ConflictItem]]:
        """
        Merge graph nodes from source context into target context.
        Returns (promoted_items, conflicts).
        """
        existing = await self.get_items_in_context(project_id, target_context_id)
        promoted: list[dict[str, Any]] = []
        conflicts: list[ConflictItem] = []

        for incoming in items:
            conflict_found = False
            for ex in existing:
                has_conflict, reason = self.detect_conflict(incoming, ex)
                if has_conflict:
                    conflicts.append(ConflictItem(
                        artifact_item_id=str(incoming.get("id", "")),
                        incoming_value=incoming,
                        existing_value=ex,
                        conflict_reason=reason,
                    ))
                    conflict_found = True
                    break
            if not conflict_found:
                promoted.append(incoming)

        return promoted, conflicts

    async def apply_resolution(
        self,
        project_id: str,
        conflict_id: str,
        resolution: str,
        resolved_value: dict[str, Any] | None,
    ) -> None:
        """
        Apply a human resolution to a pending graph node conflict.

        resolution:
          "keep_existing"  — keep existing node; discard incoming
          "use_incoming"   — replace existing node with incoming value
          "merge"          — use caller-provided resolved_value
        """
        conflict = await self.db.get(PromotionConflict, conflict_id)
        if not conflict or conflict.project_id != project_id:
            raise ValueError(f"Conflict {conflict_id!r} not found for project {project_id!r}")

        now = datetime.now(timezone.utc)
        node_id = conflict.artifact_item_id

        if resolution in ("use_incoming", "merge"):
            new_node = resolved_value if resolution == "merge" else conflict.incoming_value
            if new_node:
                await _update_node_in_blob(self.db, project_id, node_id, new_node, now)

        _resolve_conflict(conflict, resolution, resolved_value, now)

        self.db.add(ArtifactAuditLog(
            id=str(uuid.uuid4()),
            project_id=project_id,
            artifact_type="graph_node",
            artifact_item_id=node_id,
            event_type="conflict_resolved",
            new_value={"resolution": resolution, "conflict_id": conflict_id},
            actor="human",
            created_at=now,
        ))
        await self.db.commit()


class GraphEdgeAdapter(ArtifactLifecycleAdapter):
    """Lifecycle adapter for knowledge-graph edges (stored in Project.mind_map JSON)."""

    artifact_type = ArtifactType.GRAPH_EDGE

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_items_in_context(
        self, project_id: str, work_context_id: str
    ) -> list[dict[str, Any]]:
        """Return all graph edges belonging to the given work context."""
        stmt = select(ArtifactLifecycle).where(
            ArtifactLifecycle.project_id == project_id,
            ArtifactLifecycle.artifact_type == "graph_edge",
            ArtifactLifecycle.work_context_id == work_context_id,
        )
        manifest_rows = (await self.db.execute(stmt)).scalars().all()
        item_ids = {r.artifact_item_id for r in manifest_rows}

        project = await self.db.get(Project, project_id)
        if not project or not project.mind_map:
            return []
        edges = project.mind_map.get("edges", [])
        return [
            e for e in edges
            if f"{e.get('source')}→{e.get('target')}" in item_ids
        ]

    def detect_conflict(
        self, incoming: dict[str, Any], existing: dict[str, Any]
    ) -> tuple[bool, str]:
        """
        Conflict when same {source}→{target} pair has a different label.
        """
        if (incoming.get("source") != existing.get("source") or
                incoming.get("target") != existing.get("target")):
            return False, ""

        inc_label = (incoming.get("label") or "").strip()
        ex_label = (existing.get("label") or "").strip()
        if inc_label and ex_label and inc_label != ex_label:
            return True, f"label_mismatch: {ex_label!r} → {inc_label!r}"

        return False, ""

    async def merge_into_target(
        self,
        project_id: str,
        source_context_id: str,
        target_context_id: str,
        items: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[ConflictItem]]:
        """
        Merge graph edges from source context into target context.
        Returns (promoted_items, conflicts).
        """
        existing = await self.get_items_in_context(project_id, target_context_id)
        promoted: list[dict[str, Any]] = []
        conflicts: list[ConflictItem] = []

        for incoming in items:
            conflict_found = False
            for ex in existing:
                has_conflict, reason = self.detect_conflict(incoming, ex)
                if has_conflict:
                    edge_id = f"{incoming.get('source')}→{incoming.get('target')}"
                    conflicts.append(ConflictItem(
                        artifact_item_id=edge_id,
                        incoming_value=incoming,
                        existing_value=ex,
                        conflict_reason=reason,
                    ))
                    conflict_found = True
                    break
            if not conflict_found:
                promoted.append(incoming)

        return promoted, conflicts

    async def apply_resolution(
        self,
        project_id: str,
        conflict_id: str,
        resolution: str,
        resolved_value: dict[str, Any] | None,
    ) -> None:
        """Apply a human resolution to a pending graph edge conflict."""
        conflict = await self.db.get(PromotionConflict, conflict_id)
        if not conflict or conflict.project_id != project_id:
            raise ValueError(f"Conflict {conflict_id!r} not found for project {project_id!r}")

        now = datetime.now(timezone.utc)
        edge_id = conflict.artifact_item_id  # "{source}→{target}"

        if resolution in ("use_incoming", "merge"):
            new_edge = resolved_value if resolution == "merge" else conflict.incoming_value
            if new_edge:
                await _update_edge_in_blob(self.db, project_id, edge_id, new_edge, now)

        _resolve_conflict(conflict, resolution, resolved_value, now)

        self.db.add(ArtifactAuditLog(
            id=str(uuid.uuid4()),
            project_id=project_id,
            artifact_type="graph_edge",
            artifact_item_id=edge_id,
            event_type="conflict_resolved",
            new_value={"resolution": resolution, "conflict_id": conflict_id},
            actor="human",
            created_at=now,
        ))
        await self.db.commit()


# ─── Shared helpers ───────────────────────────────────────────────────────────

def _resolve_conflict(
    conflict: PromotionConflict,
    resolution: str,
    resolved_value: Optional[dict[str, Any]],
    now: datetime,
) -> None:
    status_map = {
        "keep_existing": "resolved_keep_old",
        "use_incoming": "resolved_accept_new",
        "merge": "resolved_edited",
    }
    conflict.status = status_map.get(resolution, "resolved_keep_old")
    conflict.resolution_value = resolved_value
    conflict.resolved_at = now


async def _update_node_in_blob(
    db: AsyncSession,
    project_id: str,
    node_id: str,
    new_node: dict[str, Any],
    now: datetime,
) -> None:
    """Replace a node in Project.mind_map.nodes by id."""
    project = await db.get(Project, project_id)
    if not project or not project.mind_map:
        return
    nodes = project.mind_map.get("nodes", [])
    project.mind_map = {
        "nodes": [new_node if n.get("id") == node_id else n for n in nodes],
        "edges": project.mind_map.get("edges", []),
    }
    project.context_built_at = now  # bump so status reflects update


async def _update_edge_in_blob(
    db: AsyncSession,
    project_id: str,
    edge_id: str,
    new_edge: dict[str, Any],
    now: datetime,
) -> None:
    """Replace an edge in Project.mind_map.edges by '{source}→{target}' key."""
    project = await db.get(Project, project_id)
    if not project or not project.mind_map:
        return
    edges = project.mind_map.get("edges", [])
    project.mind_map = {
        "nodes": project.mind_map.get("nodes", []),
        "edges": [
            new_edge if f"{e.get('source')}→{e.get('target')}" == edge_id else e
            for e in edges
        ],
    }
    project.context_built_at = now
