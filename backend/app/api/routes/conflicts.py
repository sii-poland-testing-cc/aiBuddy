"""
Conflicts API — Phase 6.

Human-facing endpoints for reviewing and resolving pending promotion conflicts.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.db.models import ArtifactAuditLog, PromotionConflict, WorkContext
from app.lifecycle.conflict_service import count_pending_conflicts, get_pending_conflicts
from app.lifecycle.glossary_adapter import GlossaryAdapter
from app.lifecycle.graph_adapter import GraphEdgeAdapter, GraphNodeAdapter
from app.lifecycle.promotion_service import PromotionService
from app.lifecycle.requirements_adapter import RequirementsAdapter

router = APIRouter()

# ─── Resolution mapping ───────────────────────────────────────────────────────

_RESOLUTION_MAP = {
    "accept_new": "use_incoming",
    "keep_old": "keep_existing",
    "edited": "merge",
    # "defer" handled separately
}
VALID_RESOLUTIONS = {"accept_new", "keep_old", "edited", "defer"}

_ADAPTER_MAP = {
    "graph_node": GraphNodeAdapter,
    "graph_edge": GraphEdgeAdapter,
    "glossary_term": GlossaryAdapter,
    "requirement": RequirementsAdapter,
}

# ─── Pydantic schemas for "edited" validation ─────────────────────────────────


class _GraphNodeValue(BaseModel):
    id: str
    label: str


class _GraphEdgeValue(BaseModel):
    source: str
    target: str


class _GlossaryTermValue(BaseModel):
    term: str
    definition: str


class _RequirementValue(BaseModel):
    id: str
    title: str


_EDITED_SCHEMAS: dict[str, type[BaseModel]] = {
    "graph_node": _GraphNodeValue,
    "graph_edge": _GraphEdgeValue,
    "glossary_term": _GlossaryTermValue,
    "requirement": _RequirementValue,
}

# ─── Request / response models ────────────────────────────────────────────────


class ResolveRequest(BaseModel):
    resolution: str  # "accept_new" | "keep_old" | "edited" | "defer"
    resolved_value: Optional[dict[str, Any]] = None
    note: Optional[str] = None


def _conflict_to_dict(c: PromotionConflict) -> dict[str, Any]:
    return {
        "id": c.id,
        "project_id": c.project_id,
        "artifact_type": c.artifact_type,
        "artifact_item_id": c.artifact_item_id,
        "source_context_id": c.source_context_id,
        "target_context_id": c.target_context_id,
        "incoming_value": c.incoming_value,
        "existing_value": c.existing_value,
        "conflict_reason": c.conflict_reason,
        "status": c.status,
        "resolved_at": c.resolved_at.isoformat() if c.resolved_at else None,
        "resolved_by": c.resolved_by,
        "resolution_value": c.resolution_value,
        "created_at": c.created_at.isoformat(),
    }


# ─── GET /{project_id} ────────────────────────────────────────────────────────


@router.get("/{project_id}")
async def list_conflicts(
    project_id: str,
    artifact_type: Optional[str] = None,
    context_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    conflicts = await get_pending_conflicts(
        db, project_id, artifact_type=artifact_type, context_id=context_id
    )
    return {
        "project_id": project_id,
        "count": len(conflicts),
        "conflicts": [_conflict_to_dict(c) for c in conflicts],
    }


# ─── GET /{project_id}/{conflict_id} ─────────────────────────────────────────


@router.get("/{project_id}/{conflict_id}")
async def get_conflict(
    project_id: str,
    conflict_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    conflict = await db.get(PromotionConflict, conflict_id)
    if conflict is None or conflict.project_id != project_id:
        raise HTTPException(status_code=404, detail="Conflict not found.")

    result = _conflict_to_dict(conflict)

    # Enrich with context names
    if conflict.source_context_id:
        src = await db.get(WorkContext, conflict.source_context_id)
        result["source_context_name"] = src.name if src else None
        result["source_context_level"] = src.level if src else None
    if conflict.target_context_id:
        tgt = await db.get(WorkContext, conflict.target_context_id)
        result["target_context_name"] = tgt.name if tgt else None
        result["target_context_level"] = tgt.level if tgt else None

    return result


# ─── POST /{project_id}/{conflict_id}/resolve ────────────────────────────────


@router.post("/{project_id}/{conflict_id}/resolve")
async def resolve_conflict(
    project_id: str,
    conflict_id: str,
    body: ResolveRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    # Load and validate conflict
    conflict = await db.get(PromotionConflict, conflict_id)
    if conflict is None or conflict.project_id != project_id:
        raise HTTPException(status_code=404, detail="Conflict not found.")
    if conflict.status != "pending":
        raise HTTPException(
            status_code=422,
            detail=f"Conflict is already resolved (status='{conflict.status}'). Cannot resolve again.",
        )
    if body.resolution not in VALID_RESOLUTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid resolution {body.resolution!r}. Must be one of: {sorted(VALID_RESOLUTIONS)}.",
        )

    # Validate "edited" requires resolved_value with correct schema
    if body.resolution == "edited":
        if not body.resolved_value:
            raise HTTPException(status_code=422, detail="'edited' resolution requires resolved_value.")
        schema_cls = _EDITED_SCHEMAS.get(conflict.artifact_type)
        if schema_cls:
            try:
                schema_cls.model_validate(body.resolved_value)
            except Exception as exc:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid resolved_value for artifact type '{conflict.artifact_type}': {exc}",
                )

    now = datetime.now(timezone.utc)

    if body.resolution == "defer":
        # Defer: no blob change, mark as deferred
        conflict.status = "deferred"
        conflict.resolved_at = now
        db.add(ArtifactAuditLog(
            id=str(uuid.uuid4()),
            project_id=project_id,
            artifact_type=conflict.artifact_type,
            artifact_item_id=conflict.artifact_item_id,
            event_type="conflict_resolved",
            work_context_id=conflict.source_context_id,
            new_value={"resolution": "defer", "conflict_id": conflict_id},
            actor="human",
            actor_id=None,
            note=body.note,
            created_at=now,
        ))
        await db.commit()
    else:
        # Dispatch to adapter
        adapter_cls = _ADAPTER_MAP.get(conflict.artifact_type)
        if not adapter_cls:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown artifact type: {conflict.artifact_type!r}",
            )
        adapter_resolution = _RESOLUTION_MAP[body.resolution]
        adapter = adapter_cls(db)
        await adapter.apply_resolution(project_id, conflict_id, adapter_resolution, body.resolved_value)

        # Add note to audit log if provided (adapter already committed its audit entry)
        if body.note:
            db.add(ArtifactAuditLog(
                id=str(uuid.uuid4()),
                project_id=project_id,
                artifact_type=conflict.artifact_type,
                artifact_item_id=conflict.artifact_item_id,
                event_type="conflict_note",
                work_context_id=conflict.source_context_id,
                new_value={"conflict_id": conflict_id},
                actor="human",
                actor_id=None,
                note=body.note,
                created_at=now,
            ))
            await db.commit()

    # Refresh to get updated status
    await db.refresh(conflict)

    # Check if all pending conflicts for this source context are resolved
    retry_result = None
    if conflict.source_context_id:
        pending = await count_pending_conflicts(db, project_id, conflict.source_context_id)
        if pending == 0:
            service = PromotionService(db)
            retry = await service.retry_promotion_after_resolution(project_id, conflict.source_context_id)
            retry_result = {
                "promoted_count": retry.promoted_count,
                "conflict_count": retry.conflict_count,
            }

    return {
        "conflict": _conflict_to_dict(conflict),
        "retry_result": retry_result,
    }
