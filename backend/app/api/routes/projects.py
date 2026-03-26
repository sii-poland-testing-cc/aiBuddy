"""Projects CRUD API"""

import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import ProjectCreate, ProjectOut
from app.db.engine import get_db
from app.db.models import Project, ProjectFile
from app.services.work_context import get_or_create_default_domain

router = APIRouter()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _count_stmt():
    """Reusable SELECT that joins file counts onto each project row."""
    return (
        select(
            Project.id,
            Project.name,
            Project.description,
            Project.created_at,
            func.count(ProjectFile.id).label("file_count"),
        )
        .outerjoin(ProjectFile, ProjectFile.project_id == Project.id)
        .group_by(Project.id)
    )


def _to_out(row) -> ProjectOut:
    return ProjectOut(
        project_id=row.id,
        name=row.name,
        description=row.description or "",
        created_at=row.created_at.isoformat()
        if isinstance(row.created_at, datetime)
        else str(row.created_at),
        file_count=row.file_count,
    )


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("/", response_model=List[ProjectOut])
async def list_projects(db: AsyncSession = Depends(get_db)):
    stmt = _count_stmt().order_by(Project.created_at.desc())
    rows = (await db.execute(stmt)).all()
    return [_to_out(r) for r in rows]


@router.post("/", response_model=ProjectOut, status_code=201)
async def create_project(body: ProjectCreate, db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    project = Project(
        id=str(uuid.uuid4()),
        name=body.name,
        description=body.description or "",
        created_at=now,
    )
    db.add(project)
    await db.commit()

    # Auto-provision Default Domain for every new project (idempotent)
    await get_or_create_default_domain(db, project.id)

    return ProjectOut(
        project_id=project.id,
        name=project.name,
        description=project.description,
        created_at=project.created_at.isoformat(),
        file_count=0,
    )


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    stmt = _count_stmt().where(Project.id == project_id)
    row = (await db.execute(stmt)).first()
    if not row:
        raise HTTPException(404, "Project not found")
    return _to_out(row)


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if project:
        await db.delete(project)   # cascades to ProjectFile rows
        await db.commit()


@router.get("/{project_id}/settings", response_model=Dict[str, Any])
async def get_project_settings(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project.settings or {}


@router.put("/{project_id}/settings", response_model=Dict[str, Any])
async def update_project_settings(
    project_id: str,
    body: Dict[str, Any],
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    project.name = body.get("name", project.name)
    project.description = body.get("description", project.description)
    project.settings = body
    await db.commit()
    return body