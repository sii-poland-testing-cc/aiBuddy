"""
Promotion Service — Phase 5 + Phase 8.4 (version pinning & locking).

Executes Story → Epic → Domain artifact merges for all artifact types.
Each artifact type is promoted in its own DB transaction (per-type isolation).

Partial promotion semantics:
  - Clean items are promoted immediately (lifecycle_status → "promoted")
  - Conflicting items are queued to promotion_conflicts table
    and their lifecycle_status is set to "conflict_pending"
  - promote_epic_to_domain is blocked if any pending conflicts remain for
    ANY promoted child story of the epic

Phase 8.4 additions (D12 version pinning):
  - Promoted visibility rows are pinned to the current version at promotion time
  - Re-promotion detects version drift: skip (same), update (no conflict), queue (conflict)
  - Pessimistic locking: PostgreSQL uses SELECT … FOR UPDATE on WorkContext;
    SQLite uses a promotion_locks table as fallback
  - Preview includes version deltas

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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import AsyncSessionLocal
from app.db.models import (
    ArtifactAuditLog,
    ArtifactVersion,
    ArtifactVisibility,
    PromotionConflict,
    PromotionLock,
    WorkContext,
)
from app.lifecycle.conflict_service import count_pending_conflicts, queue_conflicts
from app.lifecycle.glossary_adapter import GlossaryAdapter
from app.lifecycle.graph_adapter import GraphEdgeAdapter, GraphNodeAdapter
from app.lifecycle.interface import ArtifactLifecycleAdapter, ArtifactType, ConflictItem
from app.lifecycle.requirements_adapter import RequirementsAdapter
from app.services.versioning import get_current_version

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
        Phase 8.4: includes version_deltas in summary — items where the source
        version has drifted since the last promotion.
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
                    summary[artifact_type.value] = {
                        "items_found": 0, "promoted": 0, "conflicts": 0, "version_deltas": 0,
                    }
                    continue
                promoted_items, conflict_items = await adapter.merge_into_target(
                    project_id, ctx_id, parent.id, items
                )

                # Phase 8.4: count version deltas for already-promoted items
                version_deltas = await _count_version_deltas(
                    db, project_id, artifact_type.value, ctx_id, parent.id
                )

                total_promoted += len(promoted_items)
                total_conflicts += len(conflict_items)
                all_conflicts.extend(conflict_items)
                summary[artifact_type.value] = {
                    "items_found": len(items),
                    "promoted": len(promoted_items),
                    "conflicts": len(conflict_items),
                    "version_deltas": version_deltas,
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
        # Acquire pessimistic lock on target context
        await _acquire_promotion_lock(self.db, project_id, target_ctx.id)

        try:
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
        finally:
            await _release_promotion_lock(self.db, project_id, target_ctx.id)

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
                        db, artifact_type, project_id, source_ctx_id, target_ctx_id, promoted_items, now
                    )

                # Queue conflicts and mark conflict_pending
                if conflict_items:
                    await queue_conflicts(
                        db, project_id, artifact_type, conflict_items,
                        source_ctx_id, target_ctx_id
                    )
                    await _mark_conflict_pending_items(
                        db, artifact_type, project_id, source_ctx_id, conflict_items, now
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
            if not conflict.target_context_id:
                continue

            artifact_type_str = conflict.artifact_type
            artifact_item_id = conflict.artifact_item_id
            source_ctx_id = conflict.source_context_id

            # Adapters' apply_resolution() already created visibility rows
            # in the target context (for use_incoming/merge).
            # Here we only clean up: clear conflict_pending on source-context
            # visibility row so the item is no longer "stuck".
            if source_ctx_id:
                vis_stmt = select(ArtifactVisibility).where(
                    ArtifactVisibility.project_id == project_id,
                    ArtifactVisibility.artifact_type == artifact_type_str,
                    ArtifactVisibility.artifact_item_id == artifact_item_id,
                    ArtifactVisibility.visible_in_context_id == source_ctx_id,
                )
                src_row = (await self.db.execute(vis_stmt)).scalars().first()
                if src_row and src_row.lifecycle_status == "conflict_pending":
                    src_row.lifecycle_status = "active"
                    src_row.updated_at = now

            promoted_count += 1

            self.db.add(ArtifactAuditLog(
                id=str(uuid.uuid4()),
                project_id=project_id,
                artifact_type=artifact_type_str,
                artifact_item_id=artifact_item_id,
                event_type="promoted",
                work_context_id=conflict.target_context_id,
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

    async def re_promote(
        self, project_id: str, source_ctx_id: str, target_ctx_id: str
    ) -> "PromotionResult":
        """
        Re-promotion: for items already promoted to target, check if the source
        version has been updated since the original promotion.

        For each promoted visibility row in the target:
          - Same version → skip (no-op)
          - New version, no conflict → update pinned version
          - New version, conflict → queue for resolution
        """
        await _acquire_promotion_lock(self.db, project_id, target_ctx_id)
        try:
            return await _re_promote_items(
                self.db, project_id, source_ctx_id, target_ctx_id
            )
        finally:
            await _release_promotion_lock(self.db, project_id, target_ctx_id)

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
    """Derive the artifact_item_id from an item dict."""
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
    source_ctx_id: str,
    target_ctx_id: str,
    promoted_items: list[dict[str, Any]],
    now: datetime,
) -> None:
    """
    Create visibility rows for promoted items in the target context.

    D10 semantics: promotion = INSERT a new ArtifactVisibility row
    (same artifact_item_id, source_context_id = original source,
     visible_in_context_id = target context, lifecycle_status = 'promoted').
    NO data copying. NO moving. ONE INSERT per item.

    D12 version pinning (Phase 8.4): each promoted visibility row is pinned
    to the current version of the item at promotion time.
    """
    type_str = artifact_type.value

    for item in promoted_items:
        if artifact_type == ArtifactType.REQUIREMENT:
            item_id = str(item.get("id", "")).strip()
        else:
            item_id = _get_manifest_item_id(artifact_type, item)
        if not item_id:
            continue

        # Preserve canonical source: look up original source_context_id
        # from the existing visibility row in the source context.
        # This is critical for chained promotion (Story→Epic→Domain):
        # the domain visibility row should point to the Story, not the Epic.
        orig_source_stmt = select(ArtifactVisibility.source_context_id).where(
            ArtifactVisibility.project_id == project_id,
            ArtifactVisibility.artifact_type == type_str,
            ArtifactVisibility.artifact_item_id == item_id,
            ArtifactVisibility.visible_in_context_id == source_ctx_id,
        )
        canonical_source = (await db.execute(orig_source_stmt)).scalar()

        # D12: pin to current version at promotion time
        current_ver = await get_current_version(db, project_id, type_str, item_id)
        version_id = current_ver.id if current_ver else None

        db.add(ArtifactVisibility(
            id=str(uuid.uuid4()),
            project_id=project_id,
            artifact_type=type_str,
            artifact_item_id=item_id,
            source_context_id=canonical_source or source_ctx_id,
            visible_in_context_id=target_ctx_id,
            lifecycle_status="promoted",
            artifact_version_id=version_id,
            created_at=now,
        ))
        db.add(ArtifactAuditLog(
            id=str(uuid.uuid4()),
            project_id=project_id,
            artifact_type=type_str,
            artifact_item_id=item_id,
            event_type="promoted",
            work_context_id=target_ctx_id,
            new_value={
                "lifecycle_status": "promoted",
                "target_context_id": target_ctx_id,
                "pinned_version_id": version_id,
                "pinned_version_number": current_ver.version_number if current_ver else None,
            },
            actor="system",
            created_at=now,
        ))


async def _mark_conflict_pending_items(
    db: AsyncSession,
    artifact_type: ArtifactType,
    project_id: str,
    source_ctx_id: str,
    conflict_items: list[ConflictItem],
    now: datetime,
) -> None:
    """
    Set lifecycle_status = 'conflict_pending' on the source-context visibility
    rows for items that failed promotion due to conflicts.
    """
    type_str = artifact_type.value

    for c in conflict_items:
        stmt = select(ArtifactVisibility).where(
            ArtifactVisibility.project_id == project_id,
            ArtifactVisibility.artifact_type == type_str,
            ArtifactVisibility.artifact_item_id == c.artifact_item_id,
            ArtifactVisibility.visible_in_context_id == source_ctx_id,
        )
        row = (await db.execute(stmt)).scalars().first()
        if row:
            row.lifecycle_status = "conflict_pending"
            row.updated_at = now


# ── Pessimistic Locking (Phase 8.4) ──────────────────────────────────────────


def _is_sqlite(db: AsyncSession) -> bool:
    """Check if the underlying engine is SQLite (no FOR UPDATE support)."""
    url = str(db.bind.url) if db.bind else ""
    return "sqlite" in url


async def _acquire_promotion_lock(
    db: AsyncSession, project_id: str, target_ctx_id: str
) -> None:
    """
    Acquire a pessimistic lock on the target context for promotion.

    PostgreSQL: SELECT … FOR UPDATE on the WorkContext row.
    SQLite: INSERT into promotion_locks table (unique constraint blocks concurrent).
    """
    if _is_sqlite(db):
        lock = PromotionLock(
            id=str(uuid.uuid4()),
            project_id=project_id,
            target_context_id=target_ctx_id,
        )
        try:
            db.add(lock)
            await db.flush()
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=409,
                detail=f"Another promotion is already in progress for target context '{target_ctx_id}'.",
            )
    else:
        # PostgreSQL: SELECT … FOR UPDATE on WorkContext row
        stmt = (
            select(WorkContext)
            .where(WorkContext.id == target_ctx_id)
            .with_for_update()
        )
        result = await db.execute(stmt)
        if result.scalars().first() is None:
            raise HTTPException(404, f"Target context '{target_ctx_id}' not found.")


async def _release_promotion_lock(
    db: AsyncSession, project_id: str, target_ctx_id: str
) -> None:
    """Release the promotion lock (SQLite only; PostgreSQL releases on commit/rollback)."""
    if _is_sqlite(db):
        stmt = select(PromotionLock).where(
            PromotionLock.project_id == project_id,
            PromotionLock.target_context_id == target_ctx_id,
        )
        lock_row = (await db.execute(stmt)).scalars().first()
        if lock_row:
            await db.delete(lock_row)
            await db.flush()


async def _count_version_deltas(
    db: AsyncSession,
    project_id: str,
    artifact_type: str,
    source_ctx_id: str,
    target_ctx_id: str,
) -> int:
    """
    Count items already promoted from source to target where the pinned version
    differs from the current version in source. Used by preview_promotion.
    """
    stmt = select(ArtifactVisibility).where(
        ArtifactVisibility.project_id == project_id,
        ArtifactVisibility.artifact_type == artifact_type,
        ArtifactVisibility.source_context_id == source_ctx_id,
        ArtifactVisibility.visible_in_context_id == target_ctx_id,
        ArtifactVisibility.lifecycle_status == "promoted",
    )
    rows = (await db.execute(stmt)).scalars().all()

    deltas = 0
    for row in rows:
        current_ver = await get_current_version(
            db, project_id, row.artifact_type, row.artifact_item_id
        )
        if current_ver and row.artifact_version_id != current_ver.id:
            deltas += 1
    return deltas


# ── Re-Promotion (Phase 8.4) ─────────────────────────────────────────────────


async def _re_promote_items(
    db: AsyncSession,
    project_id: str,
    source_ctx_id: str,
    target_ctx_id: str,
) -> PromotionResult:
    """
    Re-promotion logic: for items already promoted from source to target,
    check if the source version has drifted since the original promotion.

    For each promoted item:
      - pinned version == current version → skip
      - pinned version != current version, no conflict → update pinned version
      - pinned version != current version, conflict → queue for resolution
    """
    # Find all promoted visibility rows in target that originated from source
    stmt = select(ArtifactVisibility).where(
        ArtifactVisibility.project_id == project_id,
        ArtifactVisibility.source_context_id == source_ctx_id,
        ArtifactVisibility.visible_in_context_id == target_ctx_id,
        ArtifactVisibility.lifecycle_status == "promoted",
    )
    target_rows = (await db.execute(stmt)).scalars().all()

    if not target_rows:
        return PromotionResult(promoted_count=0, conflict_count=0)

    now = datetime.now(timezone.utc)
    updated_count = 0
    conflict_count = 0

    # Build adapter lookup for conflict detection
    adapter_map: dict[str, ArtifactLifecycleAdapter] = {}
    for _, adapter_class in _ARTIFACT_TYPES:
        a = adapter_class(db)
        adapter_map[a.artifact_type.value] = a

    for row in target_rows:
        current_ver = await get_current_version(
            db, project_id, row.artifact_type, row.artifact_item_id
        )
        if current_ver is None:
            continue

        # Same version → skip
        if row.artifact_version_id == current_ver.id:
            continue

        # Version drifted — check for conflict with existing target content
        adapter = adapter_map.get(row.artifact_type)
        if adapter is None:
            continue

        # Get existing items in target (excluding this item's own promoted row)
        existing_items = await adapter.get_items_in_context(project_id, target_ctx_id)

        new_snapshot = current_ver.content_snapshot or {}
        has_conflict = False
        conflict_reason = ""

        for ex in existing_items:
            # Skip self-comparison (same item_id)
            ex_id = _get_manifest_item_id(
                adapter.artifact_type, ex
            ) if adapter.artifact_type != ArtifactType.REQUIREMENT else str(ex.get("id", ""))
            if ex_id == row.artifact_item_id:
                continue
            c, reason = adapter.detect_conflict(new_snapshot, ex)
            if c:
                has_conflict = True
                conflict_reason = reason
                break

        if has_conflict:
            # Queue conflict for the re-promoted item
            # Get old snapshot for conflict record
            old_ver = await db.get(ArtifactVersion, row.artifact_version_id) if row.artifact_version_id else None
            old_snapshot = old_ver.content_snapshot if old_ver else {}

            conflict_id = str(uuid.uuid4())
            db.add(PromotionConflict(
                id=conflict_id,
                project_id=project_id,
                artifact_type=row.artifact_type,
                artifact_item_id=row.artifact_item_id,
                source_context_id=source_ctx_id,
                target_context_id=target_ctx_id,
                incoming_value=new_snapshot,
                existing_value=old_snapshot,
                conflict_reason=f"re_promotion_version_drift: {conflict_reason}",
                status="pending",
                created_at=now,
            ))
            conflict_count += 1
        else:
            # No conflict → update pinned version
            row.artifact_version_id = current_ver.id
            row.updated_at = now
            updated_count += 1

            db.add(ArtifactAuditLog(
                id=str(uuid.uuid4()),
                project_id=project_id,
                artifact_type=row.artifact_type,
                artifact_item_id=row.artifact_item_id,
                event_type="re_promoted",
                work_context_id=target_ctx_id,
                new_value={
                    "pinned_version_id": current_ver.id,
                    "pinned_version_number": current_ver.version_number,
                },
                actor="system",
                created_at=now,
            ))

    await db.commit()

    return PromotionResult(
        promoted_count=updated_count,
        conflict_count=conflict_count,
    )
