"""Files upload + indexing API"""

import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.engine import get_db
from app.db.models import Project, ProjectFile
from app.rag.context_builder import ContextBuilder

router = APIRouter()
context_builder = ContextBuilder()
logger = logging.getLogger("ai_buddy")

_upload_root = Path(settings.UPLOAD_DIR)
_upload_root.mkdir(parents=True, exist_ok=True)


# ─── Pydantic schemas ─────────────────────────────────────────────────────────

class UploadedFile(BaseModel):
    filename: str
    file_path: str
    size_bytes: int
    project_id: str
    indexed: bool


class FileOut(BaseModel):
    filename: str
    file_path: str
    size_bytes: int
    indexed: bool
    uploaded_at: str


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("/{project_id}/upload", response_model=List[UploadedFile])
async def upload_files(
    project_id: str,
    files: List[UploadFile] = File(...),
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
