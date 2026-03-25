"""
Mapping and coverage persistence service.

Business logic for persisting requirement↔TC mappings and coverage scores.
Separated from the route layer so it can be tested and reused independently.
"""

import json
import logging
from typing import Dict, List

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.requirements_models import CoverageScore, RequirementTCMapping

logger = logging.getLogger("ai_buddy.mapping_service")


async def persist_mappings(
    db: AsyncSession,
    project_id: str,
    mappings: List[Dict],
) -> None:
    """Persist mapping results. Wipes previous mappings for this project."""
    await db.execute(
        delete(RequirementTCMapping).where(RequirementTCMapping.project_id == project_id)
    )
    await db.flush()

    for m in mappings:
        row = RequirementTCMapping(
            project_id=project_id,
            requirement_id=m["requirement_id"],
            tc_source_file=m.get("tc_source_file", "unknown"),
            tc_identifier=m.get("tc_identifier", "unknown"),
            mapping_confidence=m.get("mapping_confidence", 0.5),
            mapping_method=m.get("mapping_method", "embedding"),
            coverage_aspects=json.dumps(m.get("coverage_aspects", [])),
            human_verified=False,
        )
        db.add(row)

    await db.commit()
    logger.info("project=%s — persisted %d mappings", project_id, len(mappings))


async def persist_scores(
    db: AsyncSession,
    project_id: str,
    scores: List[Dict],
) -> None:
    """Persist coverage scores. Wipes previous scores for this project (no snapshot link in MVP)."""
    await db.execute(
        delete(CoverageScore).where(CoverageScore.project_id == project_id)
    )
    await db.flush()

    for s in scores:
        row = CoverageScore(
            project_id=project_id,
            requirement_id=s["requirement_id"],
            snapshot_id=None,  # linked to audit snapshot in future
            total_score=s.get("total_score", 0),
            base_coverage=s.get("base_coverage", 0),
            depth_coverage=s.get("depth_coverage", 0),
            quality_weight=s.get("quality_weight", 0),
            confidence_penalty=s.get("confidence_penalty", 0),
            crossref_bonus=s.get("crossref_bonus", 0),
            matched_tc_count=s.get("matched_tc_count", 0),
            coverage_aspects_present=json.dumps(s.get("coverage_aspects_present", [])),
            coverage_aspects_missing=json.dumps(s.get("coverage_aspects_missing", [])),
        )
        db.add(row)

    await db.commit()
    logger.info("project=%s — persisted %d coverage scores", project_id, len(scores))
