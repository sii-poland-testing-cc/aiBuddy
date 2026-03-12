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
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.requirements_workflow import RequirementsWorkflow, RequirementsProgressEvent
from app.core.llm import get_llm
from app.db.engine import AsyncSessionLocal, get_db
from app.db.requirements_models import CoverageScore, Requirement, RequirementTCMapping

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
    workflow = RequirementsWorkflow(llm=llm, timeout=300)

    try:
        handler = workflow.run(
            project_id=project_id,
            user_message=user_message,
        )

        async for ev in handler.stream_events():
            if isinstance(ev, RequirementsProgressEvent):
                yield _sse({
                    "type": "progress",
                    "data": {
                        "message": ev.message,
                        "progress": ev.progress,
                        "stage": ev.stage,
                    },
                })
                await asyncio.sleep(0)

        result = await handler

        # Persist to DB
        try:
            async with AsyncSessionLocal() as db:
                await _persist_requirements(
                    db, project_id, result.get("requirements_flat", [])
                )
                # Also persist gaps as project metadata
                await _persist_gaps(db, project_id, result.get("gaps", []))
        except Exception as exc:
            logger.warning("Failed to persist requirements: %s", exc)

        yield _sse({"type": "result", "data": result})

    except Exception as exc:
        logger.exception("Requirements extraction failed")
        yield _sse({"type": "error", "data": {"message": str(exc)}})
    finally:
        yield "data: [DONE]\n\n"


async def _persist_requirements(db: AsyncSession, project_id: str, flat_reqs: List[Dict]):
    """
    Persist extracted requirements to DB.
    Wipes existing requirements for this project first (full re-extract).
    """
    # Delete existing requirements for this project
    await db.execute(
        delete(Requirement).where(Requirement.project_id == project_id)
    )
    await db.flush()

    # Insert new requirements
    for req_data in flat_reqs:
        req = Requirement(
            id=req_data["id"],
            project_id=project_id,
            parent_id=req_data.get("parent_id"),
            level=req_data.get("level", "functional_req"),
            external_id=req_data.get("external_id"),
            title=req_data["title"],
            description=req_data.get("description", ""),
            source_type=req_data.get("source_type", "implicit"),
            source_references=None,
            taxonomy=req_data.get("taxonomy"),
            completeness_score=req_data.get("completeness_score"),
            confidence=req_data.get("confidence"),
            human_reviewed=False,
            needs_review=req_data.get("needs_review", False),
            review_reason=req_data.get("review_reason"),
        )
        db.add(req)

    await db.commit()
    logger.info("project=%s — persisted %d requirements", project_id, len(flat_reqs))


async def _persist_gaps(db: AsyncSession, project_id: str, gaps: List[Dict]):
    """Persist gaps as a JSON field on the Project (reuse context_stats or add new col)."""
    from app.db.models import Project
    project = await db.get(Project, project_id)
    if project:
        # Store gaps alongside existing context_stats
        existing_stats = json.loads(project.context_stats or "{}") if project.context_stats else {}
        existing_stats["requirement_gaps"] = gaps
        project.context_stats = json.dumps(existing_stats, ensure_ascii=False)
        await db.commit()


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
        return {"project_id": project_id, "has_requirements": False}

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
    from app.db.models import Project
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    stats = json.loads(project.context_stats or "{}") if project.context_stats else {}
    gaps = stats.get("requirement_gaps", [])

    return {"project_id": project_id, "gaps": gaps}


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

    # Handle taxonomy as JSON
    if "taxonomy" in update_data:
        update_data["taxonomy"] = json.dumps(update_data["taxonomy"])

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
        "taxonomy": json.loads(r.taxonomy) if r.taxonomy else None,
        "completeness_score": r.completeness_score,
        "confidence": r.confidence,
        "human_reviewed": r.human_reviewed,
        "needs_review": r.needs_review,
        "review_reason": r.review_reason,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
