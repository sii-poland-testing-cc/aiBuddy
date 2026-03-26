"""
Requirements persistence service.

Business logic for persisting extracted requirements and gaps.
Separated from the route layer so it can be tested and reused independently.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ArtifactAuditLog, Project
from app.db.requirements_models import Requirement

logger = logging.getLogger("ai_buddy.requirements_service")


async def persist_requirements(
    db: AsyncSession,
    project_id: str,
    flat_reqs: List[Dict],
) -> None:
    """
    Persist extracted requirements to DB.
    Wipes existing requirements for this project first (full re-extract).
    Emits one ArtifactAuditLog row per requirement on insert.
    """
    await db.execute(
        delete(Requirement).where(Requirement.project_id == project_id)
    )
    await db.flush()

    now = datetime.now(timezone.utc)
    for req_data in flat_reqs:
        work_context_id = req_data.get("work_context_id")
        lifecycle_status = req_data.get("lifecycle_status", "promoted")
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
        )
        db.add(req)

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
            },
            actor="system",
            created_at=now,
        ))

    await db.commit()
    logger.info("project=%s — persisted %d requirements", project_id, len(flat_reqs))


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
