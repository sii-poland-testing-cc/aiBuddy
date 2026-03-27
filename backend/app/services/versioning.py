"""
Versioning service — immutable artifact version history (D12).

Every edit creates a new version — never overwrites.  Visibility rows in the
home context (source_context_id == visible_in_context_id) are updated to point
to the latest version.  Visibility rows in OTHER contexts stay pinned to their
promotion-time version.

Public API:
  create_version()        — creates a new version, returns it
  get_current_version()   — latest version for an item
  get_version()           — specific version by id
  list_versions()         — full history (newest first)
  get_version_diff()      — field-level diff between two versions
  update_home_visibility_version() — point home row at a new version
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ArtifactVersion, ArtifactVisibility

logger = logging.getLogger("ai_buddy.versioning")


async def create_version(
    db: AsyncSession,
    project_id: str,
    artifact_type: str,
    artifact_item_id: str,
    content_snapshot: Dict[str, Any],
    context_id: Optional[str] = None,
    change_summary: Optional[str] = None,
    created_by: str = "system",
) -> ArtifactVersion:
    """
    Create a new immutable version for an artifact item.

    Determines next version_number (MAX + 1 for this item, or 1 if first).
    Returns the newly created ArtifactVersion (not yet committed — caller
    controls the transaction boundary).
    """
    # Determine next version number
    stmt = select(func.max(ArtifactVersion.version_number)).where(
        ArtifactVersion.project_id == project_id,
        ArtifactVersion.artifact_type == artifact_type,
        ArtifactVersion.artifact_item_id == artifact_item_id,
    )
    result = await db.execute(stmt)
    max_ver = result.scalar()
    next_ver = (max_ver or 0) + 1

    version = ArtifactVersion(
        id=str(uuid.uuid4()),
        project_id=project_id,
        artifact_type=artifact_type,
        artifact_item_id=artifact_item_id,
        version_number=next_ver,
        content_snapshot=content_snapshot,
        created_in_context_id=context_id,
        change_summary=change_summary,
        created_by=created_by,
        created_at=datetime.now(timezone.utc),
    )
    db.add(version)
    await db.flush()  # assign PK before caller references version.id

    logger.debug(
        "project=%s type=%s item=%s → v%d (id=%s)",
        project_id, artifact_type, artifact_item_id, next_ver, version.id,
    )
    return version


async def get_current_version(
    db: AsyncSession,
    project_id: str,
    artifact_type: str,
    artifact_item_id: str,
) -> Optional[ArtifactVersion]:
    """Return the latest version for an item, or None if no versions exist."""
    stmt = (
        select(ArtifactVersion)
        .where(
            ArtifactVersion.project_id == project_id,
            ArtifactVersion.artifact_type == artifact_type,
            ArtifactVersion.artifact_item_id == artifact_item_id,
        )
        .order_by(ArtifactVersion.version_number.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def get_version(
    db: AsyncSession,
    version_id: str,
) -> Optional[ArtifactVersion]:
    """Return a specific version by its id."""
    return await db.get(ArtifactVersion, version_id)


async def list_versions(
    db: AsyncSession,
    project_id: str,
    artifact_type: str,
    artifact_item_id: str,
) -> List[ArtifactVersion]:
    """Return full version history for an item, newest first."""
    stmt = (
        select(ArtifactVersion)
        .where(
            ArtifactVersion.project_id == project_id,
            ArtifactVersion.artifact_type == artifact_type,
            ArtifactVersion.artifact_item_id == artifact_item_id,
        )
        .order_by(ArtifactVersion.version_number.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


def get_version_diff(
    version_a: ArtifactVersion,
    version_b: ArtifactVersion,
) -> Dict[str, Any]:
    """
    Field-level comparison of two content_snapshots.

    Returns:
      {
        "version_a": { "id": ..., "version_number": ... },
        "version_b": { "id": ..., "version_number": ... },
        "changed_fields": { "title": { "old": "X", "new": "Y" }, ... },
        "added_fields": { "new_field": "value", ... },
        "removed_fields": { "old_field": "value", ... },
      }
    """
    snap_a = version_a.content_snapshot or {}
    snap_b = version_b.content_snapshot or {}

    all_keys = set(snap_a.keys()) | set(snap_b.keys())
    changed: Dict[str, Dict[str, Any]] = {}
    added: Dict[str, Any] = {}
    removed: Dict[str, Any] = {}

    for key in all_keys:
        in_a = key in snap_a
        in_b = key in snap_b
        if in_a and in_b:
            if _normalize(snap_a[key]) != _normalize(snap_b[key]):
                changed[key] = {"old": snap_a[key], "new": snap_b[key]}
        elif in_b and not in_a:
            added[key] = snap_b[key]
        elif in_a and not in_b:
            removed[key] = snap_a[key]

    return {
        "version_a": {"id": version_a.id, "version_number": version_a.version_number},
        "version_b": {"id": version_b.id, "version_number": version_b.version_number},
        "changed_fields": changed,
        "added_fields": added,
        "removed_fields": removed,
    }


def _normalize(val: Any) -> Any:
    """Normalize for comparison: convert JSON-like strings to dicts/lists."""
    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            pass
    return val


async def update_home_visibility_version(
    db: AsyncSession,
    project_id: str,
    artifact_type: str,
    artifact_item_id: str,
    version_id: str,
) -> int:
    """
    Update the HOME visibility row (where source_context_id == visible_in_context_id)
    to point to the given version.  Non-home rows (promoted references) are NOT touched.

    Returns the number of rows updated (0 or 1).
    """
    stmt = select(ArtifactVisibility).where(
        ArtifactVisibility.project_id == project_id,
        ArtifactVisibility.artifact_type == artifact_type,
        ArtifactVisibility.artifact_item_id == artifact_item_id,
        # Home row: visible where created (or both NULL for legacy data)
        and_(
            ArtifactVisibility.source_context_id == ArtifactVisibility.visible_in_context_id,
        ),
    )
    result = await db.execute(stmt)
    rows = list(result.scalars().all())

    updated = 0
    now = datetime.now(timezone.utc)
    for row in rows:
        row.artifact_version_id = version_id
        row.updated_at = now
        updated += 1

    if updated:
        await db.flush()
    return updated


async def create_version_and_update_home(
    db: AsyncSession,
    project_id: str,
    artifact_type: str,
    artifact_item_id: str,
    content_snapshot: Dict[str, Any],
    context_id: Optional[str] = None,
    change_summary: Optional[str] = None,
    created_by: str = "system",
) -> ArtifactVersion:
    """
    Convenience: create a new version AND update the home visibility row
    to point to it.  Does NOT commit — caller manages the transaction.
    """
    version = await create_version(
        db, project_id, artifact_type, artifact_item_id,
        content_snapshot, context_id, change_summary, created_by,
    )
    await update_home_visibility_version(
        db, project_id, artifact_type, artifact_item_id, version.id,
    )
    return version
