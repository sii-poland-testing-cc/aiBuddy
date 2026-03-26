"""
Work Contexts API — Domain / Epic / Story management.

Endpoints:
  POST   /api/work-contexts/{project_id}           — create Epic or Story
  GET    /api/work-contexts/{project_id}            — list all (hierarchy tree)
  GET    /api/work-contexts/{project_id}/{ctx_id}   — single context detail
  PATCH  /api/work-contexts/{project_id}/{ctx_id}   — update name / status / description
  DELETE /api/work-contexts/{project_id}/{ctx_id}   — soft-delete (status → archived)

Domains are auto-created on project creation and cannot be created via this endpoint.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.engine import get_db
from app.services.work_context import (
    archive_work_context,
    create_domain,
    create_work_context,
    get_work_context,
    list_work_contexts,
    update_work_context,
)

router = APIRouter()


# ─── Pydantic schemas ─────────────────────────────────────────────────────────

class WorkContextCreate(BaseModel):
    level: str          # "epic" | "story"  (not "domain" — auto-created)
    name: str
    description: Optional[str] = None
    parent_id: str      # required; epic needs a domain parent, story needs an epic parent


class WorkContextUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    # "active" | "ready" | "archived"
    # "promoted" is intentionally NOT settable here — use Phase 5 promotion endpoint


class WorkContextOut(BaseModel):
    id: str
    project_id: str
    parent_id: Optional[str]
    level: str
    name: str
    description: Optional[str]
    status: str
    created_at: str
    updated_at: Optional[str]
    promoted_at: Optional[str]

    model_config = {"from_attributes": True}


class WorkContextNode(WorkContextOut):
    """WorkContextOut extended with nested children for the hierarchy tree."""
    children: list["WorkContextNode"] = []


class WorkContextTree(BaseModel):
    contexts: list[WorkContextNode]
    total: int


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _dt(v: Optional[datetime]) -> Optional[str]:
    if v is None:
        return None
    return v.isoformat()


def _to_out(ctx) -> WorkContextOut:
    return WorkContextOut(
        id=ctx.id,
        project_id=ctx.project_id,
        parent_id=ctx.parent_id,
        level=ctx.level,
        name=ctx.name,
        description=ctx.description,
        status=ctx.status,
        created_at=_dt(ctx.created_at) or "",
        updated_at=_dt(ctx.updated_at),
        promoted_at=_dt(ctx.promoted_at),
    )


def _build_tree(all_ctxs: list) -> list[WorkContextNode]:
    """
    Build a nested tree from a flat list of WorkContext ORM objects.
    Top-level nodes are those without a parent (parent_id is None) or
    whose parent is not in this project's context list.
    """
    by_id: dict[str, WorkContextNode] = {}
    for ctx in all_ctxs:
        node = WorkContextNode(
            id=ctx.id,
            project_id=ctx.project_id,
            parent_id=ctx.parent_id,
            level=ctx.level,
            name=ctx.name,
            description=ctx.description,
            status=ctx.status,
            created_at=_dt(ctx.created_at) or "",
            updated_at=_dt(ctx.updated_at),
            promoted_at=_dt(ctx.promoted_at),
            children=[],
        )
        by_id[ctx.id] = node

    roots: list[WorkContextNode] = []
    for node in by_id.values():
        if node.parent_id is None or node.parent_id not in by_id:
            roots.append(node)
        else:
            by_id[node.parent_id].children.append(node)

    return roots


# ─── Routes ───────────────────────────────────────────────────────────────────

class WorkContextDomainCreate(BaseModel):
    name: str
    description: Optional[str] = None

@router.post("/{project_id}/domain", response_model=WorkContextOut, status_code=201)
async def create_domain_context(
    project_id: str,
    body: WorkContextDomainCreate,
    db: AsyncSession = Depends(get_db),
) -> WorkContextOut:
    """Create an additional Domain for multi-domain projects."""
    ctx = await create_domain(db=db, project_id=project_id, name=body.name, description=body.description)
    return _to_out(ctx)


@router.post("/{project_id}", response_model=WorkContextOut, status_code=201)
async def create_context(
    project_id: str,
    body: WorkContextCreate,
    db: AsyncSession = Depends(get_db),
) -> WorkContextOut:
    ctx = await create_work_context(
        db=db,
        project_id=project_id,
        level=body.level,
        name=body.name,
        description=body.description,
        parent_id=body.parent_id,
    )
    return _to_out(ctx)


@router.get("/{project_id}", response_model=WorkContextTree)
async def list_contexts(
    project_id: str,
    level: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
) -> WorkContextTree:
    ctxs = await list_work_contexts(db=db, project_id=project_id, level=level)
    tree = _build_tree(ctxs)
    return WorkContextTree(contexts=tree, total=len(ctxs))


@router.get("/{project_id}/{ctx_id}", response_model=WorkContextOut)
async def get_context(
    project_id: str,
    ctx_id: str,
    db: AsyncSession = Depends(get_db),
) -> WorkContextOut:
    ctx = await get_work_context(db=db, project_id=project_id, context_id=ctx_id)
    return _to_out(ctx)


@router.patch("/{project_id}/{ctx_id}", response_model=WorkContextOut)
async def patch_context(
    project_id: str,
    ctx_id: str,
    body: WorkContextUpdate,
    db: AsyncSession = Depends(get_db),
) -> WorkContextOut:
    ctx = await update_work_context(
        db=db,
        project_id=project_id,
        context_id=ctx_id,
        name=body.name,
        description=body.description,
        status=body.status,
    )
    return _to_out(ctx)


@router.delete("/{project_id}/{ctx_id}", response_model=WorkContextOut)
async def delete_context(
    project_id: str,
    ctx_id: str,
    db: AsyncSession = Depends(get_db),
) -> WorkContextOut:
    """Soft-delete: sets status to 'archived'. Works for all levels including domains."""
    ctx = await archive_work_context(db=db, project_id=project_id, context_id=ctx_id)
    return _to_out(ctx)
