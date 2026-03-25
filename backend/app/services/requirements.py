"""
Requirements persistence service.

Business logic for persisting extracted requirements and gaps.
Separated from the route layer so it can be tested and reused independently.
"""

import json
import logging
from typing import Dict, List

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Project
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
    """
    await db.execute(
        delete(Requirement).where(Requirement.project_id == project_id)
    )
    await db.flush()

    for req_data in flat_reqs:
        req = Requirement(
            id=req_data["id"],
            project_id=project_id,
            parent_id=req_data.get("parent_id"),
            level=req_data.get("level", "functional_req"),
            external_id=req_data.get("external_id"),
            title=req_data["title"],
            description=req_data.get("description", ""),
            source_type=req_data.get("source_type", "implicit"),
            source_references=None,
            taxonomy=req_data.get("taxonomy"),
            completeness_score=req_data.get("completeness_score"),
            confidence=req_data.get("confidence"),
            human_reviewed=False,
            needs_review=req_data.get("needs_review", False),
            review_reason=req_data.get("review_reason"),
        )
        db.add(req)

    await db.commit()
    logger.info("project=%s — persisted %d requirements", project_id, len(flat_reqs))


async def persist_gaps(
    db: AsyncSession,
    project_id: str,
    gaps: List[Dict],
) -> None:
    """Persist requirement gaps as a JSON field on the Project.context_stats column."""
    project = await db.get(Project, project_id)
    if project:
        existing_stats = json.loads(project.context_stats or "{}") if project.context_stats else {}
        existing_stats["requirement_gaps"] = gaps
        project.context_stats = json.dumps(existing_stats, ensure_ascii=False)
        await db.commit()
