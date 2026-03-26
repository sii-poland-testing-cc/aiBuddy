"""
WorkContext service — Domain/Epic/Story lifecycle management.

All business logic for creating, reading, updating WorkContexts lives here.
Routes call these functions; no SQLAlchemy in the routes layer.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import WorkContext

# ─── Constants ────────────────────────────────────────────────────────────────

# Valid level values
LEVELS = {"domain", "epic", "story"}

# Which level is a valid parent for each level
_VALID_PARENT_LEVEL: dict[str, str] = {
    "epic":  "domain",
    "story": "epic",
}

# Status transitions allowed via PATCH.
# "promoted" is intentionally absent as a target — that is set by Phase 5
# promotion endpoint, not by a user PATCH.
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft":    {"active", "archived"},
    "active":   {"ready",  "archived"},
    "ready":    {"archived"},
    "promoted": {"archived"},
    "archived": set(),          # terminal — no transitions out
}


# ─── Public functions ─────────────────────────────────────────────────────────

async def get_or_create_default_domain(
    db: AsyncSession,
    project_id: str,
) -> WorkContext:
    """
    Return the first Domain for the project, creating one named 'Default Domain'
    if none exists yet.  Idempotent — safe to call multiple times.
    """
    stmt = (
        select(WorkContext)
        .where(WorkContext.project_id == project_id, WorkContext.level == "domain")
        .limit(1)
    )
    result = await db.execute(stmt)
    domain = result.scalar_one_or_none()
    if domain is not None:
        return domain

    domain = WorkContext(
        project_id=project_id,
        parent_id=None,
        level="domain",
        name="Default Domain",
        status="draft",
    )
    db.add(domain)
    await db.commit()
    await db.refresh(domain)
    return domain


async def create_work_context(
    db: AsyncSession,
    project_id: str,
    level: str,
    name: str,
    description: Optional[str],
    parent_id: str,
) -> WorkContext:
    """
    Create a new Epic or Story.  Validates:
    - level must be 'epic' or 'story' (Domains are auto-created)
    - parent_id must exist, belong to this project, and be the right level
    """
    if level == "domain":
        raise HTTPException(
            status_code=422,
            detail="Domains are auto-created per project and cannot be created via this endpoint.",
        )
    if level not in _VALID_PARENT_LEVEL:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid level {level!r}. Must be 'epic' or 'story'.",
        )

    # Validate parent
    parent = await db.get(WorkContext, parent_id)
    if parent is None or parent.project_id != project_id:
        raise HTTPException(status_code=422, detail="Parent context not found.")

    expected_parent_level = _VALID_PARENT_LEVEL[level]
    if parent.level != expected_parent_level:
        raise HTTPException(
            status_code=422,
            detail=(
                f"A '{level}' must have a '{expected_parent_level}' as parent, "
                f"but parent has level '{parent.level}'."
            ),
        )

    ctx = WorkContext(
        project_id=project_id,
        parent_id=parent_id,
        level=level,
        name=name,
        description=description,
        status="draft",
    )
    db.add(ctx)
    await db.commit()
    await db.refresh(ctx)
    return ctx


async def get_work_context(
    db: AsyncSession,
    project_id: str,
    context_id: str,
) -> WorkContext:
    """Return a single WorkContext, raising 404 if not found or wrong project."""
    ctx = await db.get(WorkContext, context_id)
    if ctx is None or ctx.project_id != project_id:
        raise HTTPException(status_code=404, detail="Work context not found.")
    return ctx


async def list_work_contexts(
    db: AsyncSession,
    project_id: str,
    level: Optional[str] = None,
) -> list[WorkContext]:
    """Return all WorkContexts for the project, optionally filtered by level."""
    stmt = select(WorkContext).where(WorkContext.project_id == project_id)
    if level is not None:
        stmt = stmt.where(WorkContext.level == level)
    stmt = stmt.order_by(WorkContext.created_at)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_work_context(
    db: AsyncSession,
    project_id: str,
    context_id: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    status: Optional[str] = None,
) -> WorkContext:
    """
    Update name, description, and/or status on a WorkContext.
    Status transitions are validated against _ALLOWED_TRANSITIONS.
    Setting status='promoted' via PATCH is rejected (use Phase 5 promotion endpoint).
    Marking status='ready' validates that no in-progress children exist.
    """
    ctx = await get_work_context(db, project_id, context_id)

    if status is not None:
        if status == "promoted":
            raise HTTPException(
                status_code=422,
                detail=(
                    "Status 'promoted' cannot be set via PATCH. "
                    "Use POST /api/promotion/{project_id}/{ctx_id}/promote."
                ),
            )
        allowed = _ALLOWED_TRANSITIONS.get(ctx.status, set())
        if status not in allowed:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Invalid status transition: '{ctx.status}' → '{status}'. "
                    f"Allowed from '{ctx.status}': {sorted(allowed) or 'none (terminal)'}."
                ),
            )

        # Marking "ready": validate all children are promoted or archived
        if status == "ready" and ctx.level in ("epic", "domain"):
            await _validate_children_ready(db, project_id, context_id, ctx.level)

        ctx.status = status

    if name is not None:
        ctx.name = name
    if description is not None:
        ctx.description = description

    ctx.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(ctx)
    return ctx


async def _validate_children_ready(
    db: AsyncSession,
    project_id: str,
    context_id: str,
    level: str,
) -> None:
    """
    Raise 422 if any child WorkContext is not in a terminal state
    (promoted or archived).

    Called before marking an Epic or Domain as 'ready'.
    - Epic level → validate all child Stories
    - Domain level → validate all child Epics
    """
    child_level = "story" if level == "epic" else "epic"
    stmt = select(WorkContext).where(
        WorkContext.project_id == project_id,
        WorkContext.parent_id == context_id,
        WorkContext.level == child_level,
    )
    children = (await db.execute(stmt)).scalars().all()

    non_terminal = [
        c for c in children if c.status not in ("promoted", "archived")
    ]
    if non_terminal:
        names = ", ".join(f"'{c.name}' ({c.status})" for c in non_terminal)
        raise HTTPException(
            status_code=422,
            detail=(
                f"Cannot mark as 'ready': {len(non_terminal)} child {child_level}(s) "
                f"are not yet promoted or archived: {names}."
            ),
        )


async def archive_work_context(
    db: AsyncSession,
    project_id: str,
    context_id: str,
) -> WorkContext:
    """
    Soft-delete: set status to 'archived'.
    Works for all levels including Domains.
    """
    ctx = await get_work_context(db, project_id, context_id)
    if ctx.status == "archived":
        return ctx  # idempotent
    ctx.status = "archived"
    ctx.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(ctx)
    return ctx


async def create_domain(
    db: AsyncSession,
    project_id: str,
    name: str,
    description: Optional[str] = None,
) -> WorkContext:
    """Create an additional Domain for multi-domain projects."""
    ctx = WorkContext(
        project_id=project_id,
        parent_id=None,
        level="domain",
        name=name,
        description=description,
        status="draft",
    )
    db.add(ctx)
    await db.commit()
    await db.refresh(ctx)
    return ctx
