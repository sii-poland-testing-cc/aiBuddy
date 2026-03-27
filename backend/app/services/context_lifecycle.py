"""
Context lifecycle service — Phase 4 (revised with D10 visibility model).

Registers graph nodes, graph edges, and glossary terms in the ArtifactVisibility
manifest table after each M1 context build.

D10 model: one visibility row per (item × context where visible).
  - source_context_id = work_context_id (where item was CREATED)
  - visible_in_context_id = work_context_id (initially visible only at home)
  - source_origin populated from the document(s) that produced each item

Callers are responsible for calling db.commit() after bulk operations, or
this module calls commit internally when used standalone.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ArtifactAuditLog, ArtifactVersion, ArtifactVisibility

logger = logging.getLogger("ai_buddy.context_lifecycle")


async def _upsert_visibility_item(
    db: AsyncSession,
    project_id: str,
    artifact_type: str,
    artifact_item_id: str,
    work_context_id: Optional[str],
    lifecycle_status: str,
    source_origin: Optional[str],
    source_origin_type: Optional[str],
    now: datetime,
    artifact_version_id: Optional[str] = None,
) -> bool:
    """
    Upsert one ArtifactVisibility row.
    Returns True if a new row was inserted (so caller can emit audit log).
    """
    stmt = select(ArtifactVisibility).where(
        ArtifactVisibility.project_id == project_id,
        ArtifactVisibility.artifact_type == artifact_type,
        ArtifactVisibility.artifact_item_id == artifact_item_id,
        ArtifactVisibility.visible_in_context_id == work_context_id,
    )
    row: Optional[ArtifactVisibility] = (await db.execute(stmt)).scalars().first()

    if row is None:
        row = ArtifactVisibility(
            id=str(uuid.uuid4()),
            project_id=project_id,
            artifact_type=artifact_type,
            artifact_item_id=artifact_item_id,
            source_context_id=work_context_id,
            visible_in_context_id=work_context_id,
            lifecycle_status=lifecycle_status,
            artifact_version_id=artifact_version_id,
            source_origin=source_origin,
            source_origin_type=source_origin_type,
            created_at=now,
        )
        db.add(row)
        return True  # new item → caller should emit audit log
    else:
        changed = False
        if row.lifecycle_status != lifecycle_status:
            row.lifecycle_status = lifecycle_status
            changed = True
        if source_origin and row.source_origin != source_origin:
            row.source_origin = source_origin
            changed = True
        if artifact_version_id and row.artifact_version_id != artifact_version_id:
            row.artifact_version_id = artifact_version_id
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
    source_files: Optional[List[str]] = None,
) -> None:
    """
    Upsert ArtifactVisibility rows for every node and edge.
    Emits ArtifactAuditLog(event_type="created") for new items only.
    source_files: list of filenames that produced these graph items.
    """
    lifecycle_status = "draft" if work_context_id is not None else "promoted"
    now = datetime.now(timezone.utc)
    new_count = 0

    # Derive source_origin from source_files (first file, if any)
    source_origin = source_files[0] if source_files else None
    source_origin_type = "file" if source_origin else None

    for node in nodes:
        item_id = str(node.get("id") or "").strip()
        if not item_id:
            continue

        # D12: Create v1 for new nodes
        content_snapshot = {
            "id": node.get("id"),
            "label": node.get("label"),
            "type": node.get("type"),
            "description": node.get("description"),
        }
        version_id = str(uuid.uuid4())
        db.add(ArtifactVersion(
            id=version_id,
            project_id=project_id,
            artifact_type="graph_node",
            artifact_item_id=item_id,
            version_number=1,
            content_snapshot=content_snapshot,
            created_in_context_id=work_context_id,
            change_summary="initial version",
            created_by="system",
            created_at=now,
        ))

        is_new = await _upsert_visibility_item(
            db, project_id, "graph_node", item_id, work_context_id,
            lifecycle_status, source_origin, source_origin_type, now,
            artifact_version_id=version_id,
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
                    "source_origin": source_origin,
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

        # D12: Create v1 for new edges
        content_snapshot = {
            "source": edge.get("source"),
            "target": edge.get("target"),
            "label": edge.get("label"),
        }
        version_id = str(uuid.uuid4())
        db.add(ArtifactVersion(
            id=version_id,
            project_id=project_id,
            artifact_type="graph_edge",
            artifact_item_id=item_id,
            version_number=1,
            content_snapshot=content_snapshot,
            created_in_context_id=work_context_id,
            change_summary="initial version",
            created_by="system",
            created_at=now,
        ))

        is_new = await _upsert_visibility_item(
            db, project_id, "graph_edge", item_id, work_context_id,
            lifecycle_status, source_origin, source_origin_type, now,
            artifact_version_id=version_id,
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
                    "source_origin": source_origin,
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
    source_files: Optional[List[str]] = None,
) -> None:
    """
    Upsert ArtifactVisibility rows for every glossary term.
    item_id = normalized (lower-stripped) term name.
    Emits ArtifactAuditLog(event_type="created") for new items only.
    """
    lifecycle_status = "draft" if work_context_id is not None else "promoted"
    now = datetime.now(timezone.utc)
    new_count = 0

    source_origin = source_files[0] if source_files else None
    source_origin_type = "file" if source_origin else None

    for term in terms:
        raw_name = str(term.get("term") or "").strip()
        item_id = raw_name.lower()
        if not item_id:
            continue

        # D12: Create v1 for new glossary terms
        content_snapshot = {
            "term": term.get("term"),
            "definition": term.get("definition"),
            "related_terms": term.get("related_terms"),
            "source": term.get("source"),
        }
        version_id = str(uuid.uuid4())
        db.add(ArtifactVersion(
            id=version_id,
            project_id=project_id,
            artifact_type="glossary_term",
            artifact_item_id=item_id,
            version_number=1,
            content_snapshot=content_snapshot,
            created_in_context_id=work_context_id,
            change_summary="initial version",
            created_by="system",
            created_at=now,
        ))

        is_new = await _upsert_visibility_item(
            db, project_id, "glossary_term", item_id, work_context_id,
            lifecycle_status, source_origin, source_origin_type, now,
            artifact_version_id=version_id,
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
                    "source_origin": source_origin,
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
    Delete ArtifactVisibility and ArtifactVersion rows for a project (rebuild mode).
    If artifact_types is None, deletes graph_node, graph_edge, glossary_term.
    Returns the number of visibility rows deleted.
    """
    types_to_clear = artifact_types or ["graph_node", "graph_edge", "glossary_term"]

    # D12: Also wipe version rows for these artifact types
    await db.execute(
        delete(ArtifactVersion).where(
            ArtifactVersion.project_id == project_id,
            ArtifactVersion.artifact_type.in_(types_to_clear),
        )
    )

    stmt = delete(ArtifactVisibility).where(
        ArtifactVisibility.project_id == project_id,
        ArtifactVisibility.artifact_type.in_(types_to_clear),
    )
    result = await db.execute(stmt)
    await db.flush()
    count = result.rowcount
    logger.info("project=%s — cleared %d visibility rows + versions (rebuild)", project_id, count)
    return count


async def find_by_source(
    db: AsyncSession,
    project_id: str,
    source_origin: str,
    artifact_type: Optional[str] = None,
) -> List[Dict[str, str]]:
    """
    Find all artifact visibility items from a specific source file or URL.
    Returns list of {artifact_type, artifact_item_id} dicts.
    Enables: "document X deleted — which graph nodes and terms came from it?"
    """
    stmt = select(ArtifactVisibility).where(
        ArtifactVisibility.project_id == project_id,
        ArtifactVisibility.source_origin == source_origin,
    )
    if artifact_type:
        stmt = stmt.where(ArtifactVisibility.artifact_type == artifact_type)

    rows = (await db.execute(stmt)).scalars().all()
    return [
        {"artifact_type": r.artifact_type, "artifact_item_id": r.artifact_item_id}
        for r in rows
    ]
