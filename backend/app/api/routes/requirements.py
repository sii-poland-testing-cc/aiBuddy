"""
Faza 2: Requirements API Routes
=================================
Endpoints:
  POST /api/requirements/{project_id}/extract  — run Requirements Workflow (SSE)
  GET  /api/requirements/{project_id}          — list all requirements (hierarchical)
  GET  /api/requirements/{project_id}/flat     — list all requirements (flat)
  GET  /api/requirements/{project_id}/stats    — summary statistics
  GET  /api/requirements/{project_id}/gaps     — identified gaps
  PATCH /api/requirements/{project_id}/{req_id} — human review: update a requirement
  DELETE /api/requirements/{project_id}         — wipe all requirements (re-extract)
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.requirements_workflow import RequirementsWorkflow, RequirementsProgressEvent
from app.api.sse import SSE_DONE, sse_event
from app.api.streaming import stream_with_keepalive
from app.core.config import settings
from app.core.llm import get_llm
from app.db.engine import AsyncSessionLocal, get_db
from app.db.models import Project
from app.db.requirements_models import Requirement
from app.services.requirements import persist_gaps, persist_requirements

logger = logging.getLogger("ai_buddy.requirements_api")

router = APIRouter()


# ─── Request / Response Models ────────────────────────────────────────────────

class ExtractRequest(BaseModel):
    message: str = ""  # optional user hint (e.g. "focus on payment module")


class RequirementUpdate(BaseModel):
    """Payload for human review / manual correction."""
    title: Optional[str] = None
    description: Optional[str] = None
    external_id: Optional[str] = None
    level: Optional[str] = None
    source_type: Optional[str] = None
    taxonomy: Optional[Dict[str, Any]] = None
    confidence: Optional[float] = None
    human_reviewed: Optional[bool] = None
    needs_review: Optional[bool] = None
    review_reason: Optional[str] = None


# ─── Extract (SSE) ───────────────────────────────────────────────────────────

@router.post("/{project_id}/extract")
async def extract_requirements(project_id: str, req: ExtractRequest = ExtractRequest()):
    """
    Run Faza 2 pipeline: extract requirements from M1 RAG context.
    Returns SSE stream with progress + final result.

    If requirements already exist for this project, they are replaced (full re-extract).
    """
    return StreamingResponse(
        _run_extraction(project_id, req.message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _run_extraction(project_id: str, user_message: str):
    llm = get_llm()
    workflow = RequirementsWorkflow(
        llm=llm, timeout=settings.REQUIREMENTS_WORKFLOW_TIMEOUT_SECONDS
    )

    last_progress = {"message": "Processing…", "progress": 0.05, "stage": "extract"}
    result = None

    logger.info("Faza2 requirements extraction STARTED — project=%s", project_id)

    try:
        handler = workflow.run(
            project_id=project_id,
            user_message=user_message,
        )

        async for kind, item in stream_with_keepalive(handler):
            if kind == "event":
                if isinstance(item, RequirementsProgressEvent):
                    last_progress = {"message": item.message, "progress": item.progress, "stage": item.stage}
                    yield sse_event({"type": "progress", "data": last_progress})
                    await asyncio.sleep(0)
            elif kind == "keepalive":
                yield sse_event({"type": "progress", "data": last_progress})
                await asyncio.sleep(0)
            elif kind == "result":
                result = item
            elif kind == "error":
                raise item  # type: ignore[misc]

        if result is None:
            raise RuntimeError("Workflow completed without a result")

        # Persist to DB
        try:
            async with AsyncSessionLocal() as db:
                await persist_requirements(
                    db, project_id, result.get("requirements_flat", [])
                )
                # Also persist gaps as project metadata
                await persist_gaps(db, project_id, result.get("gaps", []))
        except Exception as exc:
            logger.warning("Failed to persist requirements: %s", exc)

        meta = result.get("metadata", {})
        logger.info(
            "Faza2 requirements extraction DONE — project=%s features=%s requirements=%s gaps=%s",
            project_id,
            meta.get("total_features", "?"),
            meta.get("total_requirements", "?"),
            len(result.get("gaps", [])),
        )
        yield sse_event({"type": "result", "data": result})

    except Exception as exc:
        logger.error("Faza2 requirements extraction FAILED — project=%s error=%s", project_id, exc)
        logger.exception("Requirements extraction failed")
        yield sse_event({"type": "error", "data": {"message": str(exc)}})
    finally:
        yield SSE_DONE


# ─── List Requirements (Hierarchical) ────────────────────────────────────────

@router.get("/{project_id}")
async def list_requirements(
    project_id: str,
    level: Optional[str] = Query(None, pattern="^(feature|functional_req|acceptance_criterion)$"),
    needs_review: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    List requirements as a hierarchical tree (features → reqs → ACs).
    Optionally filter by level or review status.
    """
    stmt = (
        select(Requirement)
        .where(Requirement.project_id == project_id)
        .order_by(Requirement.created_at)
    )
    if level:
        stmt = stmt.where(Requirement.level == level)
    if needs_review is not None:
        stmt = stmt.where(Requirement.needs_review == needs_review)

    rows = (await db.execute(stmt)).scalars().all()

    if not rows:
        return {"project_id": project_id, "features": [], "total": 0}

    # Build tree
    by_id = {}
    for r in rows:
        by_id[r.id] = _req_to_dict(r)

    # If filtering by level, return flat
    if level:
        return {
            "project_id": project_id,
            "requirements": list(by_id.values()),
            "total": len(by_id),
        }

    # Build hierarchy
    features = []
    for r in rows:
        node = by_id[r.id]
        if r.parent_id and r.parent_id in by_id:
            parent = by_id[r.parent_id]
            parent.setdefault("children", []).append(node)
        elif r.level == "feature":
            features.append(node)

    return {
        "project_id": project_id,
        "features": features,
        "total": len(by_id),
    }


# ─── List Requirements (Flat) ────────────────────────────────────────────────

@router.get("/{project_id}/flat")
async def list_requirements_flat(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return all requirements as a flat list (for audits and matching)."""
    stmt = (
        select(Requirement)
        .where(Requirement.project_id == project_id)
        .order_by(Requirement.level, Requirement.created_at)
    )
    rows = (await db.execute(stmt)).scalars().all()

    return {
        "project_id": project_id,
        "requirements": [_req_to_dict(r) for r in rows],
        "total": len(rows),
    }


# ─── Stats ────────────────────────────────────────────────────────────────────

@router.get("/{project_id}/stats")
async def requirements_stats(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Summary statistics for the requirements registry."""
    stmt = select(Requirement).where(Requirement.project_id == project_id)
    rows = (await db.execute(stmt)).scalars().all()

    if not rows:
        return {
            "project_id": project_id,
            "has_requirements": False,
            "total": 0,
            "by_level": {},
            "by_source_type": {},
            "avg_confidence": None,
            "min_confidence": None,
            "needs_review_count": 0,
            "human_reviewed_count": 0,
        }

    by_level = {}
    by_source = {}
    confidences = []
    needs_review_count = 0
    human_reviewed_count = 0

    for r in rows:
        by_level[r.level] = by_level.get(r.level, 0) + 1
        by_source[r.source_type] = by_source.get(r.source_type, 0) + 1
        if r.confidence is not None:
            confidences.append(r.confidence)
        if r.needs_review:
            needs_review_count += 1
        if r.human_reviewed:
            human_reviewed_count += 1

    return {
        "project_id": project_id,
        "has_requirements": True,
        "total": len(rows),
        "by_level": by_level,
        "by_source_type": by_source,
        "avg_confidence": round(sum(confidences) / len(confidences), 2) if confidences else None,
        "min_confidence": round(min(confidences), 2) if confidences else None,
        "needs_review_count": needs_review_count,
        "human_reviewed_count": human_reviewed_count,
    }


# ─── Gaps ─────────────────────────────────────────────────────────────────────

@router.get("/{project_id}/gaps")
async def requirements_gaps(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return identified requirement gaps for this project."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    return {"project_id": project_id, "gaps": project.requirement_gaps or []}


# ─── Human Review: Update Requirement ────────────────────────────────────────

@router.patch("/{project_id}/{requirement_id}")
async def update_requirement(
    project_id: str,
    requirement_id: str,
    body: RequirementUpdate,
    db: AsyncSession = Depends(get_db),
):
    """
    Update a requirement after human review.
    Typically used to:
      - Confirm or adjust confidence
      - Edit title/description
      - Mark as human_reviewed
      - Clear needs_review flag
    """
    req = await db.get(Requirement, requirement_id)
    if not req or req.project_id != project_id:
        raise HTTPException(404, "Requirement not found")

    update_data = body.model_dump(exclude_none=True)

    for key, value in update_data.items():
        setattr(req, key, value)

    req.updated_at = datetime.now(timezone.utc)

    # If explicitly confirming, mark as human reviewed
    if body.human_reviewed is True:
        req.human_reviewed = True
        req.needs_review = False
        req.review_reason = None

    await db.commit()
    await db.refresh(req)

    return _req_to_dict(req)


# ─── Delete All Requirements ─────────────────────────────────────────────────

@router.delete("/{project_id}")
async def delete_requirements(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Wipe all requirements for a project (before re-extraction)."""
    result = await db.execute(
        delete(Requirement).where(Requirement.project_id == project_id)
    )
    await db.commit()
    return {"deleted": result.rowcount}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _req_to_dict(r: Requirement) -> Dict[str, Any]:
    return {
        "id": r.id,
        "project_id": r.project_id,
        "parent_id": r.parent_id,
        "level": r.level,
        "external_id": r.external_id,
        "title": r.title,
        "description": r.description,
        "source_type": r.source_type,
        "taxonomy": r.taxonomy,
        "completeness_score": r.completeness_score,
        "confidence": r.confidence,
        "human_reviewed": r.human_reviewed,
        "needs_review": r.needs_review,
        "review_reason": r.review_reason,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


