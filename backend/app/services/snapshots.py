"""
Audit snapshot service.

Business logic for creating, diffing, and pruning AuditSnapshot records.
Separated from the route layer so it can be tested and reused independently.
"""

import json
import logging
from pathlib import Path
from typing import List

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditSnapshot, ProjectFile

logger = logging.getLogger("ai_buddy.snapshots")


async def save_snapshot(
    project_id: str,
    result: dict,
    files_used: List[str],
    db: AsyncSession,
) -> str:
    """
    Persist an audit result as an AuditSnapshot.

    - Computes diff against the most recent previous snapshot.
    - Enforces max 5 snapshots per project (deletes oldest if exceeded).
    - Updates ProjectFile.last_used_in_audit_id for all files in the audit.

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
        prev_summary   = json.loads(previous.summary or "{}")
        prev_uncovered = set(json.loads(previous.requirements_uncovered or "[]"))
        curr_uncovered = set(requirements_uncovered)
        prev_files     = set(json.loads(previous.files_used or "[]"))
        curr_files     = set(files_used)

        diff = {
            "coverage_delta": round(
                summary.get("coverage_pct", 0) - prev_summary.get("coverage_pct", 0), 1
            ),
            "duplicates_delta": (
                summary.get("duplicates_found", 0) - prev_summary.get("duplicates_found", 0)
            ),
            "new_covered":     list(prev_uncovered - curr_uncovered),
            "newly_uncovered": list(curr_uncovered - prev_uncovered),
            "files_added":     list(curr_files - prev_files),
            "files_removed":   list(prev_files - curr_files),
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
