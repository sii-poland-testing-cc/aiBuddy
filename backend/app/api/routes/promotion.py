"""
Promotion API — Phase 5.

Endpoints:
  POST /api/promotion/{project_id}/{ctx_id}/promote  — execute promotion
  GET  /api/promotion/{project_id}/{ctx_id}/preview  — dry-run preview
  GET  /api/promotion/{project_id}/status/{ctx_id}   — promotion state summary
"""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import WorkContext
from app.lifecycle.conflict_service import count_pending_conflicts, get_pending_conflicts
from app.lifecycle.promotion_service import PromotionService

router = APIRouter()


# ─── POST /{project_id}/{ctx_id}/promote ──────────────────────────────────────

@router.post("/{project_id}/{ctx_id}/promote")
async def promote_context(
    project_id: str,
    ctx_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Execute promotion for a Story (→ Epic) or Epic (→ Domain).

    - Story must be status='ready' and have no pending conflicts.
    - Epic must be status='ready' and have no pending conflicts
      (checked recursively for child stories too).

    Returns a summary of what was promoted and any queued conflicts.
    """
    service = PromotionService(db)

    # Determine level to dispatch to the right method
    ctx = await db.get(WorkContext, ctx_id)
    if ctx is None or ctx.project_id != project_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Work context not found.")

    if ctx.level == "story":
        result = await service.promote_story_to_epic(project_id, ctx_id)
    elif ctx.level == "epic":
        result = await service.promote_epic_to_domain(project_id, ctx_id)
    else:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=422,
            detail=f"Cannot promote a '{ctx.level}' context. Only 'story' and 'epic' can be promoted.",
        )

    return {
        "promoted_count": result.promoted_count,
        "conflict_count": result.conflict_count,
        "artifact_type_summary": result.artifact_type_summary,
        "conflicts": [
            {
                "artifact_type": c.artifact_type,
                "artifact_item_id": c.artifact_item_id,
                "conflict_reason": c.conflict_reason,
            }
            for c in result.conflicts
        ],
    }


# ─── GET /{project_id}/{ctx_id}/preview ───────────────────────────────────────

@router.get("/{project_id}/{ctx_id}/preview")
async def preview_promotion(
    project_id: str,
    ctx_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Dry-run: shows what would be promoted vs conflicted without committing.
    No state is changed.
    """
    service = PromotionService(db)
    result = await service.preview_promotion(project_id, ctx_id)

    return {
        "promoted_count": result.promoted_count,
        "conflict_count": result.conflict_count,
        "artifact_type_summary": result.artifact_type_summary,
        "conflicts": [
            {
                "artifact_type": c.artifact_type,
                "artifact_item_id": c.artifact_item_id,
                "conflict_reason": c.conflict_reason,
            }
            for c in result.conflicts
        ],
    }


# ─── GET /{project_id}/status/{ctx_id} ────────────────────────────────────────

@router.get("/{project_id}/status/{ctx_id}")
async def promotion_status(
    project_id: str,
    ctx_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Return the current promotion state for a WorkContext:
    - context metadata (level, status, promoted_at)
    - pending_conflicts count
    - list of pending PromotionConflict rows
    - child summary (for epics: child story statuses)
    """
    ctx = await db.get(WorkContext, ctx_id)
    if ctx is None or ctx.project_id != project_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Work context not found.")

    pending = await count_pending_conflicts(db, project_id, ctx_id)
    conflict_rows = await get_pending_conflicts(db, project_id, context_id=ctx_id)

    # Build child summary for epics
    children_summary: list[dict] = []
    if ctx.level in ("epic", "domain"):
        child_level = "story" if ctx.level == "epic" else "epic"
        stmt = select(WorkContext).where(
            WorkContext.project_id == project_id,
            WorkContext.parent_id == ctx_id,
            WorkContext.level == child_level,
        )
        children = (await db.execute(stmt)).scalars().all()
        children_summary = [
            {"id": c.id, "name": c.name, "status": c.status, "level": c.level}
            for c in children
        ]

    return {
        "id": ctx.id,
        "level": ctx.level,
        "name": ctx.name,
        "status": ctx.status,
        "promoted_at": ctx.promoted_at.isoformat() if ctx.promoted_at else None,
        "pending_conflicts": pending,
        "conflicts": [
            {
                "id": c.id,
                "artifact_type": c.artifact_type,
                "artifact_item_id": c.artifact_item_id,
                "conflict_reason": c.conflict_reason,
                "created_at": c.created_at.isoformat(),
            }
            for c in conflict_rows
        ],
        "children": children_summary,
    }
