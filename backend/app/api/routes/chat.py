"""
/api/chat  –  Streaming SSE endpoint
=====================================
Accepts a user message + project_id and runs the appropriate
LlamaIndex Workflow, streaming intermediate events back to the frontend.
"""

import asyncio
import logging
import re

from sqlalchemy import select
from typing import Any, AsyncGenerator, List
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.api.schemas import ChatRequest
from app.agents.audit_workflow import AuditWorkflow, AnalysisProgressEvent
from app.agents.optimize_workflow import OptimizeWorkflow, OptimizeProgressEvent
from app.api.sse import SSE_DONE, sse_event
from app.api.streaming import stream_with_keepalive
from app.core.config import settings
from app.core.llm import get_llm
from app.db.engine import AsyncSessionLocal
from app.db.models import Project, ProjectFile
from app.db.queries import audit_file_filter
from app.rag.context_builder import ContextBuilder
from app.services.snapshots import save_snapshot

logger = logging.getLogger("ai_buddy.chat")

router = APIRouter()

_context_builder = ContextBuilder()


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


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _has_m1_context(project_id: str) -> bool:
    """
    Returns True only when BOTH conditions hold:
      1. project.context_built_at IS NOT NULL  — M1 pipeline completed at least once
      2. Chroma collection has vectors         — guards against manual index deletion

    Without the context_built_at gate, a project with only M2 audit files indexed
    (CSV/XLSX) would incorrectly enter the RAG chat path and query test-file content
    as if it were documentation context.
    """
    try:
        async with AsyncSessionLocal() as db:
            project = await db.get(Project, project_id)
            if not project or not project.context_built_at:
                return False
        return await _context_builder.is_indexed(project_id)
    except Exception as exc:
        logger.warning("_has_m1_context check failed for %s: %s", project_id, exc)
        return False


async def _auto_load_audit_files(project_id: str) -> List[str]:
    """
    Load file paths for audit from DB using the shared selection policy:
      URL/Jira/Confluence sources always included; 'file' sources only if unused.
    See audit_file_filter() in app/db/queries.py for the canonical rule.
    """
    try:
        async with AsyncSessionLocal() as db:
            stmt = select(ProjectFile.file_path).where(*audit_file_filter(project_id))
            rows = (await db.execute(stmt)).scalars().all()
            return list(rows)
    except Exception as exc:
        logger.warning("Could not load project files from DB: %s", exc)
        return []


def _resolve_rag_query(message: str) -> tuple[str | None, str]:
    """
    Parse a user message into (term_name, rag_query).

    - "wyjaśnij termin: X"  →  term explanation mode; term_name set, query uses
                                definition keywords for targeted RAG retrieval.
    - Message contains a req ID (FR-001, REQ-2, UC-3, …)  →  query rewritten to
      target that ID directly (raw message has low cosine similarity to SRS chunks).
    - Otherwise  →  rag_query = message verbatim.

    Returns (None, rag_query) when no term explanation is requested.
    """
    if message.lower().startswith("wyjaśnij termin:"):
        term_name = message.split(":", 1)[1].strip().strip('"')
        return term_name, f"{term_name} definition description context usage"

    req_id_match = re.search(
        r'\b(FR|REQ|UC|NFR|AR|BR|SR|AC)-\d+\b', message, re.IGNORECASE
    )
    if req_id_match:
        req_id = req_id_match.group(0).upper()
        return None, f"{req_id} requirement description acceptance criteria details"

    return None, message


async def _handle_rag_chat(
    req: ChatRequest, llm: Any
) -> AsyncGenerator[str, None]:
    """
    Handle the no-files conversational path.
    Yields SSE events: result on success, error on failure, SSE_DONE always.
    """
    try:
        logger.info("Conversational path: project_id=%s", req.project_id)
        has_context = await _has_m1_context(req.project_id)
        logger.info("has_m1_context(%s) = %s", req.project_id, has_context)

        term_name, rag_query = _resolve_rag_query(req.message)
        # Use a higher top_k for focused queries (term explanation or req-ID lookup)
        # so we capture all chunks describing a single requirement or term.
        is_targeted = term_name is not None or rag_query != req.message

        sources: list[dict] = []
        if has_context:
            retrieval_top_k = 8 if is_targeted else 5
            logger.info(
                "RAG retrieval for project %s, query=%r, top_k=%d",
                req.project_id, rag_query, retrieval_top_k,
            )
            rag_context, sources = await _context_builder.build_with_sources(
                req.project_id, query=rag_query, top_k=retrieval_top_k
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
        yield sse_event({"type": "result", "data": {"message": str(response), "rag_sources": sources}})
    except Exception as exc:
        yield sse_event({"type": "error", "data": {"message": str(exc)}})
    finally:
        yield SSE_DONE


async def _run_workflow(req: ChatRequest) -> AsyncGenerator[str, None]:
    llm = get_llm()

    # Resolve effective file paths: use request paths if provided,
    # otherwise auto-load all uploaded files for this project from DB.
    # Only auto-load for workflow tiers (audit/optimize) — not for rag_chat
    # conversational queries from the Context Builder page.
    file_paths = list(req.file_paths)
    if not file_paths and req.tier in ("audit", "optimize"):
        file_paths = await _auto_load_audit_files(req.project_id)

    logger.info(
        "project_id=%s file_paths=%d tier=%s",
        req.project_id, len(file_paths), req.tier,
    )

    # No files anywhere → RAG-grounded conversational response
    if not file_paths:
        async for chunk in _handle_rag_chat(req, llm):
            yield chunk
        return

    workflow_map = {
        "audit": AuditWorkflow,
        "optimize": OptimizeWorkflow,
        # "regenerate": RegenerateWorkflow,  # add Tier 3
    }

    WorkflowClass = workflow_map.get(req.tier, AuditWorkflow)
    logger.info("workflow=%s", WorkflowClass.__name__)

    workflow = WorkflowClass(llm=llm, timeout=settings.M2_WORKFLOW_TIMEOUT_SECONDS)

    result = None
    last_progress = {"message": "Processing…", "progress": 0.05}

    try:
        handler = workflow.run(
            project_id=req.project_id,
            file_paths=file_paths,
            audit_report=req.audit_report,
            user_message=req.message,
        )

        async for kind, item in stream_with_keepalive(handler):
            if kind == "event":
                if isinstance(item, (AnalysisProgressEvent, OptimizeProgressEvent)):
                    last_progress = {"message": item.message, "progress": item.progress}
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

        # Persist audit snapshot (audit tier only)
        if req.tier == "audit":
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

        yield sse_event({"type": "result", "data": result})

    except Exception as exc:
        yield sse_event({"type": "error", "data": {"message": str(exc)}})

    finally:
        yield SSE_DONE
