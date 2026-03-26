"""
Phase 6 tests — Conflicts API (view + resolve pending promotion conflicts).
"""

import asyncio
import uuid
from datetime import datetime, timezone

import pytest


# ─── Async DB helpers ─────────────────────────────────────────────────────────

def _insert_conflict(
    project_id: str,
    source_ctx_id: str,
    target_ctx_id: str,
    artifact_type: str = "requirement",
    artifact_item_id: str | None = None,
    incoming: dict | None = None,
    existing: dict | None = None,
    conflict_reason: str = "title_mismatch (similarity=0.20)",
) -> str:
    from app.db.engine import AsyncSessionLocal
    from app.db.models import PromotionConflict

    if artifact_item_id is None:
        artifact_item_id = str(uuid.uuid4())
    if incoming is None:
        incoming = {"id": artifact_item_id, "title": "Incoming Title", "description": ""}
    if existing is None:
        existing = {"id": str(uuid.uuid4()), "title": "Existing Title", "description": ""}

    async def _q():
        async with AsyncSessionLocal() as db:
            conflict_id = str(uuid.uuid4())
            db.add(PromotionConflict(
                id=conflict_id,
                project_id=project_id,
                artifact_type=artifact_type,
                artifact_item_id=artifact_item_id,
                source_context_id=source_ctx_id,
                target_context_id=target_ctx_id,
                incoming_value=incoming,
                existing_value=existing,
                conflict_reason=conflict_reason,
                status="pending",
                created_at=datetime.now(timezone.utc),
            ))
            await db.commit()
            return conflict_id

    return asyncio.get_event_loop().run_until_complete(_q())


def _get_conflict_status(conflict_id: str) -> str:
    from app.db.engine import AsyncSessionLocal
    from app.db.models import PromotionConflict

    async def _q():
        async with AsyncSessionLocal() as db:
            c = await db.get(PromotionConflict, conflict_id)
            return c.status if c else "NOT_FOUND"

    return asyncio.get_event_loop().run_until_complete(_q())


def _get_audit_events(project_id: str, artifact_item_id: str) -> list[str]:
    """Return list of event_type strings for the item's audit log entries."""
    from app.db.engine import AsyncSessionLocal
    from app.db.models import ArtifactAuditLog
    from sqlalchemy import select

    async def _q():
        async with AsyncSessionLocal() as db:
            stmt = select(ArtifactAuditLog).where(
                ArtifactAuditLog.project_id == project_id,
                ArtifactAuditLog.artifact_item_id == artifact_item_id,
            )
            rows = (await db.execute(stmt)).scalars().all()
            return [r.event_type for r in rows]

    return asyncio.get_event_loop().run_until_complete(_q())


def _insert_requirement_conflict_pending(project_id: str, ctx_id: str) -> str:
    """Insert a Requirement with lifecycle_status='conflict_pending', return its ID."""
    from app.db.engine import AsyncSessionLocal
    from app.db.requirements_models import Requirement

    async def _q():
        async with AsyncSessionLocal() as db:
            req_id = str(uuid.uuid4())
            db.add(Requirement(
                id=req_id,
                project_id=project_id,
                level="functional_req",
                title="Conflict Pending Requirement",
                description="Test req",
                source_type="formal",
                work_context_id=ctx_id,
                lifecycle_status="conflict_pending",
            ))
            await db.commit()
            return req_id

    return asyncio.get_event_loop().run_until_complete(_q())


# ─── HTTP helpers ─────────────────────────────────────────────────────────────

def _make_project(app_client, name: str = "conflict-test") -> str:
    r = app_client.post("/api/projects/", json={"name": name})
    assert r.status_code in (200, 201)
    return r.json()["project_id"]


def _get_domain(app_client, project_id: str) -> dict:
    r = app_client.get(f"/api/work-contexts/{project_id}")
    assert r.status_code == 200
    domains = [c for c in r.json()["contexts"] if c["level"] == "domain"]
    return domains[0]


def _create_epic(app_client, project_id: str, domain_id: str) -> dict:
    r = app_client.post(f"/api/work-contexts/{project_id}", json={
        "level": "epic", "name": "Test Epic", "parent_id": domain_id
    })
    assert r.status_code == 201
    return r.json()


def _create_story(app_client, project_id: str, epic_id: str) -> dict:
    r = app_client.post(f"/api/work-contexts/{project_id}", json={
        "level": "story", "name": "Test Story", "parent_id": epic_id
    })
    assert r.status_code == 201
    return r.json()


def _resolve(app_client, project_id: str, conflict_id: str, resolution: str, resolved_value=None, note=None):
    body = {"resolution": resolution}
    if resolved_value is not None:
        body["resolved_value"] = resolved_value
    if note is not None:
        body["note"] = note
    return app_client.post(f"/api/conflicts/{project_id}/{conflict_id}/resolve", json=body)


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_list_pending_conflicts(app_client):
    """GET list returns all pending conflicts for the project."""
    pid = _make_project(app_client, "list-conflicts")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    _insert_conflict(pid, story["id"], epic["id"], artifact_item_id="item-1")
    _insert_conflict(pid, story["id"], epic["id"], artifact_item_id="item-2")

    r = app_client.get(f"/api/conflicts/{pid}")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 2
    assert len(data["conflicts"]) == 2


def test_list_conflicts_filter_by_artifact_type(app_client):
    """artifact_type filter narrows results."""
    pid = _make_project(app_client, "list-filter")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    _insert_conflict(pid, story["id"], epic["id"], artifact_type="requirement")
    _insert_conflict(pid, story["id"], epic["id"], artifact_type="glossary_term")

    r = app_client.get(f"/api/conflicts/{pid}?artifact_type=requirement")
    assert r.status_code == 200
    data = r.json()
    assert data["count"] == 1
    assert data["conflicts"][0]["artifact_type"] == "requirement"


def test_get_conflict_detail(app_client):
    """GET detail returns all fields including incoming/existing values."""
    pid = _make_project(app_client, "detail-conflict")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    item_id = "req-detail-test"
    cid = _insert_conflict(pid, story["id"], epic["id"], artifact_item_id=item_id)

    r = app_client.get(f"/api/conflicts/{pid}/{cid}")
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == cid
    assert data["artifact_item_id"] == item_id
    assert "incoming_value" in data
    assert "existing_value" in data
    assert "conflict_reason" in data
    assert "source_context_name" in data


def test_get_conflict_not_found(app_client):
    """GET detail for non-existent conflict → 404."""
    pid = _make_project(app_client, "detail-404")
    r = app_client.get(f"/api/conflicts/{pid}/non-existent-id")
    assert r.status_code == 404


def test_resolve_accept_new(app_client):
    """accept_new resolution → conflict status becomes 'resolved_accept_new'."""
    pid = _make_project(app_client, "resolve-accept")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    item_id = str(uuid.uuid4())
    cid = _insert_conflict(pid, story["id"], epic["id"], artifact_item_id=item_id)

    r = _resolve(app_client, pid, cid, "accept_new")
    assert r.status_code == 200
    assert r.json()["conflict"]["status"] == "resolved_accept_new"
    assert _get_conflict_status(cid) == "resolved_accept_new"


def test_resolve_keep_old(app_client):
    """keep_old resolution → conflict status becomes 'resolved_keep_old'."""
    pid = _make_project(app_client, "resolve-keep")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    item_id = str(uuid.uuid4())
    cid = _insert_conflict(pid, story["id"], epic["id"], artifact_item_id=item_id)

    r = _resolve(app_client, pid, cid, "keep_old")
    assert r.status_code == 200
    assert r.json()["conflict"]["status"] == "resolved_keep_old"
    assert _get_conflict_status(cid) == "resolved_keep_old"


def test_resolve_edited_valid(app_client):
    """edited resolution with valid resolved_value → conflict status = 'resolved_edited'."""
    pid = _make_project(app_client, "resolve-edited")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    item_id = str(uuid.uuid4())
    cid = _insert_conflict(
        pid, story["id"], epic["id"],
        artifact_type="requirement",
        artifact_item_id=item_id,
        incoming={"id": item_id, "title": "Old Title", "description": ""},
    )

    r = _resolve(app_client, pid, cid, "edited", resolved_value={"id": item_id, "title": "Merged Title"})
    assert r.status_code == 200
    assert r.json()["conflict"]["status"] == "resolved_edited"
    assert _get_conflict_status(cid) == "resolved_edited"


def test_resolve_edited_invalid_schema(app_client):
    """edited resolution with missing required field → 422."""
    pid = _make_project(app_client, "resolve-edited-invalid")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    cid = _insert_conflict(pid, story["id"], epic["id"], artifact_type="glossary_term")

    # Missing required "definition" field
    r = _resolve(app_client, pid, cid, "edited", resolved_value={"term": "Foo"})
    assert r.status_code == 422


def test_resolve_edited_missing_resolved_value(app_client):
    """edited resolution without resolved_value → 422."""
    pid = _make_project(app_client, "resolve-edited-no-val")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    cid = _insert_conflict(pid, story["id"], epic["id"])

    r = _resolve(app_client, pid, cid, "edited")
    assert r.status_code == 422


def test_resolve_defer(app_client):
    """defer resolution → conflict status becomes 'deferred'."""
    pid = _make_project(app_client, "resolve-defer")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    cid = _insert_conflict(pid, story["id"], epic["id"])

    r = _resolve(app_client, pid, cid, "defer")
    assert r.status_code == 200
    assert r.json()["conflict"]["status"] == "deferred"
    assert _get_conflict_status(cid) == "deferred"


def test_defer_not_blocking_other_promotions(app_client):
    """After deferring the only conflict, count_pending_conflicts == 0."""
    pid = _make_project(app_client, "defer-not-blocking")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    cid = _insert_conflict(pid, story["id"], epic["id"])

    # Verify it starts as pending
    r = app_client.get(f"/api/conflicts/{pid}")
    assert r.json()["count"] == 1

    # Defer it
    r = _resolve(app_client, pid, cid, "defer")
    assert r.status_code == 200

    # Pending count should now be 0
    r = app_client.get(f"/api/conflicts/{pid}")
    assert r.json()["count"] == 0


def test_resolve_invalid_resolution_type(app_client):
    """Unknown resolution string → 422."""
    pid = _make_project(app_client, "resolve-invalid")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    cid = _insert_conflict(pid, story["id"], epic["id"])

    r = _resolve(app_client, pid, cid, "bananas")
    assert r.status_code == 422


def test_resolve_already_resolved(app_client):
    """Resolving an already-resolved conflict → 422."""
    pid = _make_project(app_client, "resolve-double")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    cid = _insert_conflict(pid, story["id"], epic["id"])

    _resolve(app_client, pid, cid, "keep_old")  # first resolution
    r = _resolve(app_client, pid, cid, "accept_new")  # second attempt
    assert r.status_code == 422


def test_audit_log_emitted_on_resolution(app_client):
    """Resolving a conflict emits an ArtifactAuditLog with event_type='conflict_resolved'."""
    pid = _make_project(app_client, "resolve-audit")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    item_id = str(uuid.uuid4())
    cid = _insert_conflict(pid, story["id"], epic["id"], artifact_item_id=item_id)

    _resolve(app_client, pid, cid, "keep_old")

    events = _get_audit_events(pid, item_id)
    assert "conflict_resolved" in events


def test_retry_result_after_last_conflict_resolved(app_client):
    """Resolving the last pending conflict returns a non-null retry_result."""
    pid = _make_project(app_client, "retry-after")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    item_id = str(uuid.uuid4())
    cid = _insert_conflict(pid, story["id"], epic["id"], artifact_item_id=item_id)

    r = _resolve(app_client, pid, cid, "keep_old")
    assert r.status_code == 200
    # The only conflict is now resolved → retry_result should be non-null
    data = r.json()
    assert data["retry_result"] is not None
    assert "promoted_count" in data["retry_result"]


def test_retry_promotes_conflict_pending_requirement(app_client):
    """After resolving last conflict, conflict_pending requirement is promoted."""
    pid = _make_project(app_client, "retry-promotes")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    # Insert a requirement in conflict_pending state in story context
    req_id = _insert_requirement_conflict_pending(pid, story["id"])

    # Insert a conflict row pointing to that requirement
    cid = _insert_conflict(
        pid, story["id"], epic["id"],
        artifact_type="requirement",
        artifact_item_id=req_id,
        incoming={"id": req_id, "title": "Test Req"},
    )

    r = _resolve(app_client, pid, cid, "keep_old")
    assert r.status_code == 200
    data = r.json()
    assert data["retry_result"] is not None
    assert data["retry_result"]["promoted_count"] >= 1


def test_actor_id_null_allowed(app_client):
    """No actor_id in request → resolution still succeeds (no auth required)."""
    pid = _make_project(app_client, "resolve-no-actor")
    domain = _get_domain(app_client, pid)
    epic = _create_epic(app_client, pid, domain["id"])
    story = _create_story(app_client, pid, epic["id"])

    cid = _insert_conflict(pid, story["id"], epic["id"])

    # The ResolveRequest has no actor_id field — this is intentional
    r = app_client.post(f"/api/conflicts/{pid}/{cid}/resolve", json={"resolution": "keep_old"})
    assert r.status_code == 200
