"""
Version info API — exposes artifact version history and drift detection.

Endpoints:
  GET /api/versions/{project_id}/{artifact_type}/{item_id}
    Returns version history + pinned-vs-current info for a specific item in a context.

  GET /api/versions/{project_id}/drift?context_id=X
    Batch: returns all items in a context where pinned version != current version.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import ArtifactVersion, ArtifactVisibility
from app.services.versioning import list_versions

logger = logging.getLogger("ai_buddy.versions")

router = APIRouter()


@router.get("/{project_id}/{artifact_type}/{item_id}")
async def get_item_version_info(
    project_id: str,
    artifact_type: str,
    item_id: str,
    context_id: Optional[str] = Query(None, description="Context to check pinned version"),
    db: AsyncSession = Depends(get_db),
):
    """
    Return version history for an artifact item, plus pinned version in
    the given context (if context_id provided).
    """
    versions = await list_versions(db, project_id, artifact_type, item_id)

    pinned_version_number: Optional[int] = None
    if context_id:
        stmt = (
            select(ArtifactVersion.version_number)
            .join(
                ArtifactVisibility,
                ArtifactVisibility.artifact_version_id == ArtifactVersion.id,
            )
            .where(
                ArtifactVisibility.project_id == project_id,
                ArtifactVisibility.artifact_type == artifact_type,
                ArtifactVisibility.artifact_item_id == item_id,
                ArtifactVisibility.visible_in_context_id == context_id,
                ArtifactVisibility.lifecycle_status != "superseded",
            )
        )
        result = await db.execute(stmt)
        pinned_version_number = result.scalar()

    current = versions[0] if versions else None

    return {
        "project_id": project_id,
        "artifact_type": artifact_type,
        "item_id": item_id,
        "current_version": current.version_number if current else None,
        "pinned_version": pinned_version_number,
        "has_newer": (
            pinned_version_number is not None
            and current is not None
            and pinned_version_number < current.version_number
        ),
        "versions": [
            {
                "version_number": v.version_number,
                "change_summary": v.change_summary,
                "created_by": v.created_by,
                "created_at": v.created_at.isoformat() if v.created_at else None,
                "created_in_context_id": v.created_in_context_id,
            }
            for v in versions
        ],
    }


@router.get("/{project_id}/drift")
async def get_version_drift(
    project_id: str,
    context_id: str = Query(..., description="Context to check for version drift"),
    db: AsyncSession = Depends(get_db),
):
    """
    Batch: find all items in a context where pinned version < current version.
    Returns a map of `{artifact_type}:{item_id}` → drift info.
    """
    # Get all visibility rows in this context that have a pinned version
    vis_stmt = (
        select(
            ArtifactVisibility.artifact_type,
            ArtifactVisibility.artifact_item_id,
            ArtifactVersion.version_number.label("pinned_version"),
        )
        .join(
            ArtifactVersion,
            ArtifactVisibility.artifact_version_id == ArtifactVersion.id,
        )
        .where(
            ArtifactVisibility.project_id == project_id,
            ArtifactVisibility.visible_in_context_id == context_id,
            ArtifactVisibility.lifecycle_status != "superseded",
            ArtifactVisibility.artifact_version_id.isnot(None),
        )
    )
    pinned_rows = (await db.execute(vis_stmt)).all()

    if not pinned_rows:
        return {"project_id": project_id, "context_id": context_id, "drift": {}}

    # Get current (max) version for each item
    # Build subquery for max version per item
    max_ver_stmt = (
        select(
            ArtifactVersion.artifact_type,
            ArtifactVersion.artifact_item_id,
            func.max(ArtifactVersion.version_number).label("current_version"),
        )
        .where(ArtifactVersion.project_id == project_id)
        .group_by(ArtifactVersion.artifact_type, ArtifactVersion.artifact_item_id)
    )
    current_rows = (await db.execute(max_ver_stmt)).all()
    current_map = {(r.artifact_type, r.artifact_item_id): r.current_version for r in current_rows}

    drift = {}
    for row in pinned_rows:
        key = f"{row.artifact_type}:{row.artifact_item_id}"
        current_ver = current_map.get((row.artifact_type, row.artifact_item_id))
        if current_ver and current_ver > row.pinned_version:
            drift[key] = {
                "artifact_type": row.artifact_type,
                "item_id": row.artifact_item_id,
                "pinned_version": row.pinned_version,
                "current_version": current_ver,
            }

    return {"project_id": project_id, "context_id": context_id, "drift": drift}
