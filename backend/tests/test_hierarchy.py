"""
test_hierarchy.py — Schema tests for Phase 1 hierarchy tables.
===============================================================
Verifies that organizations and workspaces tables exist with the
correct structure and that the projects table has the new FK columns.

Run from backend/ with:
    pytest tests/test_hierarchy.py -v
"""

import asyncio
import pytest
from sqlalchemy import text
from app.db.engine import AsyncSessionLocal
from app.db.hierarchy_models import DEFAULT_ORG_ID


def run(coro):
    """Helper: run an async coroutine synchronously via the event loop."""
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(coro)


# ─────────────────────────────────────────────────────────────────────────────
# 1. organizations table exists with default org row
# ─────────────────────────────────────────────────────────────────────────────

def test_organizations_table_exists(app_client):
    """organizations table must exist and contain the default org row."""

    async def _query():
        async with AsyncSessionLocal() as session:
            # Confirm the table is accessible
            result = await session.execute(
                text("SELECT id, name, owner_id FROM organizations WHERE id = :id"),
                {"id": DEFAULT_ORG_ID},
            )
            return result.fetchone()

    row = run(_query())
    assert row is not None, "Default organization row not found"
    assert row[0] == DEFAULT_ORG_ID
    assert row[1] == "Default Organization"
    assert row[2] is None, "owner_id should be NULL (users table not yet created)"


# ─────────────────────────────────────────────────────────────────────────────
# 2. workspaces table exists with correct columns
# ─────────────────────────────────────────────────────────────────────────────

def test_workspaces_table_exists(app_client):
    """workspaces table must exist in sqlite_master with all required columns."""

    async def _query():
        async with AsyncSessionLocal() as session:
            # Confirm the table exists
            tbl = await session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='workspaces'")
            )
            table_row = tbl.fetchone()

            # Fetch column info
            cols = await session.execute(text("PRAGMA table_info(workspaces)"))
            col_names = {row[1] for row in cols.fetchall()}
            return table_row, col_names

    table_row, col_names = run(_query())
    assert table_row is not None, "workspaces table not found in sqlite_master"
    assert "id" in col_names
    assert "organization_id" in col_names
    assert "name" in col_names
    assert "created_at" in col_names


# ─────────────────────────────────────────────────────────────────────────────
# 3. projects table has organization_id and workspace_id columns
# ─────────────────────────────────────────────────────────────────────────────

def test_project_has_hierarchy_columns(app_client):
    """Creating a project via API should yield rows with organization_id + workspace_id columns."""
    # Create a project via the API
    resp = app_client.post("/api/projects/", json={"name": "Hierarchy Column Test"})
    assert resp.status_code in (200, 201), f"Expected 201, got {resp.status_code}: {resp.text}"
    # ProjectOut uses "project_id" as the field name
    project_id = resp.json().get("project_id") or resp.json().get("id")

    async def _query():
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT organization_id, workspace_id FROM projects WHERE id = :id"),
                {"id": project_id},
            )
            return result.fetchone()

    row = run(_query())
    assert row is not None, f"Project {project_id} not found in DB"
    # workspace_id should be NULL (no workspace assigned at creation)
    assert row[1] is None, "workspace_id should be NULL for a freshly created project"


# ─────────────────────────────────────────────────────────────────────────────
# 4. default organization row is correct
# ─────────────────────────────────────────────────────────────────────────────

def test_default_org_exists(app_client):
    """The well-known default org UUID must exist with correct data."""

    async def _query():
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                text("SELECT id, name, owner_id FROM organizations WHERE id = :id"),
                {"id": "00000000-0000-0000-0000-000000000001"},
            )
            return result.fetchone()

    row = run(_query())
    assert row is not None, "Default organization not seeded"
    assert row[0] == "00000000-0000-0000-0000-000000000001"
    assert row[1] == "Default Organization"
    assert row[2] is None


# ─────────────────────────────────────────────────────────────────────────────
# 5. Smoke test — existing API patterns still work after schema change
# ─────────────────────────────────────────────────────────────────────────────

def test_existing_project_api_smoke(app_client):
    """Existing project CRUD endpoints must return expected HTTP codes after migration."""
    # Create
    create_resp = app_client.post(
        "/api/projects/", json={"name": "Smoke Test Project", "description": "hierarchy smoke test"}
    )
    assert create_resp.status_code in (200, 201), f"Create failed: {create_resp.text}"
    # ProjectOut uses "project_id" as the field name
    project_id = create_resp.json().get("project_id") or create_resp.json().get("id")

    # List
    list_resp = app_client.get("/api/projects/")
    assert list_resp.status_code == 200
    ids = [p.get("project_id") or p.get("id") for p in list_resp.json()]
    assert project_id in ids, "Created project not found in list"

    # Get single
    get_resp = app_client.get(f"/api/projects/{project_id}")
    assert get_resp.status_code == 200
    assert (get_resp.json().get("project_id") or get_resp.json().get("id")) == project_id
