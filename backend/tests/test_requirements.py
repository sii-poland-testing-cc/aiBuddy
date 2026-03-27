"""
Tests for /api/requirements endpoints (Faza 2).
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _create_project(app_client, name: str = "req-test-project") -> str:
    r = app_client.post("/api/projects/", json={"name": name})
    assert r.status_code in (200, 201)
    return r.json()["project_id"]


def _mock_llm_for_requirements():
    """
    Build a MagicMock LLM whose acomplete returns valid extraction JSON on first
    call and valid validation JSON on subsequent calls.
    """
    extraction_response = json.dumps({
        "features": [
            {
                "title": "Payment Processing",
                "description": "Core payment functionality",
                "module": "payments",
                "requirements": [
                    {
                        "external_id": "FR-001",
                        "title": "Initiate bank transfer",
                        "description": "System shall allow users to initiate bank transfers.",
                        "level": "functional_req",
                        "source_type": "formal",
                        "taxonomy": {
                            "module": "payments",
                            "risk_level": "high",
                            "business_domain": "business_logic",
                        },
                        "testability": "high",
                        "confidence": 0.95,
                        "needs_review": False,
                        "review_reason": None,
                        "acceptance_criteria": [
                            {
                                "title": "Transfer within limit succeeds",
                                "description": "Transfer <= daily limit completes",
                                "testability": "high",
                                "confidence": 0.95,
                            }
                        ],
                    },
                    {
                        "external_id": "FR-002",
                        "title": "Transaction history",
                        "description": "System shall display transaction history.",
                        "level": "functional_req",
                        "source_type": "formal",
                        "taxonomy": {
                            "module": "payments",
                            "risk_level": "medium",
                            "business_domain": "data_integrity",
                        },
                        "testability": "high",
                        "confidence": 0.90,
                        "needs_review": False,
                        "review_reason": None,
                        "acceptance_criteria": [],
                    },
                ],
            }
        ],
        "gaps": [],
        "metadata": {
            "total_features": 1,
            "total_requirements": 2,
            "total_acceptance_criteria": 1,
            "formal_count": 2,
            "implicit_count": 0,
            "avg_confidence": 0.925,
            "low_confidence_count": 0,
        },
    })

    # Critic returns APPROVED so no refine call is triggered
    approved_response = json.dumps({"verdict": "APPROVED"})

    call_count = 0

    async def _side_effect(prompt, **kwargs):
        nonlocal call_count
        call_count += 1
        # First call = extraction, subsequent calls = reflection critic/refine
        if call_count == 1:
            return extraction_response
        return approved_response

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(side_effect=_side_effect)
    return mock_llm


def _run_extraction(app_client, project_id: str) -> dict:
    """Run requirements extraction with a mocked LLM and return the result data."""
    mock_llm = _mock_llm_for_requirements()

    # Mock is_indexed to return True so the workflow doesn't short-circuit
    # Mock retrieve_nodes to return empty list (context-free test)
    with patch("app.api.routes.requirements.get_llm", return_value=mock_llm), \
         patch(
             "app.agents.requirements_workflow.ContextBuilder.is_indexed",
             new_callable=AsyncMock,
             return_value=True,
         ), \
         patch(
             "app.agents.requirements_workflow.ContextBuilder.retrieve_nodes",
             new_callable=AsyncMock,
             return_value=[],
         ), \
         patch(
             "app.agents.requirements_workflow.ContextBuilder.get_indexed_filenames",
             return_value=[],
         ):
        r = app_client.post(
            f"/api/requirements/{project_id}/extract",
            json={"message": ""},
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
            elif ev.get("type") == "error":
                raise AssertionError(f"Extraction returned error: {ev['data']}")
        except json.JSONDecodeError:
            continue

    return result_data


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_requirements_extraction_mock(app_client):
    """
    POST /api/requirements/{project_id}/extract with mocked LLM should:
    - Return a result event with requirements list
    - Persist those requirements so GET returns them
    """
    project_id = _create_project(app_client)

    result = _run_extraction(app_client, project_id)

    # Result event must have requirements_flat
    assert "requirements_flat" in result, f"requirements_flat missing from result: {result.keys()}"
    reqs = result["requirements_flat"]
    assert isinstance(reqs, list)
    assert len(reqs) > 0, "Expected at least one requirement"

    # Each item must have id, title, level
    for req in reqs:
        assert "id" in req, f"Missing 'id' in requirement: {req}"
        assert "title" in req, f"Missing 'title' in requirement: {req}"
        assert "level" in req, f"Missing 'level' in requirement: {req}"

    # GET should return the same requirements
    resp = app_client.get(f"/api/requirements/{project_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] > 0, "GET returned no requirements after extraction"


def test_requirements_persist_and_list(app_client):
    """
    After extraction, both list endpoints should return non-empty results.
    """
    project_id = _create_project(app_client)
    _run_extraction(app_client, project_id)

    # Hierarchical list
    resp = app_client.get(f"/api/requirements/{project_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] > 0

    # Flat list
    resp_flat = app_client.get(f"/api/requirements/{project_id}/flat")
    assert resp_flat.status_code == 200
    data_flat = resp_flat.json()
    assert isinstance(data_flat["requirements"], list)
    assert len(data_flat["requirements"]) > 0

    # Each item has required fields
    for item in data_flat["requirements"]:
        assert "id" in item
        assert "title" in item
        assert "level" in item


def test_requirements_stats(app_client):
    """
    GET /api/requirements/{project_id}/stats should return statistics
    with total, by_level and by_source_type keys.
    """
    project_id = _create_project(app_client)
    _run_extraction(app_client, project_id)

    resp = app_client.get(f"/api/requirements/{project_id}/stats")
    assert resp.status_code == 200
    data = resp.json()

    assert data.get("has_requirements") is True
    assert "total" in data
    assert data["total"] > 0
    assert "by_level" in data
    assert isinstance(data["by_level"], dict)
    assert "by_source_type" in data
    assert isinstance(data["by_source_type"], dict)


def test_requirements_human_review(app_client):
    """
    PATCH /api/requirements/{project_id}/{req_id} should update human_reviewed flag.
    """
    project_id = _create_project(app_client)
    _run_extraction(app_client, project_id)

    # Get a requirement id from the flat list
    resp = app_client.get(f"/api/requirements/{project_id}/flat")
    assert resp.status_code == 200
    reqs = resp.json()["requirements"]
    assert len(reqs) > 0, "No requirements to review"

    req_id = reqs[0]["id"]

    # Mark as human reviewed
    patch_resp = app_client.patch(
        f"/api/requirements/{project_id}/{req_id}",
        json={"human_reviewed": True, "needs_review": False},
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["human_reviewed"] is True
    assert updated["needs_review"] is False


# ─── Phase 3: lifecycle / work_context_id tests ───────────────────────────────

def _run_extraction_with_context(app_client, project_id: str, work_context_id: str) -> dict:
    """Run extraction tagging requirements with a work_context_id."""
    mock_llm = _mock_llm_for_requirements()
    with patch("app.api.routes.requirements.get_llm", return_value=mock_llm), \
         patch(
             "app.agents.requirements_workflow.ContextBuilder.is_indexed",
             new_callable=AsyncMock,
             return_value=True,
         ), \
         patch(
             "app.agents.requirements_workflow.ContextBuilder.retrieve_nodes",
             new_callable=AsyncMock,
             return_value=[],
         ), \
         patch(
             "app.agents.requirements_workflow.ContextBuilder.get_indexed_filenames",
             return_value=[],
         ):
        r = app_client.post(
            f"/api/requirements/{project_id}/extract",
            json={"message": "", "work_context_id": work_context_id},
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
        except json.JSONDecodeError:
            continue
    return result_data


def test_extraction_without_work_context_id_is_promoted(app_client):
    """
    When no work_context_id is provided, requirements default to lifecycle_status='promoted'
    (backwards-compatible with all existing code).
    """
    project_id = _create_project(app_client)
    _run_extraction(app_client, project_id)

    resp = app_client.get(f"/api/requirements/{project_id}/flat")
    assert resp.status_code == 200
    reqs = resp.json()["requirements"]
    assert len(reqs) > 0
    for r in reqs:
        assert r["lifecycle_status"] == "promoted", (
            f"Expected 'promoted' for requirement without work_context_id, got {r['lifecycle_status']!r}"
        )
        assert r["work_context_id"] is None


def test_extraction_with_work_context_id_is_draft(app_client):
    """
    When work_context_id is provided, requirements are tagged as lifecycle_status='draft'.
    """
    project_id = _create_project(app_client)

    # Create a work context (domain → epic → story hierarchy)
    domain_resp = app_client.get(f"/api/work-contexts/{project_id}")
    assert domain_resp.status_code == 200
    contexts = domain_resp.json()["contexts"]
    assert len(contexts) > 0, "Expected a default domain to be auto-created"
    domain_id = contexts[0]["id"]

    # Create an epic under the domain
    epic_resp = app_client.post(
        f"/api/work-contexts/{project_id}",
        json={"level": "epic", "name": "Payment Epic", "parent_id": domain_id},
    )
    assert epic_resp.status_code == 201
    epic_id = epic_resp.json()["id"]

    _run_extraction_with_context(app_client, project_id, epic_id)

    # All requirements must be tagged with the epic ID and status=draft.
    # Pass include_pending=true — default view returns promoted items only.
    resp = app_client.get(
        f"/api/requirements/{project_id}/flat?work_context_id={epic_id}&include_pending=true"
    )
    assert resp.status_code == 200
    reqs = resp.json()["requirements"]
    assert len(reqs) > 0
    for r in reqs:
        assert r["lifecycle_status"] == "draft", (
            f"Expected 'draft' for requirement with work_context_id, got {r['lifecycle_status']!r}"
        )
        assert r["work_context_id"] == epic_id


def test_lifecycle_status_filter_on_flat_endpoint(app_client):
    """
    GET /flat?lifecycle_status=draft should only return draft requirements,
    and ?lifecycle_status=promoted only promoted ones.
    """
    project_id = _create_project(app_client)

    # First extraction: no context → promoted
    _run_extraction(app_client, project_id)

    resp_all = app_client.get(f"/api/requirements/{project_id}/flat")
    assert resp_all.status_code == 200
    total = len(resp_all.json()["requirements"])
    assert total > 0

    # All should be promoted
    resp_promoted = app_client.get(
        f"/api/requirements/{project_id}/flat?lifecycle_status=promoted"
    )
    assert resp_promoted.status_code == 200
    assert len(resp_promoted.json()["requirements"]) == total

    # None should be draft
    resp_draft = app_client.get(
        f"/api/requirements/{project_id}/flat?lifecycle_status=draft"
    )
    assert resp_draft.status_code == 200
    assert len(resp_draft.json()["requirements"]) == 0


def test_lifecycle_status_filter_on_hierarchical_endpoint(app_client):
    """
    GET /{project_id}?lifecycle_status=promoted should respect the filter.
    """
    project_id = _create_project(app_client)
    _run_extraction(app_client, project_id)

    resp = app_client.get(
        f"/api/requirements/{project_id}?lifecycle_status=promoted"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] > 0

    resp_draft = app_client.get(
        f"/api/requirements/{project_id}?lifecycle_status=draft"
    )
    assert resp_draft.status_code == 200
    assert resp_draft.json()["total"] == 0


def test_audit_log_created_on_extraction(app_client):
    """
    Each persisted requirement should produce an ArtifactAuditLog row with
    event_type='created'. Verify via DB introspection through the conftest db.
    """
    import asyncio
    from app.db.engine import AsyncSessionLocal
    from app.db.models import ArtifactAuditLog
    from sqlalchemy import select as sa_select

    project_id = _create_project(app_client)
    _run_extraction(app_client, project_id)

    async def _count_log_entries():
        async with AsyncSessionLocal() as db:
            stmt = sa_select(ArtifactAuditLog).where(
                ArtifactAuditLog.project_id == project_id,
                ArtifactAuditLog.event_type == "created",
                ArtifactAuditLog.artifact_type == "requirement",
            )
            rows = (await db.execute(stmt)).scalars().all()
            return len(rows)

    count = asyncio.get_event_loop().run_until_complete(_count_log_entries())
    assert count > 0, "Expected ArtifactAuditLog rows after extraction"


def test_requirements_adapter_detect_conflict_same_ext_id_different_title():
    """detect_conflict returns True when same external_id has very different titles."""
    from app.lifecycle.requirements_adapter import RequirementsAdapter
    adapter = RequirementsAdapter(db=None)  # type: ignore[arg-type]

    incoming = {"external_id": "FR-001", "title": "Initiate payment transfer", "description": ""}
    existing = {"external_id": "FR-001", "title": "Completely unrelated requirement about logging", "description": ""}

    has_conflict, reason = adapter.detect_conflict(incoming, existing)
    assert has_conflict is True
    assert "title_mismatch" in reason


def test_requirements_adapter_detect_conflict_same_title_different_ext_id():
    """detect_conflict returns True when same title appears under different external_ids."""
    from app.lifecycle.requirements_adapter import RequirementsAdapter
    adapter = RequirementsAdapter(db=None)  # type: ignore[arg-type]

    incoming = {"external_id": "FR-099", "title": "Initiate bank transfer", "description": "x"}
    existing = {"external_id": "FR-001", "title": "Initiate bank transfer", "description": "y"}

    has_conflict, reason = adapter.detect_conflict(incoming, existing)
    assert has_conflict is True
    assert reason == "duplicate_title"


def test_requirements_adapter_no_conflict_matching_requirement():
    """detect_conflict returns False when incoming and existing are effectively the same."""
    from app.lifecycle.requirements_adapter import RequirementsAdapter
    adapter = RequirementsAdapter(db=None)  # type: ignore[arg-type]

    incoming = {"external_id": "FR-001", "title": "Initiate bank transfer", "description": "Users can initiate transfers."}
    existing = {"external_id": "FR-001", "title": "Initiate bank transfer", "description": "Users can initiate transfers."}

    has_conflict, reason = adapter.detect_conflict(incoming, existing)
    assert has_conflict is False
    assert reason == ""


# ─── Phase 7: default promoted-only view + include_pending ───────────────────

def test_flat_default_returns_promoted_only(app_client):
    """
    GET /flat without filters returns only lifecycle_status='promoted' items.
    Items with other statuses (draft, etc.) are excluded by default.
    """
    project_id = _create_project(app_client)
    _run_extraction(app_client, project_id)

    resp = app_client.get(f"/api/requirements/{project_id}/flat")
    assert resp.status_code == 200
    reqs = resp.json()["requirements"]
    assert len(reqs) > 0
    for r in reqs:
        assert r["lifecycle_status"] == "promoted"


def test_flat_include_pending_shows_draft(app_client):
    """
    GET /flat?include_pending=true also returns draft/active/ready items.
    """
    project_id = _create_project(app_client)

    # Create a domain and epic, extract with work_context → draft requirements
    domain_resp = app_client.get(f"/api/work-contexts/{project_id}")
    domain_id = domain_resp.json()["contexts"][0]["id"]
    epic_resp = app_client.post(
        f"/api/work-contexts/{project_id}",
        json={"level": "epic", "name": "Epic A", "parent_id": domain_id},
    )
    epic_id = epic_resp.json()["id"]
    _run_extraction_with_context(app_client, project_id, epic_id)

    # Default view: promoted only → 0 (all are draft)
    resp_default = app_client.get(f"/api/requirements/{project_id}/flat")
    assert resp_default.status_code == 200
    assert len(resp_default.json()["requirements"]) == 0

    # With include_pending=true → should see draft items
    resp_pending = app_client.get(
        f"/api/requirements/{project_id}/flat?include_pending=true"
    )
    assert resp_pending.status_code == 200
    assert len(resp_pending.json()["requirements"]) > 0


def test_flat_work_context_id_filter(app_client):
    """
    GET /flat?work_context_id=X&include_pending=true returns only items for that context.
    """
    project_id = _create_project(app_client)

    domain_resp = app_client.get(f"/api/work-contexts/{project_id}")
    domain_id = domain_resp.json()["contexts"][0]["id"]
    epic_resp = app_client.post(
        f"/api/work-contexts/{project_id}",
        json={"level": "epic", "name": "Epic A", "parent_id": domain_id},
    )
    epic_id = epic_resp.json()["id"]
    _run_extraction_with_context(app_client, project_id, epic_id)

    resp = app_client.get(
        f"/api/requirements/{project_id}/flat?work_context_id={epic_id}&include_pending=true"
    )
    assert resp.status_code == 200
    reqs = resp.json()["requirements"]
    assert len(reqs) > 0
    for r in reqs:
        assert r["work_context_id"] == epic_id


# ─── Phase 3: D10 visibility manifest integration ────────────────────────────

def test_extraction_creates_visibility_rows(app_client):
    """
    After extraction, each requirement must have an ArtifactVisibility 'home' row
    with source_context_id == visible_in_context_id == work_context_id.
    """
    import asyncio
    from app.db.engine import AsyncSessionLocal
    from app.db.models import ArtifactVisibility
    from sqlalchemy import select as sa_select

    project_id = _create_project(app_client)

    # Create work context hierarchy
    domain_resp = app_client.get(f"/api/work-contexts/{project_id}")
    domain_id = domain_resp.json()["contexts"][0]["id"]
    epic_resp = app_client.post(
        f"/api/work-contexts/{project_id}",
        json={"level": "epic", "name": "Vis Epic", "parent_id": domain_id},
    )
    epic_id = epic_resp.json()["id"]

    _run_extraction_with_context(app_client, project_id, epic_id)

    async def _check():
        async with AsyncSessionLocal() as db:
            stmt = sa_select(ArtifactVisibility).where(
                ArtifactVisibility.project_id == project_id,
                ArtifactVisibility.artifact_type == "requirement",
            )
            rows = (await db.execute(stmt)).scalars().all()
            assert len(rows) > 0, "No visibility rows created"
            for row in rows:
                assert row.source_context_id == epic_id
                assert row.visible_in_context_id == epic_id
                assert row.lifecycle_status == "draft"

    asyncio.get_event_loop().run_until_complete(_check())


def test_extraction_without_context_creates_visibility_rows_with_null(app_client):
    """
    Extraction without work_context_id still creates visibility rows
    (source_context_id and visible_in_context_id are NULL — backwards compatible).
    """
    import asyncio
    from app.db.engine import AsyncSessionLocal
    from app.db.models import ArtifactVisibility
    from sqlalchemy import select as sa_select

    project_id = _create_project(app_client)
    _run_extraction(app_client, project_id)

    async def _check():
        async with AsyncSessionLocal() as db:
            stmt = sa_select(ArtifactVisibility).where(
                ArtifactVisibility.project_id == project_id,
                ArtifactVisibility.artifact_type == "requirement",
            )
            rows = (await db.execute(stmt)).scalars().all()
            assert len(rows) > 0, "No visibility rows for context-less extraction"
            for row in rows:
                assert row.source_context_id is None
                assert row.visible_in_context_id is None
                assert row.lifecycle_status == "promoted"

    asyncio.get_event_loop().run_until_complete(_check())


def test_source_origin_populated_from_source_references(app_client):
    """
    persist_requirements populates source_origin from source_references[0].
    """
    import asyncio
    from app.db.engine import AsyncSessionLocal
    from app.db.requirements_models import Requirement
    from app.services.requirements import persist_requirements
    from sqlalchemy import select as sa_select

    project_id = _create_project(app_client)

    async def _run():
        async with AsyncSessionLocal() as db:
            await persist_requirements(db, project_id, [
                {
                    "id": "req-src-1",
                    "title": "Req from file",
                    "level": "functional_req",
                    "source_type": "formal",
                    "source_references": ["srs_payment.docx", "another.pdf"],
                },
                {
                    "id": "req-src-2",
                    "title": "Req from URL",
                    "level": "functional_req",
                    "source_type": "formal",
                    "source_references": ["https://jira.example.com/PROJ-1"],
                },
                {
                    "id": "req-src-3",
                    "title": "Req without source",
                    "level": "functional_req",
                    "source_type": "implicit",
                    "source_references": [],
                },
            ])

        async with AsyncSessionLocal() as db:
            r1 = await db.get(Requirement, "req-src-1")
            assert r1.source_origin == "srs_payment.docx"
            assert r1.source_origin_type == "file"

            r2 = await db.get(Requirement, "req-src-2")
            assert r2.source_origin == "https://jira.example.com/PROJ-1"
            assert r2.source_origin_type == "url"

            r3 = await db.get(Requirement, "req-src-3")
            assert r3.source_origin is None
            assert r3.source_origin_type is None

    asyncio.get_event_loop().run_until_complete(_run())


def test_find_by_source_returns_matching_requirements(app_client):
    """find_by_source returns requirements extracted from a specific source file."""
    import asyncio
    from app.db.engine import AsyncSessionLocal
    from app.services.requirements import find_by_source, persist_requirements

    project_id = _create_project(app_client)

    async def _run():
        async with AsyncSessionLocal() as db:
            await persist_requirements(db, project_id, [
                {
                    "id": "fbs-1",
                    "title": "Req A from SRS",
                    "level": "functional_req",
                    "source_type": "formal",
                    "source_references": ["srs_v2.docx"],
                },
                {
                    "id": "fbs-2",
                    "title": "Req B from SRS",
                    "level": "functional_req",
                    "source_type": "formal",
                    "source_references": ["srs_v2.docx"],
                },
                {
                    "id": "fbs-3",
                    "title": "Req from other doc",
                    "level": "functional_req",
                    "source_type": "formal",
                    "source_references": ["other.pdf"],
                },
            ])

        async with AsyncSessionLocal() as db:
            results = await find_by_source(db, project_id, "srs_v2.docx")
            assert len(results) == 2
            ids = {r.id for r in results}
            assert ids == {"fbs-1", "fbs-2"}

            other = await find_by_source(db, project_id, "other.pdf")
            assert len(other) == 1
            assert other[0].id == "fbs-3"

            none = await find_by_source(db, project_id, "nonexistent.docx")
            assert len(none) == 0

    asyncio.get_event_loop().run_until_complete(_run())


def test_get_items_in_context_via_visibility(app_client):
    """
    RequirementsAdapter.get_items_in_context queries via artifact_visibility,
    not directly by Requirement.work_context_id.
    """
    import asyncio
    from app.db.engine import AsyncSessionLocal
    from app.db.models import ArtifactVisibility, WorkContext
    from app.db.requirements_models import Requirement
    from app.lifecycle.requirements_adapter import RequirementsAdapter

    project_id = _create_project(app_client)

    async def _run():
        async with AsyncSessionLocal() as db:
            # Create two contexts
            ctx_a = WorkContext(project_id=project_id, level="epic", name="Epic A", status="active")
            db.add(ctx_a)
            await db.flush()
            ctx_b = WorkContext(project_id=project_id, level="epic", name="Epic B", status="active")
            db.add(ctx_b)
            await db.flush()

            # Create a requirement in context A
            req = Requirement(
                id="vis-req-1",
                project_id=project_id,
                title="Payment FR",
                level="functional_req",
                source_type="formal",
                work_context_id=ctx_a.id,
                lifecycle_status="draft",
            )
            db.add(req)
            await db.flush()

            # Home visibility row (context A)
            db.add(ArtifactVisibility(
                project_id=project_id,
                artifact_type="requirement",
                artifact_item_id="vis-req-1",
                source_context_id=ctx_a.id,
                visible_in_context_id=ctx_a.id,
                lifecycle_status="draft",
            ))
            # Promoted visibility row (context B) — item visible in B too
            db.add(ArtifactVisibility(
                project_id=project_id,
                artifact_type="requirement",
                artifact_item_id="vis-req-1",
                source_context_id=ctx_a.id,
                visible_in_context_id=ctx_b.id,
                lifecycle_status="promoted",
            ))
            await db.commit()

        # Query via adapter
        async with AsyncSessionLocal() as db:
            adapter = RequirementsAdapter(db)

            # Context A should see the requirement
            items_a = await adapter.get_items_in_context(project_id, ctx_a.id)
            assert len(items_a) == 1
            assert items_a[0]["id"] == "vis-req-1"

            # Context B should also see it (via visibility row, NOT via work_context_id)
            items_b = await adapter.get_items_in_context(project_id, ctx_b.id)
            assert len(items_b) == 1
            assert items_b[0]["id"] == "vis-req-1"

    asyncio.get_event_loop().run_until_complete(_run())


def test_re_extraction_wipes_old_visibility_rows(app_client):
    """
    Running extraction twice should wipe old visibility rows and create fresh ones.
    """
    import asyncio
    from app.db.engine import AsyncSessionLocal
    from app.db.models import ArtifactVisibility
    from sqlalchemy import select as sa_select, func

    project_id = _create_project(app_client)

    # First extraction
    _run_extraction(app_client, project_id)

    async def _count_vis():
        async with AsyncSessionLocal() as db:
            stmt = sa_select(func.count()).select_from(ArtifactVisibility).where(
                ArtifactVisibility.project_id == project_id,
                ArtifactVisibility.artifact_type == "requirement",
            )
            return (await db.execute(stmt)).scalar()

    count_1 = asyncio.get_event_loop().run_until_complete(_count_vis())
    assert count_1 > 0

    # Second extraction (full re-extract wipes and recreates)
    _run_extraction(app_client, project_id)

    count_2 = asyncio.get_event_loop().run_until_complete(_count_vis())
    assert count_2 == count_1, (
        f"Expected same count after re-extract ({count_1}), got {count_2}"
    )


# ─── Phase 7: Visibility-based query tests ───────────────────────────────────

def test_list_requirements_uses_visibility_join(app_client):
    """
    GET /api/requirements/{project_id} returns requirements visible via
    ArtifactVisibility JOIN, not via direct Requirement.work_context_id.
    A requirement promoted from context A to context B is visible in B
    without changing its work_context_id.
    """
    import asyncio
    from app.db.engine import AsyncSessionLocal
    from app.db.models import ArtifactVisibility, WorkContext
    from app.db.requirements_models import Requirement

    project_id = _create_project(app_client)

    async def _setup():
        async with AsyncSessionLocal() as db:
            ctx_a = WorkContext(project_id=project_id, level="epic", name="Story A", status="active")
            db.add(ctx_a)
            await db.flush()
            ctx_b = WorkContext(project_id=project_id, level="epic", name="Epic B", status="active")
            db.add(ctx_b)
            await db.flush()

            req = Requirement(
                id="vis-join-req",
                project_id=project_id,
                title="Visible via JOIN",
                level="functional_req",
                source_type="formal",
                work_context_id=ctx_a.id,
                lifecycle_status="promoted",
            )
            db.add(req)
            await db.flush()

            # Home visibility row (context A)
            db.add(ArtifactVisibility(
                project_id=project_id,
                artifact_type="requirement",
                artifact_item_id="vis-join-req",
                source_context_id=ctx_a.id,
                visible_in_context_id=ctx_a.id,
                lifecycle_status="draft",
            ))
            # Promoted to context B
            db.add(ArtifactVisibility(
                project_id=project_id,
                artifact_type="requirement",
                artifact_item_id="vis-join-req",
                source_context_id=ctx_a.id,
                visible_in_context_id=ctx_b.id,
                lifecycle_status="promoted",
            ))
            await db.commit()
            return ctx_a.id, ctx_b.id

    ctx_a_id, ctx_b_id = asyncio.get_event_loop().run_until_complete(_setup())

    # Query context B — should see the requirement via visibility JOIN
    resp = app_client.get(
        f"/api/requirements/{project_id}/flat?work_context_id={ctx_b_id}"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["requirements"][0]["id"] == "vis-join-req"

    # Query context A with include_pending — should see via home visibility row
    resp_a = app_client.get(
        f"/api/requirements/{project_id}/flat?work_context_id={ctx_a_id}&include_pending=true"
    )
    assert resp_a.status_code == 200
    assert resp_a.json()["total"] == 1


def test_promoted_items_visible_at_both_source_and_target(app_client):
    """
    A requirement promoted from source context to target context is visible
    at BOTH contexts simultaneously (no data duplication — same canonical item).
    """
    import asyncio
    from app.db.engine import AsyncSessionLocal
    from app.db.models import ArtifactVisibility, WorkContext
    from app.db.requirements_models import Requirement

    project_id = _create_project(app_client)

    async def _setup():
        async with AsyncSessionLocal() as db:
            src = WorkContext(project_id=project_id, level="story", name="Story Src", status="ready")
            db.add(src)
            await db.flush()
            tgt = WorkContext(project_id=project_id, level="epic", name="Epic Tgt", status="active")
            db.add(tgt)
            await db.flush()

            req = Requirement(
                id="dual-vis-req",
                project_id=project_id,
                title="Dual visibility req",
                level="functional_req",
                source_type="formal",
                work_context_id=src.id,
                lifecycle_status="promoted",
            )
            db.add(req)
            await db.flush()

            # Visible at source (promoted)
            db.add(ArtifactVisibility(
                project_id=project_id,
                artifact_type="requirement",
                artifact_item_id="dual-vis-req",
                source_context_id=src.id,
                visible_in_context_id=src.id,
                lifecycle_status="promoted",
            ))
            # Visible at target (promoted)
            db.add(ArtifactVisibility(
                project_id=project_id,
                artifact_type="requirement",
                artifact_item_id="dual-vis-req",
                source_context_id=src.id,
                visible_in_context_id=tgt.id,
                lifecycle_status="promoted",
            ))
            await db.commit()
            return src.id, tgt.id

    src_id, tgt_id = asyncio.get_event_loop().run_until_complete(_setup())

    # Both contexts see the same requirement
    resp_src = app_client.get(f"/api/requirements/{project_id}/flat?work_context_id={src_id}")
    resp_tgt = app_client.get(f"/api/requirements/{project_id}/flat?work_context_id={tgt_id}")

    assert resp_src.status_code == 200
    assert resp_tgt.status_code == 200
    assert resp_src.json()["total"] == 1
    assert resp_tgt.json()["total"] == 1
    assert resp_src.json()["requirements"][0]["id"] == "dual-vis-req"
    assert resp_tgt.json()["requirements"][0]["id"] == "dual-vis-req"


def test_default_query_returns_promoted_only(app_client):
    """
    Default query (no work_context_id) returns same results as pre-refactor:
    only lifecycle_status="promoted" items.
    """
    project_id = _create_project(app_client)
    _run_extraction(app_client, project_id)

    resp = app_client.get(f"/api/requirements/{project_id}/flat")
    assert resp.status_code == 200
    data = resp.json()
    # Extraction without work_context creates "promoted" visibility rows
    assert data["total"] > 0

    # All items should have lifecycle_status="promoted"
    for req in data["requirements"]:
        assert req["lifecycle_status"] == "promoted"


def test_archived_and_conflict_pending_excluded(app_client):
    """
    Requirements with archived or conflict_pending visibility status
    are excluded from default queries.
    """
    import asyncio
    from app.db.engine import AsyncSessionLocal
    from app.db.models import ArtifactVisibility, WorkContext
    from app.db.requirements_models import Requirement

    project_id = _create_project(app_client)

    async def _setup():
        async with AsyncSessionLocal() as db:
            ctx = WorkContext(project_id=project_id, level="epic", name="Excl Test", status="active")
            db.add(ctx)
            await db.flush()

            for i, status in enumerate(["promoted", "archived", "conflict_pending"]):
                req = Requirement(
                    id=f"excl-req-{i}",
                    project_id=project_id,
                    title=f"Req {status}",
                    level="functional_req",
                    source_type="formal",
                    work_context_id=ctx.id,
                    lifecycle_status=status,
                )
                db.add(req)
                await db.flush()
                db.add(ArtifactVisibility(
                    project_id=project_id,
                    artifact_type="requirement",
                    artifact_item_id=f"excl-req-{i}",
                    source_context_id=ctx.id,
                    visible_in_context_id=ctx.id,
                    lifecycle_status=status,
                ))
            await db.commit()
            return ctx.id

    ctx_id = asyncio.get_event_loop().run_until_complete(_setup())

    resp = app_client.get(f"/api/requirements/{project_id}/flat?work_context_id={ctx_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["requirements"][0]["id"] == "excl-req-0"


def test_source_impact_endpoint(app_client):
    """
    GET /api/artifacts/{project_id}/by-source returns items from a specific source.
    """
    import asyncio
    from app.db.engine import AsyncSessionLocal
    from app.db.models import ArtifactVisibility

    project_id = _create_project(app_client)

    async def _setup():
        async with AsyncSessionLocal() as db:
            db.add(ArtifactVisibility(
                project_id=project_id,
                artifact_type="graph_node",
                artifact_item_id="node-1",
                lifecycle_status="promoted",
                source_origin="srs_v3.docx",
                source_origin_type="file",
            ))
            db.add(ArtifactVisibility(
                project_id=project_id,
                artifact_type="glossary_term",
                artifact_item_id="payment",
                lifecycle_status="promoted",
                source_origin="srs_v3.docx",
                source_origin_type="file",
            ))
            db.add(ArtifactVisibility(
                project_id=project_id,
                artifact_type="graph_node",
                artifact_item_id="node-2",
                lifecycle_status="promoted",
                source_origin="other.pdf",
                source_origin_type="file",
            ))
            await db.commit()

    asyncio.get_event_loop().run_until_complete(_setup())

    resp = app_client.get(
        f"/api/artifacts/{project_id}/by-source?source_origin=srs_v3.docx"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert data["source_origin"] == "srs_v3.docx"
    assert "graph_node" in data["by_type"]
    assert "glossary_term" in data["by_type"]
    assert len(data["by_type"]["graph_node"]) == 1
    assert len(data["by_type"]["glossary_term"]) == 1

    # Filter by artifact_type
    resp2 = app_client.get(
        f"/api/artifacts/{project_id}/by-source?source_origin=srs_v3.docx&artifact_type=graph_node"
    )
    assert resp2.status_code == 200
    assert resp2.json()["total"] == 1

    # No results for nonexistent source
    resp3 = app_client.get(
        f"/api/artifacts/{project_id}/by-source?source_origin=nonexistent.pdf"
    )
    assert resp3.status_code == 200
    assert resp3.json()["total"] == 0


def test_hierarchical_query_via_visibility(app_client):
    """
    GET /api/requirements/{project_id} (hierarchical) also uses visibility JOIN.
    """
    import asyncio
    from app.db.engine import AsyncSessionLocal
    from app.db.models import ArtifactVisibility, WorkContext
    from app.db.requirements_models import Requirement

    project_id = _create_project(app_client)

    async def _setup():
        async with AsyncSessionLocal() as db:
            ctx = WorkContext(project_id=project_id, level="epic", name="Hier Test", status="active")
            db.add(ctx)
            await db.flush()

            feature = Requirement(
                id="hier-feat",
                project_id=project_id,
                title="Feature X",
                level="feature",
                source_type="formal",
                work_context_id=ctx.id,
                lifecycle_status="promoted",
            )
            db.add(feature)
            await db.flush()

            child = Requirement(
                id="hier-req",
                project_id=project_id,
                parent_id="hier-feat",
                title="FR under Feature X",
                level="functional_req",
                source_type="formal",
                work_context_id=ctx.id,
                lifecycle_status="promoted",
            )
            db.add(child)
            await db.flush()

            for req_id in ["hier-feat", "hier-req"]:
                db.add(ArtifactVisibility(
                    project_id=project_id,
                    artifact_type="requirement",
                    artifact_item_id=req_id,
                    source_context_id=ctx.id,
                    visible_in_context_id=ctx.id,
                    lifecycle_status="promoted",
                ))
            await db.commit()
            return ctx.id

    ctx_id = asyncio.get_event_loop().run_until_complete(_setup())

    resp = app_client.get(f"/api/requirements/{project_id}?work_context_id={ctx_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 2
    assert len(data["features"]) == 1
    assert data["features"][0]["id"] == "hier-feat"
    assert len(data["features"][0].get("children", [])) == 1
