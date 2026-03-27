"""
Artifact visibility API — cross-type artifact queries.

Endpoints:
  GET /api/artifacts/{project_id}/by-source?source_origin=filename.pdf
    Returns all items from a given source across all artifact types.
    Enables the "source file deleted — what's affected?" workflow.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import ArtifactVisibility

logger = logging.getLogger("ai_buddy.artifacts")

router = APIRouter()


@router.get("/{project_id}/by-source")
async def artifacts_by_source(
    project_id: str,
    source_origin: str = Query(..., description="Source file or URL to search for"),
    artifact_type: Optional[str] = Query(None, description="Filter by artifact type"),
    db: AsyncSession = Depends(get_db),
):
    """
    Find all artifact visibility items from a specific source file or URL.

    Returns items across all artifact types (graph_node, graph_edge,
    glossary_term, requirement) that were produced from the given source.
    Enables: "document X deleted — which items came from it?"
    """
    stmt = select(ArtifactVisibility).where(
        ArtifactVisibility.project_id == project_id,
        ArtifactVisibility.source_origin == source_origin,
    )
    if artifact_type:
        stmt = stmt.where(ArtifactVisibility.artifact_type == artifact_type)

    rows = (await db.execute(stmt)).scalars().all()

    items = []
    for r in rows:
        items.append({
            "id": r.id,
            "artifact_type": r.artifact_type,
            "artifact_item_id": r.artifact_item_id,
            "source_context_id": r.source_context_id,
            "visible_in_context_id": r.visible_in_context_id,
            "lifecycle_status": r.lifecycle_status,
            "source_origin": r.source_origin,
            "source_origin_type": r.source_origin_type,
            "sibling_of": r.sibling_of,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    # Group by artifact_type for convenience
    by_type: dict = {}
    for item in items:
        by_type.setdefault(item["artifact_type"], []).append(item)

    return {
        "project_id": project_id,
        "source_origin": source_origin,
        "total": len(items),
        "items": items,
        "by_type": by_type,
    }
