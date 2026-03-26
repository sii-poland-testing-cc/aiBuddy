"""
Requirements lifecycle adapter — Phase 3 implementation.

Conflict rules:
  1. Same external_id with title similarity < 0.70 → conflict ("title_mismatch")
  2. Same external_id with description similarity < 0.50 → conflict ("description_mismatch")
  3. Different external_id but same title (case-insensitive) → conflict ("duplicate_title")
"""

import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ArtifactAuditLog, PromotionConflict
from app.db.requirements_models import Requirement
from app.lifecycle.interface import (
    ArtifactLifecycleAdapter,
    ArtifactType,
    ConflictItem,
)


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
        """Return all requirements belonging to the given work context."""
        stmt = select(Requirement).where(
            Requirement.project_id == project_id,
            Requirement.work_context_id == work_context_id,
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return [
            {
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
            }
            for r in rows
        ]

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
        Compares each incoming item against all existing items in the target context.
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

        resolution:
          "keep_existing"  — discard incoming; mark conflict resolved
          "use_incoming"   — update existing requirement with incoming values
          "merge"          — caller provides resolved_value to write
        """
        conflict = await self.db.get(PromotionConflict, conflict_id)
        if not conflict or conflict.project_id != project_id:
            raise ValueError(f"Conflict {conflict_id!r} not found for project {project_id!r}")

        now = datetime.now(timezone.utc)

        if resolution == "use_incoming" and resolved_value:
            req = await self.db.get(Requirement, resolved_value.get("id", ""))
            if req and req.project_id == project_id:
                req.title = resolved_value.get("title", req.title)
                req.description = resolved_value.get("description", req.description)
                req.external_id = resolved_value.get("external_id", req.external_id)
                req.updated_at = now
        elif resolution == "merge" and resolved_value:
            req_id = resolved_value.get("id", "")
            req = await self.db.get(Requirement, req_id)
            if req and req.project_id == project_id:
                for field in ("title", "description", "external_id", "taxonomy"):
                    if field in resolved_value:
                        setattr(req, field, resolved_value[field])
                req.updated_at = now

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
