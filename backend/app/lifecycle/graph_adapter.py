"""
Graph lifecycle adapters — Phase 4 + D12 versioning (D10 visibility model).

Conflict rules:
  GraphNode:  same node.id with different label or type → conflict
  GraphEdge:  same "{source}→{target}" with different label → conflict

Visibility model (D12):
  get_items_in_context() JOINs artifact_visibility → artifact_versions and
  returns content from the pinned version snapshot (not from Project.mind_map JSON).

  merge_into_target() creates visibility rows (not JSON copies).
  apply_resolution() follows D10 semantics.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ArtifactAuditLog, ArtifactVersion, ArtifactVisibility, Project, PromotionConflict
from app.lifecycle.interface import (
    ArtifactLifecycleAdapter,
    ArtifactType,
    ConflictItem,
)
from app.services.versioning import create_version, get_current_version


class GraphNodeAdapter(ArtifactLifecycleAdapter):
    """Lifecycle adapter for knowledge-graph nodes (stored in Project.mind_map JSON)."""

    artifact_type = ArtifactType.GRAPH_NODE

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_items_in_context(
        self, project_id: str, work_context_id: str
    ) -> list[dict[str, Any]]:
        """
        Return all graph nodes VISIBLE in the given work context.

        D12: JOINs artifact_visibility → artifact_versions and returns
        content from the pinned version snapshot (not from Project.mind_map JSON).
        Falls back to mind_map JSON for pre-versioning compat.
        """
        # Primary path: JOIN visibility → versions for snapshot content
        stmt = (
            select(ArtifactVersion.content_snapshot)
            .join(ArtifactVisibility, ArtifactVisibility.artifact_version_id == ArtifactVersion.id)
            .where(
                ArtifactVisibility.project_id == project_id,
                ArtifactVisibility.artifact_type == "graph_node",
                ArtifactVisibility.visible_in_context_id == work_context_id,
            )
        )
        snapshots = (await self.db.execute(stmt)).scalars().all()
        if snapshots:
            return list(snapshots)

        # Fallback: no versioned data → read from Project.mind_map JSON
        project = await self.db.get(Project, project_id)
        if not project or not project.mind_map:
            return []
        return project.mind_map.get("nodes", [])

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
        D10: does NOT copy JSON data. Returns (promoted, conflicts).
        Caller creates visibility rows for promoted items.
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

        D10 sibling semantics:
          "keep_existing"  — close conflict, no visibility change
          "use_incoming"   — INSERT visibility row for incoming item in target;
                            supersede existing item's visibility at target level
          "merge"          — CREATE sibling node in JSON blob (new id);
                            INSERT visibility row with sibling_of = original;
                            original stays untouched in source context
        """
        conflict = await self.db.get(PromotionConflict, conflict_id)
        if not conflict or conflict.project_id != project_id:
            raise ValueError(f"Conflict {conflict_id!r} not found for project {project_id!r}")

        now = datetime.now(timezone.utc)
        node_id = conflict.artifact_item_id
        target_ctx_id = conflict.target_context_id
        audit_extra: dict[str, Any] = {}

        if resolution == "use_incoming":
            source_ctx_id = conflict.source_context_id
            # Supersede existing item's visibility at target level
            await _supersede_visibility(
                self.db, project_id, "graph_node", node_id, target_ctx_id, now
            )
            # D12: pin to current version
            current_ver = await get_current_version(
                self.db, project_id, "graph_node", node_id
            )
            self.db.add(ArtifactVisibility(
                id=str(uuid.uuid4()),
                project_id=project_id,
                artifact_type="graph_node",
                artifact_item_id=node_id,
                source_context_id=source_ctx_id,
                visible_in_context_id=target_ctx_id,
                lifecycle_status="promoted",
                artifact_version_id=current_ver.id if current_ver else None,
                created_at=now,
            ))

        elif resolution == "merge" and resolved_value:
            # Create a SIBLING node — new id, added to blob, original untouched
            sibling_id = str(uuid.uuid4())[:12]
            sibling_node = {**resolved_value, "id": sibling_id}
            await _add_node_to_blob(self.db, project_id, sibling_node, now)
            # Supersede existing item at target level
            await _supersede_visibility(
                self.db, project_id, "graph_node", node_id, target_ctx_id, now
            )
            # D12: create v1 for the sibling
            sibling_ver = await create_version(
                self.db, project_id, "graph_node", sibling_id,
                sibling_node, target_ctx_id, "merged from conflict resolution",
            )
            self.db.add(ArtifactVisibility(
                id=str(uuid.uuid4()),
                project_id=project_id,
                artifact_type="graph_node",
                artifact_item_id=sibling_id,
                source_context_id=target_ctx_id,
                visible_in_context_id=target_ctx_id,
                lifecycle_status="promoted",
                sibling_of=node_id,
                artifact_version_id=sibling_ver.id,
                created_at=now,
            ))
            audit_extra = {"sibling_item_id": sibling_id, "original_item_id": node_id}

        _resolve_conflict(conflict, resolution, resolved_value, now)

        self.db.add(ArtifactAuditLog(
            id=str(uuid.uuid4()),
            project_id=project_id,
            artifact_type="graph_node",
            artifact_item_id=node_id,
            event_type="conflict_resolved",
            new_value={"resolution": resolution, "conflict_id": conflict_id, **audit_extra},
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
        """
        Return all graph edges VISIBLE in the given work context.

        D12: JOINs artifact_visibility → artifact_versions and returns
        content from the pinned version snapshot (not from Project.mind_map JSON).
        Falls back to mind_map JSON for pre-versioning compat.
        """
        # Primary path: JOIN visibility → versions for snapshot content
        stmt = (
            select(ArtifactVersion.content_snapshot)
            .join(ArtifactVisibility, ArtifactVisibility.artifact_version_id == ArtifactVersion.id)
            .where(
                ArtifactVisibility.project_id == project_id,
                ArtifactVisibility.artifact_type == "graph_edge",
                ArtifactVisibility.visible_in_context_id == work_context_id,
            )
        )
        snapshots = (await self.db.execute(stmt)).scalars().all()
        if snapshots:
            return list(snapshots)

        # Fallback: no versioned data → read from Project.mind_map JSON
        project = await self.db.get(Project, project_id)
        if not project or not project.mind_map:
            return []
        return project.mind_map.get("edges", [])

    def detect_conflict(
        self, incoming: dict[str, Any], existing: dict[str, Any]
    ) -> tuple[bool, str]:
        """Conflict when same {source}→{target} pair has a different label."""
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
        """Merge graph edges from source into target. Returns (promoted, conflicts)."""
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
        """
        Apply a human resolution to a pending graph edge conflict.

        D10 sibling semantics:
          "use_incoming"  — supersede existing + promote incoming
          "merge"         — edge identity IS source→target pair, so "merge" updates
                           the existing edge label in-place (no true sibling possible)
        """
        conflict = await self.db.get(PromotionConflict, conflict_id)
        if not conflict or conflict.project_id != project_id:
            raise ValueError(f"Conflict {conflict_id!r} not found for project {project_id!r}")

        now = datetime.now(timezone.utc)
        edge_id = conflict.artifact_item_id
        target_ctx_id = conflict.target_context_id

        if resolution == "use_incoming":
            await _supersede_visibility(
                self.db, project_id, "graph_edge", edge_id, target_ctx_id, now
            )
            # D12: pin to current version
            current_ver = await get_current_version(
                self.db, project_id, "graph_edge", edge_id
            )
            self.db.add(ArtifactVisibility(
                id=str(uuid.uuid4()),
                project_id=project_id,
                artifact_type="graph_edge",
                artifact_item_id=edge_id,
                source_context_id=conflict.source_context_id,
                visible_in_context_id=target_ctx_id,
                lifecycle_status="promoted",
                artifact_version_id=current_ver.id if current_ver else None,
                created_at=now,
            ))

        elif resolution == "merge" and resolved_value:
            # Edge identity = source→target pair; can't create a "sibling" edge
            # with the same endpoints. Update label in-place instead.
            await _update_edge_in_blob(self.db, project_id, edge_id, resolved_value, now)

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


async def _supersede_visibility(
    db: AsyncSession,
    project_id: str,
    artifact_type: str,
    item_id: str,
    target_ctx_id: str,
    now: datetime,
) -> None:
    """Mark existing item's visibility row as 'superseded' in the target context."""
    stmt = select(ArtifactVisibility).where(
        ArtifactVisibility.project_id == project_id,
        ArtifactVisibility.artifact_type == artifact_type,
        ArtifactVisibility.artifact_item_id == item_id,
        ArtifactVisibility.visible_in_context_id == target_ctx_id,
        ArtifactVisibility.lifecycle_status != "superseded",
    )
    row = (await db.execute(stmt)).scalars().first()
    if row:
        row.lifecycle_status = "superseded"
        row.updated_at = now


async def _add_node_to_blob(
    db: AsyncSession,
    project_id: str,
    new_node: dict[str, Any],
    now: datetime,
) -> None:
    """Add a sibling node to Project.mind_map.nodes (append, not replace)."""
    project = await db.get(Project, project_id)
    if not project or not project.mind_map:
        return
    nodes = list(project.mind_map.get("nodes", []))
    nodes.append(new_node)
    project.mind_map = {
        "nodes": nodes,
        "edges": project.mind_map.get("edges", []),
    }
    project.context_built_at = now


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
