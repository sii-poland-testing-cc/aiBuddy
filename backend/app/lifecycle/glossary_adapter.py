"""
Glossary lifecycle adapter — Phase 4 implementation.

Conflict rule (Decision D9):
  Same term name (case-insensitive), difflib.SequenceMatcher ratio < 0.85
  on normalized definitions → conflict.
"""

import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ArtifactAuditLog, ArtifactLifecycle, Project, PromotionConflict
from app.lifecycle.interface import (
    ArtifactLifecycleAdapter,
    ArtifactType,
    ConflictItem,
)


def _def_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


class GlossaryAdapter(ArtifactLifecycleAdapter):
    """Lifecycle adapter for glossary terms (stored in Project.glossary JSON)."""

    artifact_type = ArtifactType.GLOSSARY_TERM

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_items_in_context(
        self, project_id: str, work_context_id: str
    ) -> list[dict[str, Any]]:
        """Return all glossary terms belonging to the given work context."""
        stmt = select(ArtifactLifecycle).where(
            ArtifactLifecycle.project_id == project_id,
            ArtifactLifecycle.artifact_type == "glossary_term",
            ArtifactLifecycle.work_context_id == work_context_id,
        )
        manifest_rows = (await self.db.execute(stmt)).scalars().all()
        # item_id = normalized (lower-stripped) term name
        item_ids = {r.artifact_item_id for r in manifest_rows}

        project = await self.db.get(Project, project_id)
        if not project or not project.glossary:
            return []
        terms = project.glossary or []
        return [
            t for t in terms
            if str(t.get("term", "")).lower().strip() in item_ids
        ]

    def detect_conflict(
        self, incoming: dict[str, Any], existing: dict[str, Any]
    ) -> tuple[bool, str]:
        """
        Conflict when same term name (case-insensitive) has a definition
        with SequenceMatcher ratio < 0.85 (Decision D9).
        """
        inc_term = (incoming.get("term") or "").strip().lower()
        ex_term = (existing.get("term") or "").strip().lower()
        if not inc_term or not ex_term or inc_term != ex_term:
            return False, ""

        inc_def = (incoming.get("definition") or "").strip()
        ex_def = (existing.get("definition") or "").strip()

        if not inc_def or not ex_def:
            return False, ""

        ratio = _def_similarity(inc_def, ex_def)
        if ratio < 0.85:
            return True, f"definition_mismatch (similarity={ratio:.2f})"

        return False, ""

    async def merge_into_target(
        self,
        project_id: str,
        source_context_id: str,
        target_context_id: str,
        items: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[ConflictItem]]:
        """
        Merge glossary terms from source context into target context.
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
                        artifact_item_id=str(incoming.get("term", "")).lower().strip(),
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
        Apply a human resolution to a pending glossary term conflict.

        resolution:
          "keep_existing"  — keep existing term; discard incoming
          "use_incoming"   — replace existing term definition with incoming value
          "merge"          — use caller-provided resolved_value
        """
        conflict = await self.db.get(PromotionConflict, conflict_id)
        if not conflict or conflict.project_id != project_id:
            raise ValueError(f"Conflict {conflict_id!r} not found for project {project_id!r}")

        now = datetime.now(timezone.utc)
        term_id = conflict.artifact_item_id  # normalized term name

        if resolution in ("use_incoming", "merge"):
            new_term = resolved_value if resolution == "merge" else conflict.incoming_value
            if new_term:
                await _update_term_in_blob(self.db, project_id, term_id, new_term, now)

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
            artifact_type="glossary_term",
            artifact_item_id=term_id,
            event_type="conflict_resolved",
            new_value={"resolution": resolution, "conflict_id": conflict_id},
            actor="human",
            created_at=now,
        ))
        await self.db.commit()


async def _update_term_in_blob(
    db: AsyncSession,
    project_id: str,
    term_id: str,  # normalized (lower) term name
    new_term: dict[str, Any],
    now: datetime,
) -> None:
    """Replace a term in Project.glossary by normalized name."""
    project = await db.get(Project, project_id)
    if not project or not project.glossary:
        return
    project.glossary = [
        new_term if str(t.get("term", "")).lower().strip() == term_id else t
        for t in (project.glossary or [])
    ]
    project.context_built_at = now
