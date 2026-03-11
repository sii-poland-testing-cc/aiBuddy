"""
/api/chat  –  Streaming SSE endpoint
=====================================
Accepts a user message + project_id and runs the appropriate
LlamaIndex Workflow, streaming intermediate events back to the frontend.
"""

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.agents.audit_workflow import AuditWorkflow, AnalysisProgressEvent
from app.agents.optimize_workflow import OptimizeWorkflow, OptimizeProgressEvent
from app.core.llm import get_llm
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


async def _run_workflow(req: ChatRequest) -> AsyncGenerator[str, None]:
    llm = get_llm()

    # No files attached → RAG-grounded conversational response
    if not req.file_paths:
        try:
            logger.info("Conversational path: project_id=%s", req.project_id)
            is_indexed = await _context_builder.is_indexed(req.project_id)
            logger.info("is_indexed(%s) = %s", req.project_id, is_indexed)

            sources: list[dict] = []
            if is_indexed:
                logger.info("RAG retrieval for project %s, query=%r", req.project_id, req.message)
                rag_context, sources = await _context_builder.build_with_sources(
                    req.project_id, query=req.message
                )
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

    WorkflowClass = workflow_map.get(req.tier)
    if not WorkflowClass:
        yield _sse({"type": "error", "data": {"message": f"Unknown tier: {req.tier}"}})
        yield "data: [DONE]\n\n"
        return

    workflow = WorkflowClass(llm=llm, timeout=120)

    try:
        handler = workflow.run(
            project_id=req.project_id,
            file_paths=req.file_paths,
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
        yield _sse({"type": "result", "data": result})

    except Exception as exc:
        yield _sse({"type": "error", "data": {"message": str(exc)}})

    finally:
        yield "data: [DONE]\n\n"


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
