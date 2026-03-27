"""
Requirements persistence service.

Business logic for persisting extracted requirements and gaps.
Separated from the route layer so it can be tested and reused independently.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ArtifactAuditLog, ArtifactVersion, ArtifactVisibility, Project
from app.db.requirements_models import Requirement

logger = logging.getLogger("ai_buddy.requirements_service")


def _derive_source_origin(req_data: Dict) -> tuple[Optional[str], Optional[str]]:
    """
    Derive source_origin and source_origin_type from source_references.
    Takes the first source reference if available.
    """
    refs = req_data.get("source_references") or []
    if not refs:
        return None, None
    first_ref = str(refs[0]).strip()
    if not first_ref:
        return None, None
    # Heuristic: URLs start with http(s), everything else is a file
    if first_ref.startswith("http://") or first_ref.startswith("https://"):
        return first_ref, "url"
    return first_ref, "file"


async def persist_requirements(
    db: AsyncSession,
    project_id: str,
    flat_reqs: List[Dict],
) -> None:
    """
    Persist extracted requirements to DB.
    Wipes existing requirements for this project first (full re-extract).
    Also wipes related artifact_visibility rows for requirements.
    Emits one ArtifactAuditLog row per requirement on insert.
    Creates one ArtifactVisibility "home" row per requirement.
    """
    # Wipe existing requirements, their visibility rows, and version rows
    await db.execute(
        delete(ArtifactVisibility).where(
            ArtifactVisibility.project_id == project_id,
            ArtifactVisibility.artifact_type == "requirement",
        )
    )
    await db.execute(
        delete(ArtifactVersion).where(
            ArtifactVersion.project_id == project_id,
            ArtifactVersion.artifact_type == "requirement",
        )
    )
    await db.execute(
        delete(Requirement).where(Requirement.project_id == project_id)
    )
    await db.flush()

    now = datetime.now(timezone.utc)
    for req_data in flat_reqs:
        work_context_id = req_data.get("work_context_id")
        lifecycle_status = req_data.get("lifecycle_status", "promoted")
        source_origin, source_origin_type = _derive_source_origin(req_data)

        req = Requirement(
            id=req_data["id"],
            project_id=project_id,
            parent_id=req_data.get("parent_id"),
            level=req_data.get("level", "functional_req"),
            external_id=req_data.get("external_id"),
            title=req_data["title"],
            description=req_data.get("description", ""),
            source_type=req_data.get("source_type", "implicit"),
            source_references=req_data.get("source_references"),
            taxonomy=req_data.get("taxonomy"),
            completeness_score=req_data.get("completeness_score"),
            confidence=req_data.get("confidence"),
            human_reviewed=False,
            needs_review=req_data.get("needs_review", False),
            review_reason=req_data.get("review_reason"),
            work_context_id=work_context_id,
            lifecycle_status=lifecycle_status,
            source_origin=source_origin,
            source_origin_type=source_origin_type,
        )
        db.add(req)

        # D12: Create v1 for this requirement
        content_snapshot = {
            "id": req_data["id"],
            "title": req_data["title"],
            "description": req_data.get("description", ""),
            "level": req_data.get("level", "functional_req"),
            "external_id": req_data.get("external_id"),
            "source_type": req_data.get("source_type", "implicit"),
            "source_references": req_data.get("source_references"),
            "taxonomy": req_data.get("taxonomy"),
            "confidence": req_data.get("confidence"),
            "completeness_score": req_data.get("completeness_score"),
        }
        version_id = str(uuid.uuid4())
        db.add(ArtifactVersion(
            id=version_id,
            project_id=project_id,
            artifact_type="requirement",
            artifact_item_id=req_data["id"],
            version_number=1,
            content_snapshot=content_snapshot,
            created_in_context_id=work_context_id,
            change_summary="initial version",
            created_by="system",
            created_at=now,
        ))

        # "Home" visibility row: item is visible where it was created
        db.add(ArtifactVisibility(
            id=str(uuid.uuid4()),
            project_id=project_id,
            artifact_type="requirement",
            artifact_item_id=req_data["id"],
            source_context_id=work_context_id,
            visible_in_context_id=work_context_id,
            lifecycle_status=lifecycle_status,
            artifact_version_id=version_id,
            source_origin=source_origin,
            source_origin_type=source_origin_type,
            created_at=now,
        ))

        # Append-only audit log entry
        db.add(ArtifactAuditLog(
            id=str(uuid.uuid4()),
            project_id=project_id,
            artifact_type="requirement",
            artifact_item_id=req_data["id"],
            event_type="created",
            work_context_id=work_context_id,
            new_value={
                "title": req_data["title"],
                "level": req_data.get("level", "functional_req"),
                "lifecycle_status": lifecycle_status,
                "source_origin": source_origin,
            },
            actor="system",
            created_at=now,
        ))

    await db.commit()
    logger.info("project=%s — persisted %d requirements", project_id, len(flat_reqs))


async def find_by_source(
    db: AsyncSession,
    project_id: str,
    source_origin: str,
) -> List[Requirement]:
    """
    Find all requirements extracted from a specific source file or URL.
    Useful for: "file X was deleted — which requirements came from it?"
    """
    stmt = select(Requirement).where(
        Requirement.project_id == project_id,
        Requirement.source_origin == source_origin,
    )
    return list((await db.execute(stmt)).scalars().all())


async def persist_gaps(
    db: AsyncSession,
    project_id: str,
    gaps: List[Dict],
) -> None:
    """Persist requirement gaps to the dedicated Project.requirement_gaps column."""
    project = await db.get(Project, project_id)
    if project:
        project.requirement_gaps = gaps
        await db.commit()
