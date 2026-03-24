"""Project settings endpoints"""

import json
from typing import Any, Dict

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import JiraTestIn
from app.db.engine import get_db
from app.db.models import Project

router = APIRouter()


@router.get("/settings", response_model=Dict[str, Any])
async def get_project_settings(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    if project.settings:
        return json.loads(project.settings)
    return {}


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

    # Persist Jira settings to DB
    s = json.loads(project.settings) if project.settings else {}
    s["jira_url"] = jira_url
    s["jira_user_email"] = user_email
    s["jira_api_key"] = api_key
    project.settings = json.dumps(s)
    await db.commit()

    if not jira_url.startswith(("http://", "https://")):
        return {"ok": False, "status_code": None, "detail": "Nieprawidłowy adres — URL musi zaczynać się od http:// lub https://"}

    url = f"{jira_url}/rest/api/2/project?maxResults=1"
    auth = (user_email, api_key) if user_email else None
    headers = {} if auth else {"Authorization": f"Bearer {api_key}"}

    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(url, auth=auth, headers=headers)

        if resp.status_code == 401:
            return {"ok": False, "status_code": resp.status_code, "detail": "Nieautoryzowany. Sprawdź dane dostępowe i scope (wymagany: read:jira-work)."}
        if resp.status_code == 403:
            return {"ok": False, "status_code": resp.status_code, "detail": "Brak uprawnień. Sprawdź czy token ma scope read:jira-work."}
        if resp.status_code == 404:
            return {"ok": False, "status_code": resp.status_code, "detail": "Nie znaleziono endpointu. Sprawdź adres serwera Jira."}
        if not resp.is_success:
            return {"ok": False, "status_code": resp.status_code, "detail": f"Błąd serwera Jira: {resp.status_code}"}

        projects = resp.json()
        count = len(projects) if isinstance(projects, list) else 0
        return {"ok": True, "status_code": resp.status_code, "detail": f"Połączono. Dostępne projekty: {count}"}

    except httpx.ConnectError:
        return {"ok": False, "status_code": None, "detail": "Nie można nawiązać połączenia. Sprawdź adres serwera."}
    except httpx.TimeoutException:
        return {"ok": False, "status_code": None, "detail": "Przekroczono czas połączenia (8s)."}
    except httpx.InvalidURL as exc:
        return {"ok": False, "status_code": None, "detail": f"Nieprawidłowy adres URL: {exc}. Sprawdzany URL: {url!r}"}
    except Exception as exc:
        return {"ok": False, "status_code": None, "detail": str(exc)}


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
    project.settings = json.dumps(body)
    await db.commit()
    return body
