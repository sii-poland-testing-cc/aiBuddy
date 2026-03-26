"""
M1 Context Builder API Routes
==============================
Endpoints:
  POST /api/context/{project_id}/build    — upload .docx/.pdf + run M1 pipeline (SSE)
  GET  /api/context/{project_id}/status   — RAG ready + artefact availability
  GET  /api/context/{project_id}/mindmap  — stored mind map JSON
  GET  /api/context/{project_id}/glossary — stored glossary JSON

Artefacts are persisted to the Project DB row AND cached in _context_store
for fast in-memory reads on the same server instance.
"""

import asyncio
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context_builder_workflow import ContextBuilderWorkflow, ProgressEvent
from app.api.sse import SSE_DONE, sse_event
from app.api.streaming import stream_with_keepalive
from app.core.config import settings
from app.core.llm import get_llm
from app.db.engine import AsyncSessionLocal, get_db
from app.db.models import ArtifactLifecycle, Project
from app.rag.context_builder import ContextBuilder
from app.services.context_lifecycle import (
    clear_manifest_for_project,
    register_glossary_items,
    register_graph_items,
)

logger = logging.getLogger("ai_buddy.context")

router = APIRouter()
_context_builder = ContextBuilder()

# Write-through in-memory cache: { project_id: { mind_map, glossary, stats, ... } }
#
# WHY: mind map + glossary payloads can be large (hundreds of nodes); caching
# avoids re-parsing JSON from the DB column on every GET request.
#
# MULTI-WORKER NOTE: this dict lives in a single process. In Gunicorn multi-worker
# deployments each worker has its own independent cache. A build on worker A warms
# A's cache only; other workers cold-miss and fall through to DB until they serve
# their first warm-through request. Correctness is unaffected (DB is authoritative),
# but the cache yields no latency benefit on a fresh worker restart.
#
# LOOKUP ORDER:
#   context_status() → DB-first (must check Chroma for live rag_ready; cache can be stale)
#   get_mindmap() / get_glossary() → cache-first (JSON payload; DB is the fallback)
_context_store: dict = {}

UPLOAD_ROOT = Path(settings.UPLOAD_DIR)
M1_ALLOWED = {".docx", ".pdf"}


# ── Build (SSE) ───────────────────────────────────────────────────────────────

@router.post("/{project_id}/build")
async def build_context(
    project_id: str,
    files: List[UploadFile] = File(...),
    mode: str = Query("append", pattern="^(append|rebuild)$"),
    work_context_id: Optional[str] = Query(None),
):
    """
    Upload Word/PDF files and stream M1 pipeline progress.
    Pass work_context_id to tag artefacts as draft (lifecycle-aware build).
    SSE event shapes:
      {"type": "progress", "data": {"message": str, "progress": float, "stage": str}}
      {"type": "result",   "data": {project_id, rag_ready, mind_map, glossary, stats}}
      {"type": "error",    "data": {"message": str}}
    """
    proj_dir = UPLOAD_ROOT / project_id / "context"
    proj_dir.mkdir(parents=True, exist_ok=True)

    file_paths = []
    for upload in files:
        filename = upload.filename or "upload"
        ext = Path(filename).suffix.lower()
        if ext not in M1_ALLOWED:
            raise HTTPException(
                400,
                f"M1 only accepts .docx and .pdf files, got: '{filename}'"
            )
        dest = proj_dir / filename
        with dest.open("wb") as f:
            shutil.copyfileobj(upload.file, f)
        file_paths.append(str(dest))

    return StreamingResponse(
        _run_m1(project_id, file_paths, mode, work_context_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{project_id}/rebuild-existing")
async def rebuild_from_existing(
    project_id: str,
    mode: str = Query("rebuild", pattern="^(append|rebuild)$"),
    work_context_id: Optional[str] = Query(None),
):
    """
    Re-run the M1 pipeline using documents already on disk.
    No file upload required — reads from the project's context upload directory.
    Pass work_context_id to tag artefacts as draft.
    """
    proj_dir = UPLOAD_ROOT / project_id / "context"
    if not proj_dir.exists():
        raise HTTPException(
            404,
            "No context directory found. Upload documents first via /build."
        )
    file_paths = sorted(
        str(p) for p in proj_dir.iterdir() if p.suffix.lower() in M1_ALLOWED
    )
    if not file_paths:
        raise HTTPException(
            404,
            "No .docx or .pdf files found. Upload documents first via /build."
        )
    return StreamingResponse(
        _run_m1(project_id, file_paths, mode, work_context_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )



async def _run_m1(
    project_id: str,
    file_paths: List[str],
    mode: str = "append",
    work_context_id: Optional[str] = None,
):
    # ── Rebuild: wipe existing Chroma collection + clear cache ────────────────
    if mode == "rebuild":
        _context_builder.delete_collection(project_id)
        _context_store.pop(project_id, None)

    llm = get_llm()
    workflow = ContextBuilderWorkflow(llm=llm, timeout=settings.M1_WORKFLOW_TIMEOUT_SECONDS)
    logger.info(
        "M1 context build STARTED — project=%s mode=%s work_context=%s files=%s",
        project_id, mode, work_context_id, [Path(p).name for p in file_paths],
    )

    # Track last known stage for keepalive messages
    last_progress = {"message": "Processing…", "progress": 0.05, "stage": "parse"}
    result = None

    try:
        handler = workflow.run(
            project_id=project_id,
            file_paths=file_paths,
            work_context_id=work_context_id,
        )

        async for kind, item in stream_with_keepalive(handler):
            if kind == "event":
                if isinstance(item, ProgressEvent):
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

        # ── New filenames from this build ─────────────────────────────────────
        new_filenames = [Path(p).name for p in file_paths]

        # ── Append mode: merge new artefacts with existing ones ───────────────
        existing_files: list[str] = []
        if mode == "append":
            existing = _context_store.get(project_id)
            if not existing:
                # Try loading from DB
                try:
                    async with AsyncSessionLocal() as db:
                        project = await db.get(Project, project_id)
                        if project and project.context_built_at:
                            existing = {
                                "mind_map": project.mind_map or {"nodes": [], "edges": []},
                                "glossary": project.glossary or [],
                            }
                            existing_files = project.context_files or []
                except Exception:
                    pass
            else:
                existing_files = existing.get("context_files", [])
            if existing:
                result["mind_map"] = _merge_mind_maps(existing["mind_map"], result["mind_map"])
                result["glossary"] = _merge_glossaries(existing["glossary"], result["glossary"])
                result["stats"]["entity_count"] = len(result["mind_map"]["nodes"])
                result["stats"]["term_count"] = len(result["glossary"])

        # Merge filenames (append: union; rebuild: only new)
        merged_files = list(dict.fromkeys(existing_files + new_filenames)) if mode == "append" else new_filenames

        # ── Persist artefacts to DB ───────────────────────────────────────────
        built_at = datetime.now(timezone.utc)
        try:
            async with AsyncSessionLocal() as db:
                project = await db.get(Project, project_id)
                if project:
                    project.mind_map = result["mind_map"]
                    project.glossary = result["glossary"]
                    project.context_stats = result["stats"]
                    project.context_built_at = built_at
                    project.context_files = merged_files
                    await db.commit()
                else:
                    logger.warning(
                        "Project '%s' not found in DB — artefacts not persisted.", project_id
                    )
        except Exception as db_exc:
            logger.error("Failed to persist M1 artefacts for '%s': %s", project_id, db_exc)

        # ── Register / update ArtifactLifecycle manifest ──────────────────────
        try:
            async with AsyncSessionLocal() as db:
                if mode == "rebuild":
                    await clear_manifest_for_project(db, project_id)
                await register_graph_items(
                    db, project_id, work_context_id,
                    result["mind_map"].get("nodes", []),
                    result["mind_map"].get("edges", []),
                )
                await register_glossary_items(
                    db, project_id, work_context_id,
                    result.get("glossary", []),
                )
        except Exception as lc_exc:
            logger.error("Failed to register lifecycle manifest for '%s': %s", project_id, lc_exc)

        # ── Write-through cache ───────────────────────────────────────────────
        _context_store[project_id] = {
            "mind_map": result["mind_map"],
            "glossary": result["glossary"],
            "stats": result["stats"],
            "context_built_at": built_at.isoformat(),
            "context_files": merged_files,
        }

        stats = result.get("stats", {})
        logger.info(
            "M1 context build DONE — project=%s entities=%s relations=%s terms=%s files=%s",
            project_id,
            stats.get("entity_count", "?"),
            stats.get("relation_count", "?"),
            stats.get("term_count", "?"),
            merged_files,
        )
        yield sse_event({"type": "result", "data": result})

    except Exception as exc:
        logger.error("M1 context build FAILED — project=%s error=%s", project_id, exc)
        yield sse_event({"type": "error", "data": {"message": str(exc)}})
    finally:
        yield SSE_DONE


# ── Merge helpers ─────────────────────────────────────────────────────────────

def _merge_mind_maps(existing: dict, new: dict) -> dict:
    """Merge two mind maps, deduplicating nodes by id and edges by (source, target)."""
    node_ids: set[str] = set()
    nodes: list[dict] = []
    for n in existing.get("nodes", []) + new.get("nodes", []):
        if n["id"] not in node_ids:
            node_ids.add(n["id"])
            nodes.append(n)

    edge_keys: set[tuple] = set()
    edges: list[dict] = []
    for e in existing.get("edges", []) + new.get("edges", []):
        key = (e["source"], e["target"])
        if key not in edge_keys:
            edge_keys.add(key)
            edges.append(e)

    return {"nodes": nodes, "edges": edges}


def _merge_glossaries(existing: list, new: list) -> list:
    """Merge two glossary lists; new entries win on duplicate term (case-insensitive)."""
    merged: dict[str, dict] = {t["term"].lower(): t for t in existing}
    for t in new:
        merged[t["term"].lower()] = t  # new wins
    return list(merged.values())


# ── Status ────────────────────────────────────────────────────────────────────

@router.get("/{project_id}/status")
async def context_status(project_id: str, db: AsyncSession = Depends(get_db)):
    # Prefer DB as authoritative source; fall back to in-memory cache
    project = await db.get(Project, project_id)
    if project and project.context_built_at:
        # rag_ready only True when M1 completed (context_built_at set) AND Chroma
        # still has vectors (guards against manual collection deletion).
        # Crucially this prevents M2 test-file uploads (which write to the same
        # Chroma collection) from falsely advertising rag_ready=True.
        rag_ready = await _context_builder.is_indexed(project_id)
        stats = project.context_stats
        built_at = (
            project.context_built_at.isoformat()
            if isinstance(project.context_built_at, datetime)
            else str(project.context_built_at)
        )
        files = project.context_files or []
        return {
            "project_id": project_id,
            "rag_ready": rag_ready,
            "artefacts_ready": True,
            "stats": stats,
            "context_built_at": built_at,
            "document_count": len(files),
            "context_files": files,
        }

    # M1 has never run for this project — Chroma may contain M2 test-file
    # vectors but those do not constitute M1 context.  Always return False.
    cache = _context_store.get(project_id, {})
    files = cache.get("context_files", [])
    return {
        "project_id": project_id,
        "rag_ready": False,
        "artefacts_ready": bool(cache),
        "stats": cache.get("stats"),
        "context_built_at": cache.get("context_built_at"),
        "document_count": len(files),
        "context_files": files,
    }


# ── Mind map ──────────────────────────────────────────────────────────────────

@router.get("/{project_id}/mindmap")
async def get_mindmap(
    project_id: str,
    work_context_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    # Load full mind map (cache-first, DB fallback)
    cache = _context_store.get(project_id)
    if cache:
        mind_map = cache["mind_map"]
    else:
        project = await db.get(Project, project_id)
        if not project or not project.context_built_at:
            raise HTTPException(404, "Context not built yet for this project. Run /build first.")
        if not project.mind_map:
            raise HTTPException(404, "Mind map not available.")
        _context_store[project_id] = _load_project_artefacts(project)
        mind_map = _context_store[project_id]["mind_map"]

    # If no work_context_id: filter via manifest table (promoted items only).
    # Fallback to full data when no manifest rows exist (pre-Phase-4 projects).
    filtered = await _filter_mindmap_by_manifest(db, project_id, mind_map, work_context_id)
    return filtered


async def _filter_mindmap_by_manifest(
    db: AsyncSession,
    project_id: str,
    mind_map: dict,
    work_context_id: Optional[str],
) -> dict:
    """Filter mind map nodes/edges using the ArtifactLifecycle manifest.

    - No work_context_id: return promoted items only; fall back to full data if no manifest rows.
    - With work_context_id: return items for that context.
    """
    node_stmt = select(ArtifactLifecycle).where(
        ArtifactLifecycle.project_id == project_id,
        ArtifactLifecycle.artifact_type == "graph_node",
    )
    edge_stmt = select(ArtifactLifecycle).where(
        ArtifactLifecycle.project_id == project_id,
        ArtifactLifecycle.artifact_type == "graph_edge",
    )

    if work_context_id is not None:
        node_stmt = node_stmt.where(ArtifactLifecycle.work_context_id == work_context_id)
        edge_stmt = edge_stmt.where(ArtifactLifecycle.work_context_id == work_context_id)
    else:
        node_stmt = node_stmt.where(ArtifactLifecycle.lifecycle_status == "promoted")
        edge_stmt = edge_stmt.where(ArtifactLifecycle.lifecycle_status == "promoted")

    node_rows = (await db.execute(node_stmt)).scalars().all()
    edge_rows = (await db.execute(edge_stmt)).scalars().all()

    # Fallback: if no manifest rows exist yet, return full mind map unchanged
    if not node_rows and not edge_rows:
        return mind_map

    allowed_node_ids = {r.artifact_item_id for r in node_rows}
    allowed_edge_keys = {r.artifact_item_id for r in edge_rows}

    nodes = [n for n in mind_map.get("nodes", []) if n["id"] in allowed_node_ids]
    edges = [e for e in mind_map.get("edges", [])
             if f"{e['source']}→{e['target']}" in allowed_edge_keys]
    return {"nodes": nodes, "edges": edges}


# ── Glossary ──────────────────────────────────────────────────────────────────

@router.get("/{project_id}/glossary")
async def get_glossary(
    project_id: str,
    work_context_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    # Load full glossary (cache-first, DB fallback)
    cache = _context_store.get(project_id)
    if cache:
        glossary = cache["glossary"]
    else:
        project = await db.get(Project, project_id)
        if not project or not project.context_built_at:
            raise HTTPException(404, "Context not built yet for this project. Run /build first.")
        if not project.glossary:
            raise HTTPException(404, "Glossary not available.")
        _context_store[project_id] = _load_project_artefacts(project)
        glossary = _context_store[project_id]["glossary"]

    # Filter via manifest table; fallback to full data when no manifest rows exist
    return await _filter_glossary_by_manifest(db, project_id, glossary, work_context_id)


async def _filter_glossary_by_manifest(
    db: AsyncSession,
    project_id: str,
    glossary: list,
    work_context_id: Optional[str],
) -> list:
    """Filter glossary terms using the ArtifactLifecycle manifest."""
    stmt = select(ArtifactLifecycle).where(
        ArtifactLifecycle.project_id == project_id,
        ArtifactLifecycle.artifact_type == "glossary_term",
    )
    if work_context_id is not None:
        stmt = stmt.where(ArtifactLifecycle.work_context_id == work_context_id)
    else:
        stmt = stmt.where(ArtifactLifecycle.lifecycle_status == "promoted")

    rows = (await db.execute(stmt)).scalars().all()

    # Fallback: no manifest rows → return full glossary unchanged
    if not rows:
        return glossary

    allowed_terms = {r.artifact_item_id for r in rows}
    return [t for t in glossary if t.get("term", "").lower().replace(" ", "_") in allowed_terms
            or t.get("term", "") in allowed_terms]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_project_artefacts(project: Project) -> dict:
    """Build a _context_store entry from a Project ORM row (no DB calls)."""
    return {
        "mind_map": project.mind_map or {"nodes": [], "edges": []},
        "glossary": project.glossary or [],
        "stats": project.context_stats or {},
        "context_built_at": (
            project.context_built_at.isoformat()
            if isinstance(project.context_built_at, datetime)
            else str(project.context_built_at)
        ),
    }
