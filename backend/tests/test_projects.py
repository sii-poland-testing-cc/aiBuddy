"""
Tests for /api/projects/ endpoints.
"""

import pytest


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_create_project(app_client):
    """POST /api/projects/ creates a project and returns its id."""
    r = app_client.post("/api/projects/", json={"name": "my-project"})
    assert r.status_code in (200, 201), r.text
    data = r.json()
    assert "project_id" in data
    assert data["name"] == "my-project"
    assert isinstance(data["project_id"], str)
    assert len(data["project_id"]) == 36  # UUID


def test_create_project_with_description(app_client):
    """POST /api/projects/ accepts an optional description."""
    r = app_client.post("/api/projects/", json={"name": "p2", "description": "desc"})
    assert r.status_code in (200, 201), r.text
    assert r.json()["name"] == "p2"


def test_list_projects(app_client):
    """GET /api/projects/ returns the created project."""
    app_client.post("/api/projects/", json={"name": "list-test"})
    r = app_client.get("/api/projects/")
    assert r.status_code == 200
    names = [p["name"] for p in r.json()]
    assert "list-test" in names


def test_get_project(app_client):
    """GET /api/projects/{id} returns the project."""
    create = app_client.post("/api/projects/", json={"name": "get-test"})
    project_id = create.json()["project_id"]

    r = app_client.get(f"/api/projects/{project_id}")
    assert r.status_code == 200
    assert r.json()["project_id"] == project_id


def test_get_project_not_found(app_client):
    """GET /api/projects/{id} returns 404 for unknown id."""
    r = app_client.get("/api/projects/does-not-exist")
    assert r.status_code == 404


def test_delete_project(app_client):
    """DELETE /api/projects/{id} removes the project."""
    create = app_client.post("/api/projects/", json={"name": "del-test"})
    project_id = create.json()["project_id"]

    r = app_client.delete(f"/api/projects/{project_id}")
    assert r.status_code == 204

    r2 = app_client.get(f"/api/projects/{project_id}")
    assert r2.status_code == 404


def test_project_settings_roundtrip(app_client):
    """PUT /api/projects/{id}/settings persists and GET retrieves settings."""
    create = app_client.post("/api/projects/", json={"name": "settings-test"})
    project_id = create.json()["project_id"]

    payload = {"theme": "dark", "language": "pl"}
    put = app_client.put(f"/api/projects/{project_id}/settings", json=payload)
    assert put.status_code == 200

    get = app_client.get(f"/api/projects/{project_id}/settings")
    assert get.status_code == 200
    assert get.json()["theme"] == "dark"


def test_project_settings_empty(app_client):
    """GET /api/projects/{id}/settings returns {} for a fresh project."""
    create = app_client.post("/api/projects/", json={"name": "settings-empty"})
    project_id = create.json()["project_id"]

    r = app_client.get(f"/api/projects/{project_id}/settings")
    assert r.status_code == 200
    assert r.json() == {}
