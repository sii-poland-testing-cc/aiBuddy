"""Project settings endpoints"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import JiraTestIn
from app.db.engine import get_db
from app.db.models import Project
from app.services.jira_client import JiraClient

router = APIRouter()


@router.get("/settings", response_model=Dict[str, Any])
async def get_project_settings(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project.settings or {}


@router.post("/settings/test-jira")
async def test_jira_connection(
    project_id: str,
    body: JiraTestIn,
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")

    jira_url = body.jira_url.strip().rstrip("/")
    user_email = body.jira_user_email.strip()
    api_key = body.jira_api_key.strip()

    if not jira_url or not api_key:
        raise HTTPException(400, "jira_url and jira_api_key are required")

    # Persist Jira settings to DB (JsonType handles serialisation automatically)
    existing: dict = project.settings or {}
    s = {**existing}
    s["jira_url"] = jira_url
    s["jira_user_email"] = user_email
    s["jira_api_key"] = api_key
    project.settings = s
    await db.commit()

    client = JiraClient(jira_url=jira_url, user_email=user_email, api_key=api_key)
    return await client.test_connection()


@router.put("/settings", response_model=Dict[str, Any])
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
