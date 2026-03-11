"""
/api/chat  –  Streaming SSE endpoint
=====================================
Accepts a user message + project_id and runs the appropriate
LlamaIndex Workflow, streaming intermediate events back to the frontend.
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, AsyncGenerator, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.audit_workflow import AuditWorkflow, AnalysisProgressEvent
from app.agents.optimize_workflow import OptimizeWorkflow, OptimizeProgressEvent
from app.core.llm import get_llm
from app.db.engine import AsyncSessionLocal, get_db
from app.db.models import AuditSnapshot, ProjectFile
from app.rag.context_builder import ContextBuilder

logger = logging.getLogger("ai_buddy.chat")

router = APIRouter()

_context_builder = ContextBuilder()


# ─── Request / Response ───────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    project_id: str
    message: str
    file_paths: list[str] = []
    tier: str = "audit"                        # "audit" | "optimize" | "regenerate"
    audit_report: Optional[Dict[str, Any]] = None  # required for tier="optimize"


# ─── Route ────────────────────────────────────────────────────────────────────

@router.post("/stream")
async def chat_stream(req: ChatRequest):
    """
    SSE stream:  text/event-stream
    Each event is a JSON object:
      { "type": "progress" | "result" | "error", "data": {...} }
    """
    return StreamingResponse(
        _run_workflow(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


async def save_snapshot(
    project_id: str,
    result: dict,
    files_used: List[str],
    db: AsyncSession,
) -> str:
    """
    Saves audit result as AuditSnapshot.
    Computes diff against the most recent previous snapshot.
    Enforces max 5 snapshots per project (deletes oldest if exceeded).
    Returns the new snapshot id.
    """
    summary = result.get("summary", {})
    recommendations = result.get("recommendations", [])
    requirements_uncovered = summary.get("requirements_uncovered", [])

    # Load previous snapshots (ordered desc by created_at)
    stmt = (
        select(AuditSnapshot)
        .where(AuditSnapshot.project_id == project_id)
        .order_by(AuditSnapshot.created_at.desc())
    )
    existing = list((await db.execute(stmt)).scalars().all())
    previous = existing[0] if existing else None

    # Compute diff vs previous snapshot
    diff = None
    if previous:
        prev_summary    = json.loads(previous.summary or "{}")
        prev_uncovered  = set(json.loads(previous.requirements_uncovered or "[]"))
        curr_uncovered  = set(requirements_uncovered)
        prev_files      = set(json.loads(previous.files_used or "[]"))
        curr_files      = set(files_used)

        diff = {
            "coverage_delta": round(
                summary.get("coverage_pct", 0) - prev_summary.get("coverage_pct", 0), 1
            ),
            "duplicates_delta": (
                summary.get("duplicates_found", 0) - prev_summary.get("duplicates_found", 0)
            ),
            "new_covered":      list(prev_uncovered - curr_uncovered),
            "newly_uncovered":  list(curr_uncovered - prev_uncovered),
            "files_added":      list(curr_files - prev_files),
            "files_removed":    list(prev_files - curr_files),
        }

    snapshot = AuditSnapshot(
        project_id=project_id,
        files_used=json.dumps(files_used),
        summary=json.dumps(summary),
        requirements_uncovered=json.dumps(requirements_uncovered),
        recommendations=json.dumps(recommendations),
        diff=json.dumps(diff) if diff is not None else None,
    )
    db.add(snapshot)

    # Enforce max 5 snapshots — delete oldest if exceeded
    if len(existing) >= 5:
        for old in existing[4:]:
            await db.delete(old)

    await db.commit()
    await db.refresh(snapshot)

    # Update last_used_in_audit_id on matching ProjectFiles
    used_filenames = [Path(p).name for p in files_used]
    if used_filenames:
        await db.execute(
            update(ProjectFile)
            .where(ProjectFile.project_id == project_id)
            .where(ProjectFile.filename.in_(used_filenames))
            .values(last_used_in_audit_id=snapshot.id)
        )
        await db.commit()

    logger.info("project=%s — snapshot saved: %s", project_id, snapshot.id)
    return snapshot.id


async def _run_workflow(req: ChatRequest) -> AsyncGenerator[str, None]:
    llm = get_llm()

    # Resolve effective file paths: use request paths if provided,
    # otherwise auto-load all uploaded files for this project from DB.
    # Only auto-load for workflow tiers (audit/optimize) — not for rag_chat
    # conversational queries from the Context Builder page.
    file_paths = list(req.file_paths)
    if not file_paths and req.tier in ("audit", "optimize"):
        try:
            async with AsyncSessionLocal() as db:
                stmt = select(ProjectFile.file_path).where(
                    ProjectFile.project_id == req.project_id
                )
                rows = (await db.execute(stmt)).scalars().all()
                file_paths = list(rows)
        except Exception as exc:
            logger.warning("Could not load project files from DB: %s", exc)

    logger.info(
        "project_id=%s file_paths=%d tier=%s",
        req.project_id, len(file_paths), req.tier,
    )

    # No files anywhere → RAG-grounded conversational response
    if not file_paths:
        try:
            logger.info("Conversational path: project_id=%s", req.project_id)
            is_indexed = await _context_builder.is_indexed(req.project_id)
            logger.info("is_indexed(%s) = %s", req.project_id, is_indexed)

            # Detect term explanation queries
            if req.message.lower().startswith("wyjaśnij termin:"):
                term_name = req.message.split(":", 1)[1].strip().strip('"')
                rag_query = f"{term_name} definition description context usage"
            else:
                term_name = None
                rag_query = req.message

            sources: list[dict] = []
            if is_indexed:
                logger.info("RAG retrieval for project %s, query=%r", req.project_id, rag_query)
                rag_context, sources = await _context_builder.build_with_sources(
                    req.project_id, query=rag_query
                )
                if term_name is not None:
                    prompt = (
                        f'You are a QA domain expert.\n'
                        f'Explain the term "{term_name}" based ONLY on the project documentation below.\n\n'
                        f'Structure your answer in exactly three sections:\n'
                        f'1. **Opis** — expanded definition (2-4 sentences)\n'
                        f'2. **Kontekst** — how and where this term is used in the project\n'
                        f'3. **Powiązane terminy** — comma-separated list of related terms from the docs\n\n'
                        f'If the term is not in the documentation, say so explicitly.\n'
                        f'Do not use general knowledge — only what is in the documentation below.\n\n'
                        f'Documentation:\n{rag_context}'
                    )
                else:
                    prompt = (
                        "You are a QA domain assistant. "
                        "Answer questions using ONLY the following context from project documentation. "
                        "If the answer is not in the context, say so explicitly.\n\n"
                        f"Context:\n{rag_context}\n\n"
                        f"User: {req.message}\n\nAssistant:"
                    )
            else:
                logger.info("No RAG index for project %s — using generic response", req.project_id)
                prompt = (
                    "You are AI Buddy, a QA specialist assistant. "
                    "Your job is to audit and optimise test suites uploaded by the user.\n\n"
                    f"User: {req.message}\n\n"
                    "Reply helpfully and concisely. "
                    "If no files have been uploaded yet, ask the user to upload their test suite files "
                    "(Excel, CSV, JSON, .feature, etc.) so you can begin the audit."
                )

            if llm is None:
                raise RuntimeError("LLM is not configured. Check LLM_PROVIDER and credentials.")
            response = await llm.acomplete(prompt)
            yield _sse({"type": "result", "data": {"message": str(response), "rag_sources": sources}})
        except Exception as exc:
            yield _sse({"type": "error", "data": {"message": str(exc)}})
        finally:
            yield "data: [DONE]\n\n"
        return

    workflow_map = {
        "audit": AuditWorkflow,
        "optimize": OptimizeWorkflow,
        # "regenerate": RegenerateWorkflow,  # add Tier 3
    }

    WorkflowClass = workflow_map.get(req.tier, AuditWorkflow)
    logger.info("workflow=%s", WorkflowClass.__name__)

    workflow = WorkflowClass(llm=llm, timeout=120)

    try:
        handler = workflow.run(
            project_id=req.project_id,
            file_paths=file_paths,
            audit_report=req.audit_report,
            user_message=req.message,
        )

        # Stream intermediate events (both tiers share the same payload shape)
        async for ev in handler.stream_events():
            if isinstance(ev, (AnalysisProgressEvent, OptimizeProgressEvent)):
                yield _sse({
                    "type": "progress",
                    "data": {"message": ev.message, "progress": ev.progress},
                })
                await asyncio.sleep(0)   # yield control to the event loop

        # Final result
        result = await handler

        # Persist audit snapshot (audit tier only)
        if req.tier in ("audit",):
            try:
                async with AsyncSessionLocal() as db:
                    snapshot_id = await save_snapshot(
                        project_id=req.project_id,
                        result=result,
                        files_used=file_paths,
                        db=db,
                    )
                    result["snapshot_id"] = snapshot_id
            except Exception as exc:
                logger.warning("Failed to save audit snapshot: %s", exc)

        yield _sse({"type": "result", "data": result})

    except Exception as exc:
        yield _sse({"type": "error", "data": {"message": str(exc)}})

    finally:
        yield "data: [DONE]\n\n"


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
