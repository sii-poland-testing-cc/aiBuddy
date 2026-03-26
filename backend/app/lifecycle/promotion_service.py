"""
Promotion Service — Phase 5.

Executes Story → Epic → Domain artifact merges for all artifact types.
Each artifact type is promoted in its own DB transaction (per-type isolation).

Partial promotion semantics:
  - Clean items are promoted immediately (lifecycle_status → "promoted")
  - Conflicting items are queued to promotion_conflicts table
    and their lifecycle_status is set to "conflict_pending"
  - promote_epic_to_domain is blocked if any pending conflicts remain for
    ANY promoted child story of the epic

Usage:
    service = PromotionService(db)
    result = await service.promote_story_to_epic(project_id, story_id)
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Type

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import AsyncSessionLocal
from app.db.models import ArtifactAuditLog, ArtifactLifecycle, PromotionConflict, WorkContext
from app.db.requirements_models import Requirement
from app.lifecycle.conflict_service import count_pending_conflicts, queue_conflicts
from app.lifecycle.glossary_adapter import GlossaryAdapter
from app.lifecycle.graph_adapter import GraphEdgeAdapter, GraphNodeAdapter
from app.lifecycle.interface import ArtifactLifecycleAdapter, ArtifactType, ConflictItem
from app.lifecycle.requirements_adapter import RequirementsAdapter

logger = logging.getLogger("ai_buddy.promotion_service")

# Ordered list of (ArtifactType, AdapterClass) — each type promoted independently
_ARTIFACT_TYPES: list[tuple[ArtifactType, Type[ArtifactLifecycleAdapter]]] = [
    (ArtifactType.GRAPH_NODE, GraphNodeAdapter),
    (ArtifactType.GRAPH_EDGE, GraphEdgeAdapter),
    (ArtifactType.GLOSSARY_TERM, GlossaryAdapter),
    (ArtifactType.REQUIREMENT, RequirementsAdapter),
]


@dataclass
class ArtifactTypeSummary:
    items_found: int = 0
    promoted: int = 0
    conflicts: int = 0


@dataclass
class PromotionResult:
    promoted_count: int
    conflict_count: int
    conflicts: list[ConflictItem] = field(default_factory=list)
    artifact_type_summary: dict[str, dict] = field(default_factory=dict)


class PromotionService:
    """
    Drives the Story→Epic and Epic→Domain promotion flows.

    Each call to _promote_artifact_type opens its own AsyncSession so that
    failures in one artifact type do not roll back another (per-type isolation).
    The outer `db` session is used only for structural work:
    loading WorkContexts and updating their status/promoted_at.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Public methods ────────────────────────────────────────────────────────

    async def promote_story_to_epic(
        self, project_id: str, story_id: str
    ) -> PromotionResult:
        """
        Merge all artifact items from Story into its parent Epic.
        Clean items promoted immediately; conflicts queued for human review.
        """
        story = await self._require_context(project_id, story_id, expected_level="story")
        epic = await self._require_parent(project_id, story, expected_level="epic")

        if story.status != "ready":
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Story must be in 'ready' status to promote, "
                    f"current status is '{story.status}'."
                ),
            )

        pending = await count_pending_conflicts(self.db, project_id, story_id)
        if pending > 0:
            raise HTTPException(
                status_code=409,
                detail=f"Cannot promote: {pending} pending conflict(s) must be resolved first.",
            )

        result = await self._run_promotion(project_id, story, epic)

        # Mark story as promoted
        now = datetime.now(timezone.utc)
        story.status = "promoted"
        story.promoted_at = now
        story.updated_at = now
        await self.db.commit()
        await self.db.refresh(story)

        return result

    async def promote_epic_to_domain(
        self, project_id: str, epic_id: str
    ) -> PromotionResult:
        """
        Merge all artifact items from Epic into its parent Domain.
        Blocks if any pending conflicts exist for this epic (including from child stories).
        """
        epic = await self._require_context(project_id, epic_id, expected_level="epic")
        domain = await self._require_parent(project_id, epic, expected_level="domain")

        if epic.status != "ready":
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Epic must be in 'ready' status to promote, "
                    f"current status is '{epic.status}'."
                ),
            )

        # Block if any pending conflicts for the epic itself OR any child story
        pending = await self._count_pending_for_epic(project_id, epic_id)
        if pending > 0:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Cannot promote epic: {pending} pending conflict(s) must be resolved first "
                    f"(check epic and all child story conflicts)."
                ),
            )

        result = await self._run_promotion(project_id, epic, domain)

        # Mark epic as promoted
        now = datetime.now(timezone.utc)
        epic.status = "promoted"
        epic.promoted_at = now
        epic.updated_at = now
        await self.db.commit()
        await self.db.refresh(epic)

        return result

    async def preview_promotion(
        self, project_id: str, ctx_id: str
    ) -> PromotionResult:
        """
        Dry-run: shows what would promote vs conflict, without committing.
        """
        ctx = await self._load_context(project_id, ctx_id)
        if ctx is None:
            raise HTTPException(404, "Work context not found.")

        parent = await self._load_parent(project_id, ctx, expected_level=None)

        total_promoted = 0
        total_conflicts = 0
        all_conflicts: list[ConflictItem] = []
        summary: dict[str, dict] = {}

        for artifact_type, adapter_class in _ARTIFACT_TYPES:
            async with AsyncSessionLocal() as db:
                adapter = adapter_class(db)
                items = await adapter.get_items_in_context(project_id, ctx_id)
                if not items:
                    summary[artifact_type.value] = {"items_found": 0, "promoted": 0, "conflicts": 0}
                    continue
                promoted_items, conflict_items = await adapter.merge_into_target(
                    project_id, ctx_id, parent.id, items
                )
                total_promoted += len(promoted_items)
                total_conflicts += len(conflict_items)
                all_conflicts.extend(conflict_items)
                summary[artifact_type.value] = {
                    "items_found": len(items),
                    "promoted": len(promoted_items),
                    "conflicts": len(conflict_items),
                }

        return PromotionResult(
            promoted_count=total_promoted,
            conflict_count=total_conflicts,
            conflicts=all_conflicts,
            artifact_type_summary=summary,
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _run_promotion(
        self, project_id: str, source_ctx: WorkContext, target_ctx: WorkContext
    ) -> PromotionResult:
        """Core promotion loop shared by story→epic and epic→domain."""
        total_promoted = 0
        total_conflicts = 0
        all_conflicts: list[ConflictItem] = []
        summary: dict[str, dict] = {}

        for artifact_type, adapter_class in _ARTIFACT_TYPES:
            promoted, conflict_items, type_summary = await self._promote_artifact_type(
                adapter_class, artifact_type, project_id, source_ctx.id, target_ctx.id
            )
            total_promoted += promoted
            total_conflicts += len(conflict_items)
            all_conflicts.extend(conflict_items)
            summary[artifact_type.value] = type_summary

        return PromotionResult(
            promoted_count=total_promoted,
            conflict_count=total_conflicts,
            conflicts=all_conflicts,
            artifact_type_summary=summary,
        )

    async def _promote_artifact_type(
        self,
        adapter_class: Type[ArtifactLifecycleAdapter],
        artifact_type: ArtifactType,
        project_id: str,
        source_ctx_id: str,
        target_ctx_id: str,
    ) -> tuple[int, list[ConflictItem], dict]:
        """
        Core merge loop for one artifact type, in its own DB transaction.
        1. Get items from source context
        2. Call adapter.merge_into_target()
        3. Persist promoted items in target context
        4. Queue conflicts
        5. Emit audit log events
        Returns (promoted_count, conflict_items, summary_dict).
        """
        async with AsyncSessionLocal() as db:
            try:
                adapter = adapter_class(db)
                items = await adapter.get_items_in_context(project_id, source_ctx_id)

                if not items:
                    logger.debug(
                        "project=%s type=%s — no items in source context %s",
                        project_id, artifact_type.value, source_ctx_id,
                    )
                    return 0, [], {"items_found": 0, "promoted": 0, "conflicts": 0}

                promoted_items, conflict_items = await adapter.merge_into_target(
                    project_id, source_ctx_id, target_ctx_id, items
                )

                now = datetime.now(timezone.utc)

                # Persist clean promoted items
                if promoted_items:
                    await _persist_promoted_items(
                        db, artifact_type, project_id, target_ctx_id, promoted_items, now
                    )

                # Queue conflicts and mark conflict_pending
                if conflict_items:
                    await queue_conflicts(
                        db, project_id, artifact_type, conflict_items,
                        source_ctx_id, target_ctx_id
                    )
                    await _mark_conflict_pending_items(
                        db, artifact_type, project_id, conflict_items, now
                    )

                await db.commit()

                logger.info(
                    "project=%s type=%s — promoted=%d conflicts=%d (source=%s target=%s)",
                    project_id, artifact_type.value,
                    len(promoted_items), len(conflict_items),
                    source_ctx_id, target_ctx_id,
                )
                return len(promoted_items), conflict_items, {
                    "items_found": len(items),
                    "promoted": len(promoted_items),
                    "conflicts": len(conflict_items),
                }

            except Exception as exc:
                await db.rollback()
                logger.error(
                    "project=%s type=%s — promotion failed: %s",
                    project_id, artifact_type.value, exc,
                )
                raise

    async def _require_context(
        self, project_id: str, ctx_id: str, expected_level: str
    ) -> WorkContext:
        ctx = await self.db.get(WorkContext, ctx_id)
        if ctx is None or ctx.project_id != project_id:
            raise HTTPException(404, f"Work context '{ctx_id}' not found.")
        if ctx.level != expected_level:
            raise HTTPException(
                422,
                f"Expected a '{expected_level}' context, got '{ctx.level}'.",
            )
        return ctx

    async def _load_context(
        self, project_id: str, ctx_id: str
    ) -> Optional[WorkContext]:
        ctx = await self.db.get(WorkContext, ctx_id)
        if ctx is None or ctx.project_id != project_id:
            return None
        return ctx

    async def _require_parent(
        self, project_id: str, ctx: WorkContext, expected_level: Optional[str]
    ) -> WorkContext:
        if ctx.parent_id is None:
            raise HTTPException(
                422,
                f"Context '{ctx.id}' (level='{ctx.level}') has no parent — cannot promote.",
            )
        parent = await self.db.get(WorkContext, ctx.parent_id)
        if parent is None or parent.project_id != project_id:
            raise HTTPException(404, "Parent work context not found.")
        if expected_level and parent.level != expected_level:
            raise HTTPException(
                422,
                f"Expected parent level '{expected_level}', got '{parent.level}'.",
            )
        return parent

    async def _load_parent(
        self, project_id: str, ctx: WorkContext, expected_level: Optional[str]
    ) -> WorkContext:
        """Like _require_parent but raises 404 instead of 422 for missing parent."""
        if ctx.parent_id is None:
            raise HTTPException(404, "Context has no parent.")
        parent = await self.db.get(WorkContext, ctx.parent_id)
        if parent is None or parent.project_id != project_id:
            raise HTTPException(404, "Parent context not found.")
        return parent

    async def retry_promotion_after_resolution(
        self, project_id: str, context_id: str
    ) -> "PromotionResult":
        """
        After all pending conflicts for context_id are resolved,
        promote artifacts that were previously left as conflict_pending.

        Only runs if count_pending_conflicts == 0.
        Finds all resolved (non-deferred) conflicts for the context,
        updates each artifact to lifecycle_status="promoted" in its target context.
        """
        pending = await count_pending_conflicts(self.db, project_id, context_id)
        if pending > 0:
            return PromotionResult(
                promoted_count=0,
                conflict_count=pending,
                conflicts=[],
            )

        # Find all resolved (non-deferred) conflicts for this source context
        stmt = select(PromotionConflict).where(
            PromotionConflict.project_id == project_id,
            PromotionConflict.source_context_id == context_id,
            PromotionConflict.status.in_([
                "resolved_accept_new", "resolved_keep_old", "resolved_edited"
            ]),
        )
        resolved_conflicts = (await self.db.execute(stmt)).scalars().all()

        if not resolved_conflicts:
            return PromotionResult(promoted_count=0, conflict_count=0, conflicts=[])

        now = datetime.now(timezone.utc)
        promoted_count = 0

        for conflict in resolved_conflicts:
            target_ctx_id = conflict.target_context_id
            if not target_ctx_id:
                continue

            artifact_type_str = conflict.artifact_type
            artifact_item_id = conflict.artifact_item_id

            if artifact_type_str == ArtifactType.REQUIREMENT.value:
                req = await self.db.get(Requirement, artifact_item_id)
                if req and req.project_id == project_id and req.lifecycle_status == "conflict_pending":
                    req.work_context_id = target_ctx_id
                    req.lifecycle_status = "promoted"
                    req.updated_at = now
                    promoted_count += 1
            else:
                lc_stmt = select(ArtifactLifecycle).where(
                    ArtifactLifecycle.project_id == project_id,
                    ArtifactLifecycle.artifact_type == artifact_type_str,
                    ArtifactLifecycle.artifact_item_id == artifact_item_id,
                )
                row = (await self.db.execute(lc_stmt)).scalars().first()
                if row and row.lifecycle_status == "conflict_pending":
                    row.work_context_id = target_ctx_id
                    row.lifecycle_status = "promoted"
                    row.updated_at = now
                    promoted_count += 1

            self.db.add(ArtifactAuditLog(
                id=str(uuid.uuid4()),
                project_id=project_id,
                artifact_type=artifact_type_str,
                artifact_item_id=artifact_item_id,
                event_type="promoted",
                work_context_id=target_ctx_id,
                new_value={"lifecycle_status": "promoted", "via_conflict_resolution": True},
                actor="system",
                created_at=now,
            ))

        await self.db.commit()

        return PromotionResult(
            promoted_count=promoted_count,
            conflict_count=0,
            conflicts=[],
        )

    async def _count_pending_for_epic(self, project_id: str, epic_id: str) -> int:
        """
        Count pending conflicts for the epic AND all its child stories.
        A pending conflict on any story blocks epic promotion.
        """
        # Conflicts directly on the epic
        total = await count_pending_conflicts(self.db, project_id, epic_id)

        # Conflicts on child stories
        stmt = select(WorkContext).where(
            WorkContext.project_id == project_id,
            WorkContext.parent_id == epic_id,
            WorkContext.level == "story",
        )
        stories = (await self.db.execute(stmt)).scalars().all()
        for story in stories:
            total += await count_pending_conflicts(self.db, project_id, story.id)

        return total


# ── Standalone helpers (used by _promote_artifact_type) ───────────────────────

def _get_manifest_item_id(artifact_type: ArtifactType, item: dict[str, Any]) -> str:
    """Derive the ArtifactLifecycle.artifact_item_id from an item dict."""
    if artifact_type == ArtifactType.GRAPH_NODE:
        return str(item.get("id", "")).strip()
    if artifact_type == ArtifactType.GRAPH_EDGE:
        return f"{item.get('source')}→{item.get('target')}"
    if artifact_type == ArtifactType.GLOSSARY_TERM:
        return str(item.get("term", "")).lower().strip()
    # requirements use their id directly (see _persist_promoted_items)
    return str(item.get("id", "")).strip()


async def _persist_promoted_items(
    db: AsyncSession,
    artifact_type: ArtifactType,
    project_id: str,
    target_ctx_id: str,
    promoted_items: list[dict[str, Any]],
    now: datetime,
) -> None:
    """
    Move promoted items into the target context and mark as 'promoted'.

    For requirements (row-stored): UPDATE Requirement ORM rows.
    For graph/glossary (manifest): UPDATE ArtifactLifecycle manifest rows.
    """
    type_str = artifact_type.value

    if artifact_type == ArtifactType.REQUIREMENT:
        for item in promoted_items:
            req = await db.get(Requirement, item["id"])
            if req and req.project_id == project_id:
                req.work_context_id = target_ctx_id
                req.lifecycle_status = "promoted"
                req.updated_at = now
                db.add(ArtifactAuditLog(
                    id=str(uuid.uuid4()),
                    project_id=project_id,
                    artifact_type=type_str,
                    artifact_item_id=item["id"],
                    event_type="promoted",
                    work_context_id=target_ctx_id,
                    new_value={"lifecycle_status": "promoted", "target_context_id": target_ctx_id},
                    actor="system",
                    created_at=now,
                ))
    else:
        for item in promoted_items:
            item_id = _get_manifest_item_id(artifact_type, item)
            if not item_id:
                continue
            stmt = select(ArtifactLifecycle).where(
                ArtifactLifecycle.project_id == project_id,
                ArtifactLifecycle.artifact_type == type_str,
                ArtifactLifecycle.artifact_item_id == item_id,
            )
            row = (await db.execute(stmt)).scalars().first()
            if row:
                row.work_context_id = target_ctx_id
                row.lifecycle_status = "promoted"
                row.updated_at = now
            db.add(ArtifactAuditLog(
                id=str(uuid.uuid4()),
                project_id=project_id,
                artifact_type=type_str,
                artifact_item_id=item_id,
                event_type="promoted",
                work_context_id=target_ctx_id,
                new_value={"lifecycle_status": "promoted", "target_context_id": target_ctx_id},
                actor="system",
                created_at=now,
            ))


async def _mark_conflict_pending_items(
    db: AsyncSession,
    artifact_type: ArtifactType,
    project_id: str,
    conflict_items: list[ConflictItem],
    now: datetime,
) -> None:
    """
    Set lifecycle_status = 'conflict_pending' on items that failed promotion
    due to conflicts.
    """
    type_str = artifact_type.value

    if artifact_type == ArtifactType.REQUIREMENT:
        for c in conflict_items:
            req = await db.get(Requirement, c.artifact_item_id)
            if req and req.project_id == project_id:
                req.lifecycle_status = "conflict_pending"
                req.updated_at = now
    else:
        for c in conflict_items:
            stmt = select(ArtifactLifecycle).where(
                ArtifactLifecycle.project_id == project_id,
                ArtifactLifecycle.artifact_type == type_str,
                ArtifactLifecycle.artifact_item_id == c.artifact_item_id,
            )
            row = (await db.execute(stmt)).scalars().first()
            if row:
                row.lifecycle_status = "conflict_pending"
                row.updated_at = now
