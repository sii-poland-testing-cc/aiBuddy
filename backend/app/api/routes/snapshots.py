"""
Audit Snapshots read API
========================
Endpoints to retrieve and manage per-project audit history.
"""

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import AuditSnapshot

logger = logging.getLogger("ai_buddy.snapshots")

router = APIRouter()


def _parse_snapshot(snap: AuditSnapshot) -> Dict[str, Any]:
    return {
        "id": snap.id,
        "created_at": snap.created_at.isoformat(),
        "files_used": snap.files_used or [],
        "summary": snap.summary or {},
        "requirements_uncovered": snap.requirements_uncovered or [],
        "recommendations": snap.recommendations or [],
        "diff": snap.diff,
    }


@router.get("/{project_id}")
async def list_snapshots(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> List[Dict[str, Any]]:
    """Return last 5 snapshots for a project, newest first."""
    stmt = (
        select(AuditSnapshot)
        .where(AuditSnapshot.project_id == project_id)
        .order_by(AuditSnapshot.created_at.desc())
        .limit(5)
    )
    rows = list((await db.execute(stmt)).scalars().all())
    return [_parse_snapshot(s) for s in rows]


@router.get("/{project_id}/trend")
async def get_trend(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Return aggregated trend data (oldest → newest) for charts.
    Shape: {labels, coverage, duplicates, requirements_covered, requirements_total}
    """
    stmt = (
        select(AuditSnapshot)
        .where(AuditSnapshot.project_id == project_id)
        .order_by(AuditSnapshot.created_at.asc())
        .limit(5)
    )
    rows = list((await db.execute(stmt)).scalars().all())

    labels: List[str] = []
    coverage: List[float] = []
    duplicates: List[int] = []
    requirements_covered: List[int] = []
    requirements_total: List[int] = []

    for snap in rows:
        labels.append(snap.created_at.isoformat())
        summary = snap.summary or {}
        coverage.append(summary.get("coverage_pct", 0.0))
        duplicates.append(summary.get("duplicates_found", 0))
        requirements_covered.append(summary.get("requirements_covered", 0))
        requirements_total.append(summary.get("requirements_total", 0))

    return {
        "labels": labels,
        "coverage": coverage,
        "duplicates": duplicates,
        "requirements_covered": requirements_covered,
        "requirements_total": requirements_total,
    }


@router.get("/{project_id}/latest")
async def get_latest(
    project_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Return the most recent snapshot or 404 if none exist."""
    stmt = (
        select(AuditSnapshot)
        .where(AuditSnapshot.project_id == project_id)
        .order_by(AuditSnapshot.created_at.desc())
        .limit(1)
    )
    snap = (await db.execute(stmt)).scalars().first()

    if snap is None:
        raise HTTPException(status_code=404, detail="No snapshots found for this project")

    return _parse_snapshot(snap)


@router.delete("/{project_id}/{snapshot_id}", status_code=204)
async def delete_snapshot(
    project_id: str,
    snapshot_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a specific snapshot. Returns 404 if not found or belongs to a different project."""
    stmt = select(AuditSnapshot).where(AuditSnapshot.id == snapshot_id)
    snap = (await db.execute(stmt)).scalars().first()

    if snap is None or snap.project_id != project_id:
        raise HTTPException(status_code=404, detail="Snapshot not found")

    await db.delete(snap)
    await db.commit()
