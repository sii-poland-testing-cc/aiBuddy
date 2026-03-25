"""
Tests for /api/snapshots endpoints.
"""

import json
import uuid
from datetime import datetime, timezone, timedelta

import pytest


def _make_snapshot(project_id: str, offset_seconds: int = 0, **overrides):
    """Build an AuditSnapshot ORM object directly."""
    from app.db.models import AuditSnapshot

    snap = AuditSnapshot(
        id=str(uuid.uuid4()),
        project_id=project_id,
        created_at=datetime.now(timezone.utc) + timedelta(seconds=offset_seconds),
        files_used=json.dumps(overrides.get("files_used", ["test.csv"])),
        summary=json.dumps(overrides.get("summary", {
            "coverage_pct": 80.0,
            "duplicates_found": 2,
            "requirements_total": 10,
            "requirements_covered": 8,
        })),
        requirements_uncovered=json.dumps(overrides.get("requirements_uncovered", ["FR-009", "FR-010"])),
        recommendations=json.dumps(overrides.get("recommendations", ["Add more tests"])),
        diff=json.dumps(overrides.get("diff")) if "diff" in overrides else None,
    )
    return snap


async def _make_project(project_id: str) -> None:
    """Insert a minimal Project row so FK constraints on AuditSnapshot are satisfied."""
    from app.db.engine import AsyncSessionLocal
    from app.db.models import Project

    async with AsyncSessionLocal() as db:
        db.add(Project(id=project_id, name="test-project"))
        await db.commit()


async def _insert_snapshots(snapshots, project_id: str | None = None):
    """Insert ORM objects into the test DB, creating a parent project if needed."""
    from app.db.engine import AsyncSessionLocal

    if project_id is not None:
        await _make_project(project_id)

    async with AsyncSessionLocal() as db:
        for s in snapshots:
            db.add(s)
        await db.commit()


@pytest.mark.asyncio
async def test_list_empty(app_client):
    """GET /api/snapshots/{project_id} returns [] for a project with no snapshots."""
    project_id = str(uuid.uuid4())
    resp = app_client.get(f"/api/snapshots/{project_id}")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_returns_snapshots(app_client):
    """GET /api/snapshots/{project_id} returns inserted snapshots, newest first."""
    project_id = str(uuid.uuid4())
    snaps = [
        _make_snapshot(project_id, offset_seconds=0),
        _make_snapshot(project_id, offset_seconds=60),
    ]
    await _insert_snapshots(snaps, project_id=project_id)

    resp = app_client.get(f"/api/snapshots/{project_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    # Newest first
    assert data[0]["created_at"] > data[1]["created_at"]
    # JSON fields are parsed
    assert isinstance(data[0]["files_used"], list)
    assert isinstance(data[0]["summary"], dict)
    assert isinstance(data[0]["requirements_uncovered"], list)
    assert isinstance(data[0]["recommendations"], list)


@pytest.mark.asyncio
async def test_trend_shape(app_client):
    """GET /api/snapshots/{project_id}/trend returns arrays with correct shape."""
    project_id = str(uuid.uuid4())
    snaps = [
        _make_snapshot(project_id, offset_seconds=0, summary={"coverage_pct": 60.0, "duplicates_found": 1, "requirements_total": 5, "requirements_covered": 3}),
        _make_snapshot(project_id, offset_seconds=60, summary={"coverage_pct": 80.0, "duplicates_found": 0, "requirements_total": 5, "requirements_covered": 4}),
    ]
    await _insert_snapshots(snaps, project_id=project_id)

    resp = app_client.get(f"/api/snapshots/{project_id}/trend")
    assert resp.status_code == 200
    data = resp.json()

    assert set(data.keys()) == {"labels", "coverage", "duplicates", "requirements_covered", "requirements_total"}
    assert len(data["labels"]) == 2
    assert len(data["coverage"]) == 2
    # Oldest first in trend
    assert data["coverage"][0] <= data["coverage"][1]
    assert data["requirements_total"] == [5, 5]


@pytest.mark.asyncio
async def test_latest_returns_newest(app_client):
    """GET /api/snapshots/{project_id}/latest returns the most recent snapshot."""
    project_id = str(uuid.uuid4())
    older = _make_snapshot(project_id, offset_seconds=0)
    newer = _make_snapshot(project_id, offset_seconds=120)
    await _insert_snapshots([older, newer], project_id=project_id)

    resp = app_client.get(f"/api/snapshots/{project_id}/latest")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == newer.id


@pytest.mark.asyncio
async def test_latest_404_when_empty(app_client):
    """GET /api/snapshots/{project_id}/latest returns 404 for unknown project."""
    project_id = str(uuid.uuid4())
    resp = app_client.get(f"/api/snapshots/{project_id}/latest")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_snapshot(app_client):
    """DELETE /api/snapshots/{project_id}/{snapshot_id} removes the snapshot."""
    project_id = str(uuid.uuid4())
    snap = _make_snapshot(project_id)
    await _insert_snapshots([snap], project_id=project_id)

    resp = app_client.delete(f"/api/snapshots/{project_id}/{snap.id}")
    assert resp.status_code == 204

    # Should now be gone
    resp2 = app_client.get(f"/api/snapshots/{project_id}")
    assert resp2.json() == []


@pytest.mark.asyncio
async def test_delete_wrong_project_returns_404(app_client):
    """DELETE with mismatched project_id returns 404 (not leaking other projects' data)."""
    project_id = str(uuid.uuid4())
    other_project_id = str(uuid.uuid4())
    snap = _make_snapshot(project_id)
    await _insert_snapshots([snap], project_id=project_id)

    resp = app_client.delete(f"/api/snapshots/{other_project_id}/{snap.id}")
    assert resp.status_code == 404

    # Snapshot should still exist
    resp2 = app_client.get(f"/api/snapshots/{project_id}")
    assert len(resp2.json()) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Audit-selection endpoint tests
# ─────────────────────────────────────────────────────────────────────────────

def _create_project(app_client) -> str:
    r = app_client.post("/api/projects/", json={"name": "selection-test"})
    assert r.status_code in (200, 201)
    return r.json()["project_id"]


def _upload_csv(app_client, project_id: str, name: str = "sample_tests.csv",
                source_type: str = "file") -> None:
    from pathlib import Path
    csv_path = Path(__file__).parent / "fixtures" / "sample_tests.csv"
    with csv_path.open("rb") as fh:
        r = app_client.post(
            f"/api/files/{project_id}/upload?source_type={source_type}",
            files={"files": (name, fh, "text/csv")},
        )
    assert r.status_code == 200


def _run_audit(app_client, project_id: str) -> dict:
    from unittest.mock import AsyncMock, MagicMock, patch
    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(return_value='["Add more edge case tests."]')
    with patch("app.api.routes.chat.get_llm", return_value=mock_llm):
        r = app_client.post(
            "/api/chat/stream",
            json={"project_id": project_id, "message": "audit", "file_paths": []},
        )
    assert r.status_code == 200
    result_data: dict = {}
    for line in r.text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if payload == "[DONE]":
            break
        try:
            ev = json.loads(payload)
            if ev.get("type") == "result":
                result_data = ev["data"]
        except Exception:
            continue
    return result_data


def test_audit_selection_new_files_selected(app_client):
    """Files that have never been audited must be selected: true."""
    project_id = _create_project(app_client)
    _upload_csv(app_client, project_id, "file_a.csv")
    _upload_csv(app_client, project_id, "file_b.csv")

    resp = app_client.get(f"/api/files/{project_id}/audit-selection")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    for item in items:
        assert item["selected"] is True, f"Expected selected=true for {item['filename']}"
        assert item["last_used_in_audit_id"] is None


def test_audit_selection_used_files_deselected(app_client):
    """Files used in a prior audit must be selected: false."""
    project_id = _create_project(app_client)
    _upload_csv(app_client, project_id, "file_used.csv")
    _run_audit(app_client, project_id)

    resp = app_client.get(f"/api/files/{project_id}/audit-selection")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    item = items[0]
    assert item["selected"] is False, "Used file should be deselected"
    assert item["last_used_in_audit_id"] is not None


def test_audit_selection_url_always_selected(app_client):
    """URL-sourced files must remain selected: true even after being used in an audit."""
    project_id = _create_project(app_client)
    _upload_csv(app_client, project_id, "url_source.csv", source_type="url")
    _run_audit(app_client, project_id)

    resp = app_client.get(f"/api/files/{project_id}/audit-selection")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    item = items[0]
    assert item["source_type"] == "url"
    assert item["last_used_in_audit_id"] is not None, "Should have been used in audit"
    assert item["selected"] is True, "URL source must stay selected regardless of audit history"


def test_chat_auto_selects_new_files_only(app_client):
    """
    When file_paths is empty, the chat endpoint must only include files that
    haven't been used before (last_used_in_audit_id is None).
    """
    import asyncio
    from app.db.engine import AsyncSessionLocal
    from app.db.models import AuditSnapshot
    from sqlalchemy import select as sa_select

    project_id = _create_project(app_client)

    # Upload v1 and run audit (marks v1 as used)
    _upload_csv(app_client, project_id, "file_v1.csv")
    _run_audit(app_client, project_id)

    # Upload v2 (not yet audited)
    _upload_csv(app_client, project_id, "file_v2.csv")

    # Run second audit — should only pick up file_v2
    result = _run_audit(app_client, project_id)
    assert result, "No result from second audit"
    snapshot_id = result.get("snapshot_id")
    assert snapshot_id, "snapshot_id missing from second audit result"

    async def _query_snap():
        async with AsyncSessionLocal() as db:
            return (await db.execute(
                sa_select(AuditSnapshot).where(AuditSnapshot.id == snapshot_id)
            )).scalars().first()

    snap = asyncio.get_event_loop().run_until_complete(_query_snap())
    assert snap is not None
    files_used = json.loads(snap.files_used or "[]")
    assert any("file_v2.csv" in p for p in files_used), \
        f"file_v2.csv should be in files_used: {files_used}"
    assert not any("file_v1.csv" in p for p in files_used), \
        f"file_v1.csv should NOT be in files_used: {files_used}"
