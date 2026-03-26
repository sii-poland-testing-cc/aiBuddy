"""
Context lifecycle service — Phase 4.

Registers graph nodes, graph edges, and glossary terms in the ArtifactLifecycle
manifest table after each M1 context build.

Upsert semantics:
  - New item:      INSERT row + emit ArtifactAuditLog(event_type="created")
  - Existing item: UPDATE work_context_id / lifecycle_status if changed;
                   no audit log for pure no-ops.

Callers are responsible for calling db.commit() after bulk operations, or
this module calls commit internally when used standalone.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ArtifactAuditLog, ArtifactLifecycle

logger = logging.getLogger("ai_buddy.context_lifecycle")


async def _upsert_manifest_item(
    db: AsyncSession,
    project_id: str,
    artifact_type: str,
    artifact_item_id: str,
    work_context_id: Optional[str],
    lifecycle_status: str,
    now: datetime,
) -> bool:
    """
    Upsert one ArtifactLifecycle row.
    Returns True if a new row was inserted (so caller can emit audit log).
    """
    stmt = select(ArtifactLifecycle).where(
        ArtifactLifecycle.project_id == project_id,
        ArtifactLifecycle.artifact_type == artifact_type,
        ArtifactLifecycle.artifact_item_id == artifact_item_id,
    )
    row: Optional[ArtifactLifecycle] = (await db.execute(stmt)).scalars().first()

    if row is None:
        row = ArtifactLifecycle(
            id=str(uuid.uuid4()),
            project_id=project_id,
            artifact_type=artifact_type,
            artifact_item_id=artifact_item_id,
            work_context_id=work_context_id,
            lifecycle_status=lifecycle_status,
            created_at=now,
        )
        db.add(row)
        return True  # new item → caller should emit audit log
    else:
        changed = False
        if work_context_id is not None and row.work_context_id != work_context_id:
            row.work_context_id = work_context_id
            changed = True
        if row.lifecycle_status != lifecycle_status:
            row.lifecycle_status = lifecycle_status
            changed = True
        if changed:
            row.updated_at = now
        return False  # existing item → no audit log


async def register_graph_items(
    db: AsyncSession,
    project_id: str,
    work_context_id: Optional[str],
    nodes: List[Dict[str, Any]],
    edges: List[Dict[str, Any]],
) -> None:
    """
    Upsert ArtifactLifecycle rows for every node and edge.
    Emits ArtifactAuditLog(event_type="created") for new items only.
    """
    lifecycle_status = "draft" if work_context_id is not None else "promoted"
    now = datetime.now(timezone.utc)
    new_count = 0

    for node in nodes:
        item_id = str(node.get("id") or "").strip()
        if not item_id:
            continue
        is_new = await _upsert_manifest_item(
            db, project_id, "graph_node", item_id, work_context_id, lifecycle_status, now
        )
        if is_new:
            db.add(ArtifactAuditLog(
                id=str(uuid.uuid4()),
                project_id=project_id,
                artifact_type="graph_node",
                artifact_item_id=item_id,
                event_type="created",
                work_context_id=work_context_id,
                new_value={
                    "label": node.get("label"),
                    "type": node.get("type"),
                    "lifecycle_status": lifecycle_status,
                },
                actor="system",
                created_at=now,
            ))
            new_count += 1

    for edge in edges:
        src = str(edge.get("source") or "").strip()
        tgt = str(edge.get("target") or "").strip()
        if not src or not tgt:
            continue
        item_id = f"{src}→{tgt}"
        is_new = await _upsert_manifest_item(
            db, project_id, "graph_edge", item_id, work_context_id, lifecycle_status, now
        )
        if is_new:
            db.add(ArtifactAuditLog(
                id=str(uuid.uuid4()),
                project_id=project_id,
                artifact_type="graph_edge",
                artifact_item_id=item_id,
                event_type="created",
                work_context_id=work_context_id,
                new_value={
                    "label": edge.get("label"),
                    "lifecycle_status": lifecycle_status,
                },
                actor="system",
                created_at=now,
            ))
            new_count += 1

    await db.commit()
    logger.info(
        "project=%s — registered %d new graph items (nodes=%d edges=%d total_new=%d)",
        project_id, new_count, len(nodes), len(edges), new_count,
    )


async def register_glossary_items(
    db: AsyncSession,
    project_id: str,
    work_context_id: Optional[str],
    terms: List[Dict[str, Any]],
) -> None:
    """
    Upsert ArtifactLifecycle rows for every glossary term.
    item_id = normalized (lower-stripped) term name.
    Emits ArtifactAuditLog(event_type="created") for new items only.
    """
    lifecycle_status = "draft" if work_context_id is not None else "promoted"
    now = datetime.now(timezone.utc)
    new_count = 0

    for term in terms:
        raw_name = str(term.get("term") or "").strip()
        item_id = raw_name.lower()
        if not item_id:
            continue
        is_new = await _upsert_manifest_item(
            db, project_id, "glossary_term", item_id, work_context_id, lifecycle_status, now
        )
        if is_new:
            db.add(ArtifactAuditLog(
                id=str(uuid.uuid4()),
                project_id=project_id,
                artifact_type="glossary_term",
                artifact_item_id=item_id,
                event_type="created",
                work_context_id=work_context_id,
                new_value={
                    "term": raw_name,
                    "lifecycle_status": lifecycle_status,
                },
                actor="system",
                created_at=now,
            ))
            new_count += 1

    await db.commit()
    logger.info(
        "project=%s — registered %d new glossary terms (total=%d new=%d)",
        project_id, new_count, len(terms), new_count,
    )


async def clear_manifest_for_project(
    db: AsyncSession,
    project_id: str,
    artifact_types: Optional[List[str]] = None,
) -> int:
    """
    Delete ArtifactLifecycle rows for a project (used in rebuild mode).
    If artifact_types is None, deletes all types (graph_node, graph_edge, glossary_term).
    Returns the number of rows deleted.
    """
    types_to_clear = artifact_types or ["graph_node", "graph_edge", "glossary_term"]
    stmt = delete(ArtifactLifecycle).where(
        ArtifactLifecycle.project_id == project_id,
        ArtifactLifecycle.artifact_type.in_(types_to_clear),
    )
    result = await db.execute(stmt)
    await db.flush()
    count = result.rowcount
    logger.info("project=%s — cleared %d manifest rows (rebuild)", project_id, count)
    return count
