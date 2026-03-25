"""Files upload + indexing API"""

import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from app.api.schemas import AuditSelectionItem, FileOut, JiraIssueIn, UploadedFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.engine import AsyncSessionLocal, get_db
from app.db.models import AuditSnapshot, Project, ProjectFile
from app.rag.context_builder import ContextBuilder

router = APIRouter()
context_builder = ContextBuilder()
logger = logging.getLogger("ai_buddy")

_upload_root = Path(settings.UPLOAD_DIR)
_upload_root.mkdir(parents=True, exist_ok=True)


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/{project_id}/upload", response_model=List[UploadedFile])
async def upload_files(
    project_id: str,
    files: List[UploadFile] = File(...),
    source_type: str = Query(default="file"),
    db: AsyncSession = Depends(get_db),
):
    # Verify the project exists
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, f"Project '{project_id}' not found")

    project_dir = _upload_root / project_id
    project_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: List[str] = []
    db_records: List[ProjectFile] = []
    result: List[UploadedFile] = []

    for upload in files:
        ext = Path(upload.filename).suffix.lower()
        if ext not in settings.ALLOWED_EXTENSIONS:
            raise HTTPException(400, f"File type '{ext}' not allowed.")

        dest = project_dir / upload.filename
        with dest.open("wb") as f:
            shutil.copyfileobj(upload.file, f)

        size = dest.stat().st_size
        if size > settings.MAX_UPLOAD_MB * 1024 * 1024:
            dest.unlink()
            raise HTTPException(
                413, f"File '{upload.filename}' exceeds {settings.MAX_UPLOAD_MB} MB."
            )

        file_path = str(dest)
        record = ProjectFile(
            id=str(uuid.uuid4()),
            project_id=project_id,
            filename=upload.filename,
            file_path=file_path,
            size_bytes=size,
            indexed=False,
            uploaded_at=datetime.now(timezone.utc),
            source_type=source_type,
        )
        db.add(record)
        db_records.append(record)
        saved_paths.append(file_path)
        result.append(
            UploadedFile(
                filename=upload.filename,
                file_path=file_path,
                size_bytes=size,
                project_id=project_id,
                indexed=False,
            )
        )

    await db.commit()

    # Index into RAG vector store; update indexed flag on success
    if saved_paths:
        try:
            await context_builder.index_files(
                project_id=project_id, file_paths=saved_paths
            )
            for record in db_records:
                record.indexed = True
            for out in result:
                out.indexed = True
            await db.commit()
        except Exception as exc:
            logger.warning("RAG indexing failed: %s", exc)

    return result


@router.get("/{project_id}", response_model=List[FileOut])
async def list_files(project_id: str, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(ProjectFile)
        .where(ProjectFile.project_id == project_id)
        .order_by(ProjectFile.uploaded_at.desc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [
        FileOut(
            filename=r.filename,
            file_path=r.file_path,
            size_bytes=r.size_bytes,
            indexed=r.indexed,
            uploaded_at=r.uploaded_at.isoformat()
            if isinstance(r.uploaded_at, datetime)
            else str(r.uploaded_at),
        )
        for r in rows
    ]


@router.post("/{project_id}/jira", response_model=UploadedFile, status_code=201)
async def add_jira_issue(
    project_id: str,
    body: JiraIssueIn,
    db: AsyncSession = Depends(get_db),
):
    from app.services.jira_client import JiraClient, to_markdown

    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, f"Project '{project_id}' not found")

    issue_key = body.issue_key.strip().upper()
    if not issue_key:
        raise HTTPException(400, "issue_key is required")

    # Read Jira credentials from project settings (JsonType → already a dict)
    s: dict = project.settings or {}
    jira_url = s.get("jira_url", "")
    user_email = s.get("jira_user_email", "")
    api_key = s.get("jira_api_key", "")
    if not jira_url or not api_key:
        raise HTTPException(
            400,
            "Brak konfiguracji Jira. Skonfiguruj połączenie w ustawieniach projektu.",
        )

    # Fetch issue with full depth-aware context
    client = JiraClient(jira_url=jira_url, user_email=user_email, api_key=api_key)
    data = await client.fetch_with_context(issue_key)
    if data is None:
        raise HTTPException(404, f"Issue '{issue_key}' not found in Jira.")

    # Save as markdown to disk
    jira_dir = _upload_root / project_id / "jira"
    jira_dir.mkdir(parents=True, exist_ok=True)
    md_path = jira_dir / f"{issue_key}.md"
    md_path.write_text(to_markdown(data), encoding="utf-8")
    file_path = str(md_path)
    size = md_path.stat().st_size

    # Upsert ProjectFile record (re-fetch refreshes the MD)
    stmt = select(ProjectFile).where(
        ProjectFile.project_id == project_id,
        ProjectFile.filename == issue_key,
        ProjectFile.source_type == "jira",
    )
    record = (await db.execute(stmt)).scalar_one_or_none()
    if record:
        record.file_path = file_path
        record.size_bytes = size
        record.uploaded_at = datetime.now(timezone.utc)
    else:
        record = ProjectFile(
            id=str(uuid.uuid4()),
            project_id=project_id,
            filename=issue_key,
            file_path=file_path,
            size_bytes=size,
            indexed=False,
            uploaded_at=datetime.now(timezone.utc),
            source_type="jira",
        )
        db.add(record)
    await db.commit()

    # Index into Chroma
    try:
        await context_builder.index_files(project_id=project_id, file_paths=[file_path])
        record.indexed = True
        await db.commit()
    except Exception as exc:
        logger.warning("RAG indexing failed for Jira %s: %s", issue_key, exc)

    return UploadedFile(
        filename=issue_key,
        file_path=file_path,
        size_bytes=size,
        project_id=project_id,
        indexed=record.indexed,
    )


@router.delete("/{project_id}/{file_id}", status_code=204)
async def delete_file(
    project_id: str,
    file_id: str,
    db: AsyncSession = Depends(get_db),
):
    record = await db.get(ProjectFile, file_id)
    if not record or record.project_id != project_id:
        raise HTTPException(404, "File not found")
    await db.delete(record)
    await db.commit()


@router.get("/{project_id}/audit-selection", response_model=List[AuditSelectionItem])
async def get_audit_selection(project_id: str, db: AsyncSession = Depends(get_db)):
    """
    Return all project files with a computed default selection state.

    Selection rules:
    - source_type != "file" (URL/Jira/Confluence) → always selected
    - last_used_in_audit_id is None → selected (never used in an audit)
    - last_used_in_audit_id is set → deselected (already audited)

    Order: selected files first, deselected last. Within each group: newest first.
    """
    stmt = (
        select(ProjectFile)
        .where(ProjectFile.project_id == project_id)
        .order_by(ProjectFile.uploaded_at.desc())
    )
    files = list((await db.execute(stmt)).scalars().all())

    # Build a lookup of snapshot created_at by snapshot id
    snapshot_ids = {f.last_used_in_audit_id for f in files if f.last_used_in_audit_id}
    snap_dates: dict[str, str] = {}
    if snapshot_ids:
        from app.db.models import AuditSnapshot
        snap_stmt = select(AuditSnapshot).where(AuditSnapshot.id.in_(snapshot_ids))
        snaps = (await db.execute(snap_stmt)).scalars().all()
        snap_dates = {s.id: s.created_at.isoformat() for s in snaps}

    def _selected(f: ProjectFile) -> bool:
        # Same policy as audit_file_filter() in app/db/queries.py — keep in sync.
        if f.source_type != "file":
            return True
        return f.last_used_in_audit_id is None

    items = [
        AuditSelectionItem(
            id=f.id,
            filename=f.filename,
            file_path=f.file_path,
            source_type=f.source_type,
            size_bytes=f.size_bytes,
            uploaded_at=f.uploaded_at.isoformat()
            if isinstance(f.uploaded_at, datetime)
            else str(f.uploaded_at),
            last_used_in_audit_id=f.last_used_in_audit_id,
            last_used_in_audit_at=snap_dates.get(f.last_used_in_audit_id)
            if f.last_used_in_audit_id
            else None,
            selected=_selected(f),
        )
        for f in files
    ]

    # selected first, deselected last (stable: within group order is already newest-first)
    items.sort(key=lambda x: (0 if x.selected else 1))
    return items
