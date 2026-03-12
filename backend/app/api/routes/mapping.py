"""
Faza 5+6: Mapping & Coverage API Routes
=========================================
Endpoints:
  POST /api/mapping/{project_id}/run         — run Mapping Workflow (SSE)
  GET  /api/mapping/{project_id}             — list all mappings
  GET  /api/mapping/{project_id}/coverage    — coverage scores per requirement
  GET  /api/mapping/{project_id}/summary     — coverage summary + distribution
  GET  /api/mapping/{project_id}/heatmap     — module-level heatmap data
  PATCH /api/mapping/{project_id}/{mapping_id} — human verify a mapping
  DELETE /api/mapping/{project_id}            — wipe mappings (before re-run)
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.mapping_workflow import MappingWorkflow, MappingProgressEvent
from app.core.llm import get_llm
from app.db.engine import AsyncSessionLocal, get_db
from app.db.requirements_models import CoverageScore, Requirement, RequirementTCMapping

logger = logging.getLogger("ai_buddy.mapping_api")

router = APIRouter()


# ─── Request / Response ──────────────────────────────────────────────────────

class RunMappingRequest(BaseModel):
    file_paths: List[str] = []   # explicit TC file paths; empty = auto-load from DB
    message: str = ""            # optional user hint


class MappingVerification(BaseModel):
    human_verified: bool = True
    mapping_confidence: Optional[float] = None
    coverage_aspects: Optional[List[str]] = None


# ─── Run Mapping (SSE) ───────────────────────────────────────────────────────

@router.post("/{project_id}/run")
async def run_mapping(project_id: str, req: RunMappingRequest = RunMappingRequest()):
    """
    Run Faza 5+6 pipeline: semantic matching + coverage scoring.
    Prerequisites: Faza 2 (requirements extracted) + test files uploaded.
    """
    return StreamingResponse(
        _run_mapping(project_id, req.file_paths, req.message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _run_mapping(project_id: str, file_paths: List[str], user_message: str):
    llm = get_llm()
    workflow = MappingWorkflow(llm=llm, timeout=300)

    try:
        handler = workflow.run(
            project_id=project_id,
            file_paths=file_paths,
            user_message=user_message,
        )

        async for ev in handler.stream_events():
            if isinstance(ev, MappingProgressEvent):
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

        # Persist mappings and scores to DB
        try:
            async with AsyncSessionLocal() as db:
                await _persist_mappings(db, project_id, result.get("mappings", []))
                await _persist_scores(db, project_id, result.get("scores", []))
        except Exception as exc:
            logger.warning("Failed to persist mappings/scores: %s", exc)

        yield _sse({"type": "result", "data": result})

    except Exception as exc:
        logger.exception("Mapping workflow failed")
        yield _sse({"type": "error", "data": {"message": str(exc)}})
    finally:
        yield "data: [DONE]\n\n"


async def _persist_mappings(db: AsyncSession, project_id: str, mappings: List[Dict]):
    """Persist mapping results. Wipes previous mappings for this project."""
    await db.execute(
        delete(RequirementTCMapping).where(RequirementTCMapping.project_id == project_id)
    )
    await db.flush()

    for m in mappings:
        row = RequirementTCMapping(
            project_id=project_id,
            requirement_id=m["requirement_id"],
            tc_source_file=m.get("tc_source_file", "unknown"),
            tc_identifier=m.get("tc_identifier", "unknown"),
            mapping_confidence=m.get("mapping_confidence", 0.5),
            mapping_method=m.get("mapping_method", "embedding"),
            coverage_aspects=json.dumps(m.get("coverage_aspects", [])),
            human_verified=False,
        )
        db.add(row)

    await db.commit()
    logger.info("project=%s — persisted %d mappings", project_id, len(mappings))


async def _persist_scores(db: AsyncSession, project_id: str, scores: List[Dict]):
    """Persist coverage scores. Wipes previous scores for this project (no snapshot link in MVP)."""
    await db.execute(
        delete(CoverageScore).where(CoverageScore.project_id == project_id)
    )
    await db.flush()

    for s in scores:
        row = CoverageScore(
            project_id=project_id,
            requirement_id=s["requirement_id"],
            snapshot_id=None,  # linked to audit snapshot in future
            total_score=s.get("total_score", 0),
            base_coverage=s.get("base_coverage", 0),
            depth_coverage=s.get("depth_coverage", 0),
            quality_weight=s.get("quality_weight", 0),
            confidence_penalty=s.get("confidence_penalty", 0),
            crossref_bonus=s.get("crossref_bonus", 0),
            matched_tc_count=s.get("matched_tc_count", 0),
            coverage_aspects_present=json.dumps(s.get("coverage_aspects_present", [])),
            coverage_aspects_missing=json.dumps(s.get("coverage_aspects_missing", [])),
        )
        db.add(row)

    await db.commit()
    logger.info("project=%s — persisted %d coverage scores", project_id, len(scores))


# ─── List Mappings ───────────────────────────────────────────────────────────

@router.get("/{project_id}")
async def list_mappings(
    project_id: str,
    requirement_id: Optional[str] = None,
    min_confidence: Optional[float] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all requirement ↔ TC mappings for a project."""
    stmt = (
        select(RequirementTCMapping)
        .where(RequirementTCMapping.project_id == project_id)
        .order_by(RequirementTCMapping.mapping_confidence.desc())
    )
    if requirement_id:
        stmt = stmt.where(RequirementTCMapping.requirement_id == requirement_id)
    if min_confidence is not None:
        stmt = stmt.where(RequirementTCMapping.mapping_confidence >= min_confidence)

    rows = (await db.execute(stmt)).scalars().all()

    return {
        "project_id": project_id,
        "mappings": [_mapping_to_dict(m) for m in rows],
        "total": len(rows),
    }


# ─── Coverage Scores ────────────────────────────────────────────────────────

@router.get("/{project_id}/coverage")
async def coverage_scores(
    project_id: str,
    sort_by: str = Query("total_score", pattern="^(total_score|requirement_id)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    db: AsyncSession = Depends(get_db),
):
    """
    Per-requirement coverage scores.
    Default sort: ascending by score (worst first — actionable).
    """
    stmt = select(CoverageScore).where(CoverageScore.project_id == project_id)

    if sort_by == "total_score":
        col = CoverageScore.total_score.asc() if order == "asc" else CoverageScore.total_score.desc()
    else:
        col = CoverageScore.requirement_id.asc()
    stmt = stmt.order_by(col)

    rows = (await db.execute(stmt)).scalars().all()

    # Enrich with requirement info
    req_ids = [r.requirement_id for r in rows]
    req_stmt = select(Requirement).where(Requirement.id.in_(req_ids)) if req_ids else None
    reqs_by_id = {}
    if req_stmt is not None:
        req_rows = (await db.execute(req_stmt)).scalars().all()
        reqs_by_id = {r.id: r for r in req_rows}

    enriched = []
    for s in rows:
        req = reqs_by_id.get(s.requirement_id)
        enriched.append({
            **_score_to_dict(s),
            "external_id": req.external_id if req else None,
            "title": req.title if req else "Unknown",
            "level": req.level if req else None,
            "taxonomy": json.loads(req.taxonomy) if req and req.taxonomy else None,
        })

    return {
        "project_id": project_id,
        "scores": enriched,
        "total": len(enriched),
    }


# ─── Summary ────────────────────────────────────────────────────────────────

@router.get("/{project_id}/summary")
async def coverage_summary(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Coverage summary with distribution breakdown."""
    stmt = select(CoverageScore).where(CoverageScore.project_id == project_id)
    rows = (await db.execute(stmt)).scalars().all()

    if not rows:
        return {"project_id": project_id, "has_scores": False}

    scores = [r.total_score for r in rows]
    covered = sum(1 for s in scores if s > 0)

    return {
        "project_id": project_id,
        "has_scores": True,
        "total_requirements": len(rows),
        "covered_requirements": covered,
        "uncovered_requirements": len(rows) - covered,
        "coverage_pct": round(covered / len(rows) * 100, 1) if rows else 0,
        "avg_score": round(sum(scores) / len(scores), 1),
        "min_score": round(min(scores), 1),
        "max_score": round(max(scores), 1),
        "distribution": {
            "green_80_100": sum(1 for s in scores if s >= 80),
            "yellow_60_79": sum(1 for s in scores if 60 <= s < 80),
            "orange_30_59": sum(1 for s in scores if 30 <= s < 60),
            "red_0_29": sum(1 for s in scores if s < 30),
        },
    }


# ─── Heatmap ─────────────────────────────────────────────────────────────────

@router.get("/{project_id}/heatmap")
async def coverage_heatmap(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Module-level coverage heatmap.
    Groups scores by taxonomy.module and computes aggregates.
    """
    stmt = select(CoverageScore).where(CoverageScore.project_id == project_id)
    score_rows = (await db.execute(stmt)).scalars().all()

    if not score_rows:
        return {"project_id": project_id, "modules": []}

    # Load requirements for taxonomy
    req_ids = [s.requirement_id for s in score_rows]
    req_stmt = select(Requirement).where(Requirement.id.in_(req_ids))
    req_rows = (await db.execute(req_stmt)).scalars().all()
    reqs_by_id = {r.id: r for r in req_rows}

    # Group by module
    modules: Dict[str, List] = {}
    for s in score_rows:
        req = reqs_by_id.get(s.requirement_id)
        taxonomy = json.loads(req.taxonomy) if req and req.taxonomy else {}
        module = taxonomy.get("module", "unknown")
        modules.setdefault(module, []).append({
            "requirement_id": s.requirement_id,
            "external_id": req.external_id if req else None,
            "title": req.title if req else "Unknown",
            "score": s.total_score,
            "matched_tc_count": s.matched_tc_count,
        })

    heatmap = []
    for module_name, items in sorted(modules.items()):
        scores = [i["score"] for i in items]
        heatmap.append({
            "module": module_name,
            "total_requirements": len(items),
            "avg_score": round(sum(scores) / len(scores), 1),
            "min_score": round(min(scores), 1),
            "covered_count": sum(1 for s in scores if s > 0),
            "critical_gaps": [
                {"external_id": i["external_id"], "title": i["title"], "score": i["score"]}
                for i in items if i["score"] < 30
            ],
            "requirements": items,
        })

    # Sort by avg_score ascending (worst modules first)
    heatmap.sort(key=lambda m: m["avg_score"])

    return {"project_id": project_id, "modules": heatmap}


# ─── Human Verify Mapping ───────────────────────────────────────────────────

@router.patch("/{project_id}/{mapping_id}")
async def verify_mapping(
    project_id: str,
    mapping_id: str,
    body: MappingVerification,
    db: AsyncSession = Depends(get_db),
):
    """Human verify or reject a mapping."""
    mapping = await db.get(RequirementTCMapping, mapping_id)
    if not mapping or mapping.project_id != project_id:
        raise HTTPException(404, "Mapping not found")

    mapping.human_verified = body.human_verified
    if body.mapping_confidence is not None:
        mapping.mapping_confidence = body.mapping_confidence
    if body.coverage_aspects is not None:
        mapping.coverage_aspects = json.dumps(body.coverage_aspects)
    mapping.mapping_method = "human"

    await db.commit()
    await db.refresh(mapping)
    return _mapping_to_dict(mapping)


# ─── Delete All Mappings ─────────────────────────────────────────────────────

@router.delete("/{project_id}")
async def delete_mappings(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Wipe all mappings and scores for a project (before re-run)."""
    m_result = await db.execute(
        delete(RequirementTCMapping).where(RequirementTCMapping.project_id == project_id)
    )
    s_result = await db.execute(
        delete(CoverageScore).where(CoverageScore.project_id == project_id)
    )
    await db.commit()
    return {"deleted_mappings": m_result.rowcount, "deleted_scores": s_result.rowcount}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _mapping_to_dict(m: RequirementTCMapping) -> Dict:
    return {
        "id": m.id,
        "requirement_id": m.requirement_id,
        "project_id": m.project_id,
        "tc_source_file": m.tc_source_file,
        "tc_identifier": m.tc_identifier,
        "mapping_confidence": m.mapping_confidence,
        "mapping_method": m.mapping_method,
        "coverage_aspects": json.loads(m.coverage_aspects) if m.coverage_aspects else [],
        "human_verified": m.human_verified,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _score_to_dict(s: CoverageScore) -> Dict:
    return {
        "id": s.id,
        "requirement_id": s.requirement_id,
        "total_score": s.total_score,
        "base_coverage": s.base_coverage,
        "depth_coverage": s.depth_coverage,
        "quality_weight": s.quality_weight,
        "confidence_penalty": s.confidence_penalty,
        "crossref_bonus": s.crossref_bonus,
        "matched_tc_count": s.matched_tc_count,
        "coverage_aspects_present": json.loads(s.coverage_aspects_present) if s.coverage_aspects_present else [],
        "coverage_aspects_missing": json.loads(s.coverage_aspects_missing) if s.coverage_aspects_missing else [],
    }


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
