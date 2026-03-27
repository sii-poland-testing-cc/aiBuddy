"""
Glossary lifecycle adapter — Phase 4 + D12 versioning (D10 visibility model).

Conflict rule (Decision D9):
  Same term name (case-insensitive), difflib.SequenceMatcher ratio < 0.85
  on normalized definitions → conflict.

Visibility model (D12):
  get_items_in_context() JOINs artifact_visibility → artifact_versions and
  returns content from the pinned version snapshot (not from Project.glossary JSON).
  merge_into_target() creates visibility rows (not data copies).
"""

import uuid
from datetime import datetime, timezone
from difflib import SequenceMatcher
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
        """
        Return all glossary terms VISIBLE in the given work context.

        D12: JOINs artifact_visibility → artifact_versions and returns
        content from the pinned version snapshot (not from Project.glossary JSON).
        Falls back to glossary JSON for pre-versioning compat.
        """
        # Primary path: JOIN visibility → versions for snapshot content
        stmt = (
            select(ArtifactVersion.content_snapshot)
            .join(ArtifactVisibility, ArtifactVisibility.artifact_version_id == ArtifactVersion.id)
            .where(
                ArtifactVisibility.project_id == project_id,
                ArtifactVisibility.artifact_type == "glossary_term",
                ArtifactVisibility.visible_in_context_id == work_context_id,
            )
        )
        snapshots = (await self.db.execute(stmt)).scalars().all()
        if snapshots:
            return list(snapshots)

        # Fallback: no versioned data → read from Project.glossary JSON
        project = await self.db.get(Project, project_id)
        if not project or not project.glossary:
            return []
        return project.glossary or []

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
        Merge glossary terms from source into target.
        D10: does NOT copy JSON data. Returns (promoted, conflicts).
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

        D10 sibling semantics:
          "keep_existing"  — close conflict, no visibility change
          "use_incoming"   — INSERT visibility row in target; supersede existing
          "merge"          — CREATE sibling term in JSON blob; INSERT visibility
                            with sibling_of; original stays untouched
        """
        conflict = await self.db.get(PromotionConflict, conflict_id)
        if not conflict or conflict.project_id != project_id:
            raise ValueError(f"Conflict {conflict_id!r} not found for project {project_id!r}")

        now = datetime.now(timezone.utc)
        term_id = conflict.artifact_item_id
        target_ctx_id = conflict.target_context_id
        audit_extra: dict[str, Any] = {}

        if resolution == "use_incoming":
            # Supersede existing term's visibility at target level
            await _supersede_visibility(
                self.db, project_id, "glossary_term", term_id, target_ctx_id, now
            )
            # D12: pin to current version
            current_ver = await get_current_version(
                self.db, project_id, "glossary_term", term_id
            )
            self.db.add(ArtifactVisibility(
                id=str(uuid.uuid4()),
                project_id=project_id,
                artifact_type="glossary_term",
                artifact_item_id=term_id,
                source_context_id=conflict.source_context_id,
                visible_in_context_id=target_ctx_id,
                lifecycle_status="promoted",
                artifact_version_id=current_ver.id if current_ver else None,
                created_at=now,
            ))

        elif resolution == "merge" and resolved_value:
            # Create a SIBLING term — added to blob, original untouched
            sibling_term_id = f"{term_id}_merged_{str(uuid.uuid4())[:8]}"
            sibling_term = {**resolved_value, "_sibling_id": sibling_term_id}
            await _add_term_to_blob(self.db, project_id, sibling_term, now)
            # Supersede existing at target level
            await _supersede_visibility(
                self.db, project_id, "glossary_term", term_id, target_ctx_id, now
            )
            # D12: create v1 for the sibling
            sibling_ver = await create_version(
                self.db, project_id, "glossary_term", sibling_term_id,
                sibling_term, target_ctx_id, "merged from conflict resolution",
            )
            self.db.add(ArtifactVisibility(
                id=str(uuid.uuid4()),
                project_id=project_id,
                artifact_type="glossary_term",
                artifact_item_id=sibling_term_id,
                source_context_id=target_ctx_id,
                visible_in_context_id=target_ctx_id,
                lifecycle_status="promoted",
                sibling_of=term_id,
                artifact_version_id=sibling_ver.id,
                created_at=now,
            ))
            audit_extra = {"sibling_item_id": sibling_term_id, "original_item_id": term_id}

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
            new_value={"resolution": resolution, "conflict_id": conflict_id, **audit_extra},
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
    from sqlalchemy import select as sa_select
    stmt = sa_select(ArtifactVisibility).where(
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


async def _add_term_to_blob(
    db: AsyncSession,
    project_id: str,
    new_term: dict[str, Any],
    now: datetime,
) -> None:
    """Add a sibling term to Project.glossary (append, not replace)."""
    project = await db.get(Project, project_id)
    if not project:
        return
    glossary = list(project.glossary or [])
    glossary.append(new_term)
    project.glossary = glossary
    project.context_built_at = now
