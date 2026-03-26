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
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import StreamingResponse
from app.api.schemas import JiraIssueIn
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.context_builder_workflow import ContextBuilderWorkflow, ProgressEvent
from app.api.sse import SSE_DONE, sse_event
from app.api.streaming import stream_with_keepalive
from app.core.config import settings
from app.core.llm import get_llm
from app.db.engine import AsyncSessionLocal, get_db
from app.db.models import Project
from app.rag.context_builder import ContextBuilder
from app.services.jira_client import JiraClient, to_markdown

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


def _jira_md_paths(project_id: str) -> list[str]:
    """Return sorted paths of Jira markdown files already fetched for this project."""
    jira_dir = UPLOAD_ROOT / project_id / "context" / "jira"
    if not jira_dir.exists():
        return []
    return sorted(str(p) for p in jira_dir.iterdir() if p.suffix.lower() == ".md")


def _jira_mds_for_append(project_id: str, cf: dict, context_built_at) -> list[str]:
    """
    Return Jira MD paths that need to be included in an append build.

    A Jira item is included when its indexed_at > context_built_at — meaning it was
    added/refreshed after the last M1 run and hasn't been processed by the pipeline yet.
    Items with no indexed_at or no prior build are always included.
    """
    jira_dir = UPLOAD_ROOT / project_id / "context" / "jira"
    if not jira_dir.exists():
        return []

    result = []
    for item in cf.get("jira", []):
        md_path = jira_dir / f"{item['key']}.md"
        if not md_path.exists():
            continue
        indexed_at_str = item.get("indexed_at")
        if context_built_at is None or indexed_at_str is None:
            result.append(str(md_path))
            continue
        try:
            indexed_at = datetime.fromisoformat(indexed_at_str)
            built_at = context_built_at if context_built_at.tzinfo else context_built_at.replace(tzinfo=timezone.utc)
            if indexed_at > built_at:
                result.append(str(md_path))
        except (ValueError, TypeError):
            result.append(str(md_path))

    return sorted(result)


def _parse_context_files(raw) -> dict:
    """
    Parse context_files from DB into canonical dict form.

    Handles all formats for backward compatibility:
      Legacy list:  ["doc.pdf", "jira:KEY"]
      Dict v1:      {"docs": ["doc.pdf"], "jira": [...]}   (docs as plain strings)
      Dict v2:      {"docs": [{"name": "doc.pdf", "indexed_at": "..."}], "jira": [...]}
    """
    if raw is None:
        return {"docs": [], "jira": []}
    if isinstance(raw, list):
        # Oldest format — plain string list, possibly with "jira:" prefix entries
        docs = [{"name": f, "indexed_at": None} for f in raw if not f.startswith("jira:")]
        jira = [{"key": f[5:], "indexed": True, "indexed_at": None} for f in raw if f.startswith("jira:")]
        return {"docs": docs, "jira": jira}
    if isinstance(raw, dict):
        raw_docs = raw.get("docs", [])
        docs = [
            d if isinstance(d, dict) else {"name": d, "indexed_at": None}
            for d in raw_docs
        ]
        return {"docs": docs, "jira": list(raw.get("jira", []))}
    return {"docs": [], "jira": []}


# ── Build (SSE) ───────────────────────────────────────────────────────────────

@router.post("/{project_id}/build")
async def build_context(
    project_id: str,
    files: List[UploadFile] = File(...),
    mode: str = Query("append", pattern="^(append|rebuild)$"),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload Word/PDF files and stream M1 pipeline progress.
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

    project = await db.get(Project, project_id)
    cf = _parse_context_files(project.context_files if project else None)
    if mode == "rebuild":
        file_paths.extend(_jira_md_paths(project_id))
    else:
        # append: only Jira items added/refreshed after the last M1 build
        file_paths.extend(_jira_mds_for_append(project_id, cf, project.context_built_at if project else None))

    return StreamingResponse(
        _run_m1(project_id, file_paths, mode),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{project_id}/rebuild-existing")
async def rebuild_from_existing(
    project_id: str,
    mode: str = Query("rebuild", pattern="^(append|rebuild)$"),
    db: AsyncSession = Depends(get_db),
):
    """
    Re-run the M1 pipeline using documents already on disk.
    No file upload required — reads from the project's context upload directory.
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
    project = await db.get(Project, project_id)
    cf = _parse_context_files(project.context_files if project else None)
    if mode == "rebuild":
        file_paths.extend(_jira_md_paths(project_id))
    else:
        file_paths.extend(_jira_mds_for_append(project_id, cf, project.context_built_at if project else None))

    if not file_paths:
        raise HTTPException(
            404,
            "No context files found (.docx, .pdf, or Jira issues). Upload documents first via /build."
        )
    return StreamingResponse(
        _run_m1(project_id, file_paths, mode),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )



async def _run_m1(project_id: str, file_paths: List[str], mode: str = "append"):
    # ── Rebuild: wipe existing Chroma collection + clear cache ────────────────
    if mode == "rebuild":
        _context_builder.delete_collection(project_id)
        _context_store.pop(project_id, None)

    norm = lambda p: str(p).replace("\\", "/")

    # indexed_at is stamped NOW — before the workflow runs — so it is always
    # earlier than context_built_at (set after the workflow completes).
    # This makes `indexed_at < context_built_at` naturally true for every file
    # processed in this run, which is used as the "already indexed" guard in
    # subsequent append builds.
    now_iso = datetime.now(timezone.utc).isoformat()

    # ── Pre-load existing state (append needs it both for filtering and merge) ─
    existing_cf: dict = {"docs": [], "jira": []}
    last_built_at: Optional[datetime] = None
    existing_artefacts: Optional[dict] = None

    if mode == "append":
        cached = _context_store.get(project_id)
        if cached:
            existing_cf = _parse_context_files(cached.get("context_files"))
            existing_artefacts = {
                "mind_map": cached.get("mind_map", {"nodes": [], "edges": []}),
                "glossary": cached.get("glossary", []),
            }
            raw_built = cached.get("context_built_at")
            if raw_built:
                try:
                    last_built_at = datetime.fromisoformat(raw_built)
                except Exception:
                    pass
        if not last_built_at or existing_artefacts is None:
            try:
                async with AsyncSessionLocal() as db:
                    project = await db.get(Project, project_id)
                    if project and project.context_built_at:
                        existing_cf = _parse_context_files(project.context_files)
                        last_built_at = project.context_built_at
                        existing_artefacts = {
                            "mind_map": project.mind_map or {"nodes": [], "edges": []},
                            "glossary": project.glossary or [],
                        }
            except Exception:
                pass

        # ── Filter: skip non-jira docs already indexed since the last build ───
        # A doc is "already indexed" when its indexed_at < last context_built_at,
        # meaning it was indexed during a previous build and its vectors are still
        # in Chroma (append mode never wipes the collection).
        if last_built_at:
            doc_map = {d["name"]: d for d in existing_cf["docs"]}

            def _already_indexed(path: str) -> bool:
                if "/context/jira/" in norm(path):
                    return False  # Jira handled by _jira_mds_for_append
                doc = doc_map.get(Path(path).name)
                if not doc or not doc.get("indexed_at"):
                    return False  # new file — must be processed
                try:
                    indexed_dt = datetime.fromisoformat(doc["indexed_at"])
                    lba = last_built_at
                    # Normalise to naive UTC — SQLite may return naive datetimes
                    if indexed_dt.tzinfo is not None:
                        indexed_dt = indexed_dt.replace(tzinfo=None)
                    if lba.tzinfo is not None:  # type: ignore[union-attr]
                        lba = lba.replace(tzinfo=None)
                    return indexed_dt < lba
                except Exception:
                    return False

            non_jira_before = sum(1 for p in file_paths if "/context/jira/" not in norm(p))
            file_paths = [p for p in file_paths if not _already_indexed(p)]
            non_jira_after = sum(1 for p in file_paths if "/context/jira/" not in norm(p))
            skipped = non_jira_before - non_jira_after
            if skipped:
                logger.info("M1 append: skipping %d already-indexed doc(s)", skipped)

        # ── Nothing left to process — short-circuit without running workflow ──
        if not file_paths:
            logger.info("M1 append: nothing to process for project=%s", project_id)
            yield sse_event({
                "type": "noop",
                "data": {"message": "Wszystkie pliki są już zaindeksowane — brak zmian do przetworzenia."},
            })
            yield SSE_DONE
            return

    llm = get_llm()
    workflow = ContextBuilderWorkflow(llm=llm, timeout=settings.M1_WORKFLOW_TIMEOUT_SECONDS)
    logger.info(
        "M1 context build STARTED — project=%s mode=%s files=%s",
        project_id, mode, [Path(p).name for p in file_paths],
    )

    # Track last known stage for keepalive messages
    last_progress = {"message": "Processing…", "progress": 0.05, "stage": "parse"}
    result = None

    try:
        handler = workflow.run(project_id=project_id, file_paths=file_paths)

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

        # ── Docs processed in this run (non-jira, with fresh indexed_at) ──────
        new_docs = [
            {"name": Path(p).name, "indexed_at": now_iso}
            for p in file_paths if "/context/jira/" not in norm(p)
        ]

        # ── Merge artefacts (append only) ─────────────────────────────────────
        if mode == "append" and existing_artefacts:
            result["mind_map"] = _merge_mind_maps(existing_artefacts["mind_map"], result["mind_map"])
            result["glossary"] = _merge_glossaries(existing_artefacts["glossary"], result["glossary"])
            result["stats"]["entity_count"] = len(result["mind_map"]["nodes"])
            result["stats"]["term_count"] = len(result["glossary"])

        # ── Merge context_files ────────────────────────────────────────────────
        if mode == "append":
            # Start from existing docs; overwrite indexed_at for any file that was
            # re-processed in this run; add newly seen files.
            existing_doc_map = {d["name"]: d for d in existing_cf["docs"]}
            for d in new_docs:
                existing_doc_map[d["name"]] = d  # update indexed_at
            merged_docs = list(existing_doc_map.values())
            merged_jira = existing_cf["jira"]  # managed by add/delete endpoints
        else:
            # rebuild: stamp new indexed_at on uploaded docs; re-stamp jira items
            merged_docs = new_docs
            old_jira: list = []
            try:
                async with AsyncSessionLocal() as db:
                    project_row = await db.get(Project, project_id)
                    if project_row:
                        old_jira = _parse_context_files(project_row.context_files)["jira"]
            except Exception:
                pass
            merged_jira = [
                {**j, "indexed": True, "indexed_at": now_iso} for j in old_jira
            ]

        merged_cf = {"docs": merged_docs, "jira": merged_jira}

        # built_at is set AFTER the workflow — always later than now_iso, so
        # every doc indexed in this run satisfies indexed_at < context_built_at.
        built_at = datetime.now(timezone.utc)

        # ── Persist artefacts to DB ───────────────────────────────────────────
        try:
            async with AsyncSessionLocal() as db:
                project = await db.get(Project, project_id)
                if project:
                    project.mind_map = result["mind_map"]
                    project.glossary = result["glossary"]
                    project.context_stats = result["stats"]
                    project.context_built_at = built_at
                    project.context_files = merged_cf
                    await db.commit()
                else:
                    logger.warning(
                        "Project '%s' not found in DB — artefacts not persisted.", project_id
                    )
        except Exception as db_exc:
            logger.error("Failed to persist M1 artefacts for '%s': %s", project_id, db_exc)

        # ── Write-through cache ───────────────────────────────────────────────
        _context_store[project_id] = {
            "mind_map": result["mind_map"],
            "glossary": result["glossary"],
            "stats": result["stats"],
            "context_built_at": built_at.isoformat(),
            "context_files": merged_cf,
        }

        stats = result.get("stats", {})
        logger.info(
            "M1 context build DONE — project=%s entities=%s relations=%s terms=%s docs=%s jira=%s",
            project_id,
            stats.get("entity_count", "?"),
            stats.get("relation_count", "?"),
            stats.get("term_count", "?"),
            [d["name"] for d in merged_docs],
            [j["key"] for j in merged_jira],
        )
        yield sse_event({"type": "result", "data": result})

    except Exception as exc:
        logger.error("M1 context build FAILED — project=%s error=%s", project_id, exc)
        yield sse_event({"type": "error", "data": {"message": str(exc)}})
    finally:
        yield SSE_DONE


# ── Merge helpers ─────────────────────────────────────────────────────────────

def _merge_mind_maps(existing: dict, new: dict) -> dict:
    """Merge two mind maps, deduplicating nodes by label and edges by (source, target).

    Deduplication is by label (case-insensitive) rather than id because each workflow
    run reassigns sequential ids (e1, e2, …) from scratch — id-based dedup would
    silently drop every node from an append build since e1…eN already exist.
    When a new node's label matches an existing node, its id is remapped to the
    existing node's id so that edges in the new map remain consistent.
    """
    # Build canonical label→id map from existing nodes
    label_to_id: dict[str, str] = {}
    nodes: list[dict] = []
    for n in existing.get("nodes", []):
        label_key = n.get("label", "").strip().lower()
        if label_key and label_key not in label_to_id:
            label_to_id[label_key] = n["id"]
            nodes.append(n)

    # Add new nodes; remap ids when label already exists
    id_remap: dict[str, str] = {}
    for n in new.get("nodes", []):
        label_key = n.get("label", "").strip().lower()
        if not label_key:
            continue
        if label_key in label_to_id:
            id_remap[n["id"]] = label_to_id[label_key]
        else:
            label_to_id[label_key] = n["id"]
            id_remap[n["id"]] = n["id"]
            nodes.append(n)

    # Merge edges — remap source/target using id_remap for edges from the new map
    edge_keys: set[tuple] = set()
    edges: list[dict] = []
    for e in existing.get("edges", []):
        key = (e["source"], e["target"])
        if key not in edge_keys:
            edge_keys.add(key)
            edges.append(e)
    for e in new.get("edges", []):
        src = id_remap.get(e["source"], e["source"])
        tgt = id_remap.get(e["target"], e["target"])
        key = (src, tgt)
        if key not in edge_keys:
            edge_keys.add(key)
            edges.append({**e, "source": src, "target": tgt})

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
        cf = _parse_context_files(project.context_files)
        return {
            "project_id": project_id,
            "rag_ready": rag_ready,
            "artefacts_ready": True,
            "stats": stats,
            "context_built_at": built_at,
            "document_count": len(cf["docs"]),
            "context_files": cf["docs"],
            "jira_sources": cf["jira"],
        }

    # M1 has never run for this project — Chroma may contain M2 test-file
    # vectors but those do not constitute M1 context.  Always return False.
    cache = _context_store.get(project_id, {})
    cf = _parse_context_files(cache.get("context_files"))
    return {
        "project_id": project_id,
        "rag_ready": False,
        "artefacts_ready": bool(cache),
        "stats": cache.get("stats"),
        "context_built_at": cache.get("context_built_at"),
        "document_count": len(cf["docs"]),
        "context_files": cf["docs"],
        "jira_sources": cf["jira"],
    }


# ── Mind map ──────────────────────────────────────────────────────────────────

@router.get("/{project_id}/mindmap")
async def get_mindmap(project_id: str, db: AsyncSession = Depends(get_db)):
    # 1. In-memory cache hit
    cache = _context_store.get(project_id)
    if cache:
        return cache["mind_map"]

    # 2. DB fallback
    project = await db.get(Project, project_id)
    if not project or not project.context_built_at:
        raise HTTPException(404, "Context not built yet for this project. Run /build first.")
    if not project.mind_map:
        raise HTTPException(404, "Mind map not available.")

    # Warm the cache for subsequent requests
    _context_store[project_id] = _load_project_artefacts(project)
    return _context_store[project_id]["mind_map"]


# ── Glossary ──────────────────────────────────────────────────────────────────

@router.get("/{project_id}/glossary")
async def get_glossary(project_id: str, db: AsyncSession = Depends(get_db)):
    # 1. In-memory cache hit
    cache = _context_store.get(project_id)
    if cache:
        return cache["glossary"]

    # 2. DB fallback
    project = await db.get(Project, project_id)
    if not project or not project.context_built_at:
        raise HTTPException(404, "Context not built yet for this project. Run /build first.")
    if not project.glossary:
        raise HTTPException(404, "Glossary not available.")

    _context_store[project_id] = _load_project_artefacts(project)
    return _context_store[project_id]["glossary"]


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
        "context_files": _parse_context_files(project.context_files),
    }

# ── Jira context sources ──────────────────────────────────────────────────────


@router.post("/{project_id}/jira", status_code=201)
async def add_context_jira(
    project_id: str,
    body: JiraIssueIn,
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    issue_key = body.issue_key.strip().upper()
    if not issue_key:
        raise HTTPException(400, "issue_key is required")

    # Read Jira credentials from project settings (JsonType → already a dict)
    s: dict = project.settings or {}
    jira_url = s.get("jira_url", "")
    user_email = s.get("jira_user_email", "")
    api_key = s.get("jira_api_key", "")
    if not jira_url or not api_key:
        raise HTTPException(
            400,
            "Brak konfiguracji Jira. Skonfiguruj połączenie w ustawieniach projektu.",
        )

    # Fetch issue with full depth-aware context
    client = JiraClient(jira_url=jira_url, user_email=user_email, api_key=api_key)
    data = await client.fetch_with_context(issue_key)
    if data is None:
        raise HTTPException(404, f"Issue '{issue_key}' not found in Jira.")

    # Save as markdown to disk
    jira_dir = UPLOAD_ROOT / project_id / "context" / "jira"
    jira_dir.mkdir(parents=True, exist_ok=True)
    md_path = jira_dir / f"{issue_key}.md"
    md_path.write_text(to_markdown(data), encoding="utf-8")
    file_path = str(md_path)

    # Index into M1 Chroma
    indexed = False
    try:
        await _context_builder.index_files(project_id=project_id, file_paths=[file_path])
        indexed = True
    except Exception as exc:
        logger.warning("Failed to index Jira %s into M1 context: %s", issue_key, exc)

    # Update context_files in new dict format
    cf = _parse_context_files(project.context_files)
    existing_keys = [j["key"] for j in cf["jira"]]
    now_iso = datetime.now(timezone.utc).isoformat()
    if issue_key not in existing_keys:
        cf["jira"].append({"key": issue_key, "indexed": indexed, "indexed_at": now_iso if indexed else None})
    else:
        # Re-fetch: update indexed status and timestamp
        cf["jira"] = [
            {**j, "indexed": indexed, "indexed_at": now_iso if indexed else j.get("indexed_at")}
            if j["key"] == issue_key else j
            for j in cf["jira"]
        ]
    project.context_files = cf
    await db.commit()

    # Update write-through cache
    cache = dict(_context_store.get(project_id, {}))
    cache["context_files"] = cf
    _context_store[project_id] = cache

    return {"issue_key": issue_key, "indexed": indexed, "indexed_at": now_iso if indexed else None}


@router.delete("/{project_id}/jira/{issue_key}", status_code=204)
async def delete_context_jira(
    project_id: str,
    issue_key: str,
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    key = issue_key.upper()
    cf = _parse_context_files(project.context_files)
    if key not in [j["key"] for j in cf["jira"]]:
        raise HTTPException(404, "Jira issue not found in context sources")

    cf["jira"] = [j for j in cf["jira"] if j["key"] != key]
    project.context_files = cf
    await db.commit()

    cache = dict(_context_store.get(project_id, {}))
    cache["context_files"] = cf
    _context_store[project_id] = cache

    # Delete MD file from disk
    md_path = UPLOAD_ROOT / project_id / "context" / "jira" / f"{key}.md"
    try:
        if md_path.exists():
            md_path.unlink()
    except Exception as exc:
        logger.warning("Could not delete Jira MD file from disk: %s", exc)

    # Remove from Chroma
    _context_builder.delete_file_from_index(project_id, f"{key}.md")


@router.delete("/{project_id}/docs/{filename}", status_code=204)
async def delete_context_doc(
    project_id: str,
    filename: str,
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    cf = _parse_context_files(project.context_files)
    doc_names = [d["name"] for d in cf["docs"]]
    if filename not in doc_names:
        raise HTTPException(404, "Document not found in context sources")

    # Delete the file from disk
    doc_path = UPLOAD_ROOT / project_id / "context" / filename
    try:
        if doc_path.exists():
            doc_path.unlink()
    except Exception as exc:
        logger.warning("Could not delete context doc from disk: %s", exc)

    # Remove from Chroma
    _context_builder.delete_file_from_index(project_id, filename)

    # Remove from context_files["docs"] and save to DB
    cf["docs"] = [d for d in cf["docs"] if d["name"] != filename]
    project.context_files = cf
    await db.commit()

    # Update write-through cache
    cache = dict(_context_store.get(project_id, {}))
    cache["context_files"] = cf
    _context_store[project_id] = cache