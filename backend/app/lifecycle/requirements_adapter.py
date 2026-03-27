"""
Requirements lifecycle adapter — Phase 3 + D12 versioning (D10 visibility model).

Conflict rules:
  1. Same external_id with title similarity < 0.70 → conflict ("title_mismatch")
  2. Same external_id with description similarity < 0.50 → conflict ("description_mismatch")
  3. Different external_id but same title (case-insensitive) → conflict ("duplicate_title")

Visibility model (D12):
  get_items_in_context() JOINs artifact_visibility → artifact_versions and
  returns content from the pinned version snapshot (not from live Requirement rows).
  This returns items CREATED here AND items PROMOTED here from children.

  merge_into_target() creates visibility rows (not requirement copies).
  For conflicts: queues them without creating visibility.
"""

import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ArtifactAuditLog, ArtifactVersion, ArtifactVisibility, PromotionConflict
from app.db.requirements_models import Requirement
from app.lifecycle.interface import (
    ArtifactLifecycleAdapter,
    ArtifactType,
    ConflictItem,
)
from app.services.versioning import create_version, get_current_version


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


class RequirementsAdapter(ArtifactLifecycleAdapter):
    """Lifecycle adapter for requirements (stored as rows in the requirements table)."""

    artifact_type = ArtifactType.REQUIREMENT

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_items_in_context(
        self, project_id: str, work_context_id: str
    ) -> list[dict[str, Any]]:
        """
        Return all requirements VISIBLE in the given work context.

        D12: JOINs artifact_visibility → artifact_versions and returns
        content from the pinned version snapshot (not from live Requirement rows).
        Falls back to live data for pre-visibility or pre-versioning compat.
        """
        # Primary path: JOIN visibility → versions for snapshot content
        stmt = (
            select(ArtifactVersion, ArtifactVisibility)
            .join(ArtifactVersion, ArtifactVisibility.artifact_version_id == ArtifactVersion.id)
            .where(
                ArtifactVisibility.project_id == project_id,
                ArtifactVisibility.artifact_type == "requirement",
                ArtifactVisibility.visible_in_context_id == work_context_id,
            )
        )
        rows = (await self.db.execute(stmt)).all()
        if rows:
            return [self._snapshot_to_dict(ver.content_snapshot, vis) for ver, vis in rows]

        # Fallback: no versioned visibility rows → check direct work_context_id
        # (backwards compat for requirements created before visibility/versioning)
        return await self._get_items_direct(project_id, work_context_id)

    async def _get_items_direct(
        self, project_id: str, work_context_id: str
    ) -> list[dict[str, Any]]:
        """Fallback: query requirements directly by work_context_id (pre-visibility compat)."""
        stmt = select(Requirement).where(
            Requirement.project_id == project_id,
            Requirement.work_context_id == work_context_id,
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return [self._req_to_dict(r) for r in rows]

    @staticmethod
    def _snapshot_to_dict(
        snapshot: dict[str, Any], vis: ArtifactVisibility
    ) -> dict[str, Any]:
        """Build requirement dict from version snapshot + visibility metadata."""
        result = dict(snapshot)
        # Fill in metadata fields from visibility (not stored in snapshot)
        result.setdefault("project_id", vis.project_id)
        result.setdefault("parent_id", None)
        result.setdefault("work_context_id", vis.source_context_id)
        result.setdefault("lifecycle_status", vis.lifecycle_status)
        result.setdefault("source_origin", vis.source_origin)
        result.setdefault("source_origin_type", vis.source_origin_type)
        return result

    @staticmethod
    def _req_to_dict(r: Requirement) -> dict[str, Any]:
        return {
            "id": r.id,
            "project_id": r.project_id,
            "parent_id": r.parent_id,
            "level": r.level,
            "external_id": r.external_id,
            "title": r.title,
            "description": r.description or "",
            "source_type": r.source_type,
            "taxonomy": r.taxonomy,
            "confidence": r.confidence,
            "work_context_id": r.work_context_id,
            "lifecycle_status": r.lifecycle_status,
            "source_origin": r.source_origin,
            "source_origin_type": r.source_origin_type,
        }

    def detect_conflict(
        self, incoming: dict[str, Any], existing: dict[str, Any]
    ) -> tuple[bool, str]:
        """
        Type-specific conflict detection for requirements.

        Rule 1: Same external_id → check title similarity (threshold 0.70)
        Rule 2: Same external_id → check description similarity (threshold 0.50)
        Rule 3: Different external_id but identical title (case-insensitive) → duplicate
        """
        inc_ext = (incoming.get("external_id") or "").strip()
        ex_ext = (existing.get("external_id") or "").strip()

        inc_title = (incoming.get("title") or "").strip()
        ex_title = (existing.get("title") or "").strip()

        if inc_ext and ex_ext and inc_ext == ex_ext:
            title_sim = _similarity(inc_title, ex_title)
            if title_sim < 0.70:
                return True, f"title_mismatch (similarity={title_sim:.2f})"

            inc_desc = (incoming.get("description") or "").strip()
            ex_desc = (existing.get("description") or "").strip()
            if inc_desc and ex_desc:
                desc_sim = _similarity(inc_desc, ex_desc)
                if desc_sim < 0.50:
                    return True, f"description_mismatch (similarity={desc_sim:.2f})"

        # Rule 3: same title, different external_id — likely duplicate
        if inc_title and ex_title and inc_title.lower() == ex_title.lower():
            if inc_ext != ex_ext:
                return True, "duplicate_title"

        return False, ""

    async def merge_into_target(
        self,
        project_id: str,
        source_context_id: str,
        target_context_id: str,
        items: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[ConflictItem]]:
        """
        Merge requirements from source context into target context.

        D10 visibility model: does NOT copy requirement rows.
        For clean items: INSERT artifact_visibility row with
        visible_in_context_id = target_context_id.
        For conflicts: queue them without creating visibility.
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
                        artifact_item_id=incoming["id"],
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
        Apply a human resolution to a pending conflict.

        D10 sibling semantics:
          "keep_existing"  — close conflict, no visibility change
          "use_incoming"   — INSERT visibility row for incoming item in target;
                            supersede existing item's visibility at target level
          "merge"          — CREATE new requirement row (sibling) with new UUID;
                            sibling_of points to original; original stays untouched
        """
        conflict = await self.db.get(PromotionConflict, conflict_id)
        if not conflict or conflict.project_id != project_id:
            raise ValueError(f"Conflict {conflict_id!r} not found for project {project_id!r}")

        now = datetime.now(timezone.utc)
        target_ctx_id = conflict.target_context_id

        if resolution == "use_incoming":
            # Supersede existing item's visibility at target level
            existing_item_id = (conflict.existing_value or {}).get("id")
            if existing_item_id:
                await _supersede_visibility(
                    self.db, project_id, "requirement", existing_item_id, target_ctx_id, now
                )
            # Make the incoming item visible in the target context
            incoming_item_id = conflict.artifact_item_id
            source_ctx_id = conflict.source_context_id

            # D12: pin to current version
            current_ver = await get_current_version(
                self.db, project_id, "requirement", incoming_item_id
            )
            self.db.add(ArtifactVisibility(
                id=str(uuid.uuid4()),
                project_id=project_id,
                artifact_type="requirement",
                artifact_item_id=incoming_item_id,
                source_context_id=source_ctx_id,
                visible_in_context_id=target_ctx_id,
                lifecycle_status="promoted",
                artifact_version_id=current_ver.id if current_ver else None,
                created_at=now,
            ))

        elif resolution == "merge" and resolved_value:
            # Create a new requirement row as a sibling of the original
            original_item_id = conflict.artifact_item_id
            new_req_id = str(uuid.uuid4())
            new_req = Requirement(
                id=new_req_id,
                project_id=project_id,
                parent_id=None,
                level=resolved_value.get("level", "functional_req"),
                external_id=resolved_value.get("external_id"),
                title=resolved_value.get("title", ""),
                description=resolved_value.get("description", ""),
                source_type=resolved_value.get("source_type", "formal"),
                taxonomy=resolved_value.get("taxonomy"),
                confidence=resolved_value.get("confidence"),
                work_context_id=target_ctx_id,
                lifecycle_status="promoted",
                created_at=now,
            )
            self.db.add(new_req)

            # D12: create v1 for the new sibling
            sibling_ver = await create_version(
                self.db, project_id, "requirement", new_req_id,
                resolved_value, target_ctx_id, "merged from conflict resolution",
            )

            # Visibility row for the new sibling in the target context
            self.db.add(ArtifactVisibility(
                id=str(uuid.uuid4()),
                project_id=project_id,
                artifact_type="requirement",
                artifact_item_id=new_req_id,
                source_context_id=target_ctx_id,
                visible_in_context_id=target_ctx_id,
                lifecycle_status="promoted",
                sibling_of=original_item_id,
                artifact_version_id=sibling_ver.id,
                created_at=now,
            ))

        # elif resolution == "keep_existing": no visibility change needed

        status_map = {
            "keep_existing": "resolved_keep_old",
            "use_incoming": "resolved_accept_new",
            "merge": "resolved_edited",
        }
        conflict.status = status_map.get(resolution, "resolved_keep_old")
        conflict.resolution_value = resolved_value
        conflict.resolved_at = now

        self.db.add(ArtifactAuditLog(
            id=str(uuid.uuid4()),
            project_id=project_id,
            artifact_type="requirement",
            artifact_item_id=conflict.artifact_item_id,
            event_type="conflict_resolved",
            new_value={"resolution": resolution, "conflict_id": conflict_id},
            actor="human",
            created_at=now,
        ))

        await self.db.commit()


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
