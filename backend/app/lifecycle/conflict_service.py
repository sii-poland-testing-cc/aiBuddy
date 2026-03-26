"""
Conflict service — Phase 5.

Manages the promotion_conflicts table:
  - queue_conflicts: batch insert ConflictItem list into promotion_conflicts
  - get_pending_conflicts: list pending conflicts for a project
  - count_pending_conflicts: used to block promotion when conflicts remain
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ArtifactAuditLog, PromotionConflict
from app.lifecycle.interface import ArtifactType, ConflictItem

logger = logging.getLogger("ai_buddy.conflict_service")


async def queue_conflicts(
    db: AsyncSession,
    project_id: str,
    artifact_type: ArtifactType,
    conflicts: list[ConflictItem],
    source_context_id: str,
    target_context_id: str,
) -> list[str]:
    """
    Batch-insert PromotionConflict rows for each conflict.
    Emits ArtifactAuditLog(event_type="conflict_detected") per conflict.
    Returns the list of newly created conflict IDs.
    """
    now = datetime.now(timezone.utc)
    type_str = artifact_type.value if hasattr(artifact_type, "value") else str(artifact_type)
    conflict_ids: list[str] = []

    for c in conflicts:
        conflict_id = str(uuid.uuid4())
        conflict_ids.append(conflict_id)

        db.add(PromotionConflict(
            id=conflict_id,
            project_id=project_id,
            artifact_type=type_str,
            artifact_item_id=c.artifact_item_id,
            source_context_id=source_context_id,
            target_context_id=target_context_id,
            incoming_value=c.incoming_value,
            existing_value=c.existing_value,
            conflict_reason=c.conflict_reason,
            status="pending",
            created_at=now,
        ))

        db.add(ArtifactAuditLog(
            id=str(uuid.uuid4()),
            project_id=project_id,
            artifact_type=type_str,
            artifact_item_id=c.artifact_item_id,
            event_type="conflict_detected",
            work_context_id=source_context_id,
            new_value={
                "conflict_id": conflict_id,
                "conflict_reason": c.conflict_reason,
                "target_context_id": target_context_id,
            },
            actor="system",
            created_at=now,
        ))

    logger.info(
        "project=%s type=%s — queued %d conflicts (source=%s target=%s)",
        project_id, type_str, len(conflicts), source_context_id, target_context_id,
    )
    return conflict_ids


async def get_pending_conflicts(
    db: AsyncSession,
    project_id: str,
    artifact_type: Optional[str] = None,
    context_id: Optional[str] = None,
) -> list[PromotionConflict]:
    """
    Return pending PromotionConflict rows for a project.

    Optionally filter by:
      artifact_type — "graph_node" | "graph_edge" | "glossary_term" | "requirement"
      context_id    — source_context_id (the context being promoted)
    """
    stmt = select(PromotionConflict).where(
        PromotionConflict.project_id == project_id,
        PromotionConflict.status == "pending",
    )
    if artifact_type is not None:
        stmt = stmt.where(PromotionConflict.artifact_type == artifact_type)
    if context_id is not None:
        stmt = stmt.where(PromotionConflict.source_context_id == context_id)
    stmt = stmt.order_by(PromotionConflict.created_at)
    return list((await db.execute(stmt)).scalars().all())


async def count_pending_conflicts(
    db: AsyncSession,
    project_id: str,
    context_id: str,
) -> int:
    """
    Count pending conflicts where the source context is context_id.
    Used to block promotion when unresolved conflicts remain.
    """
    stmt = select(func.count()).where(
        PromotionConflict.project_id == project_id,
        PromotionConflict.source_context_id == context_id,
        PromotionConflict.status == "pending",
    )
    return (await db.execute(stmt)).scalar() or 0
