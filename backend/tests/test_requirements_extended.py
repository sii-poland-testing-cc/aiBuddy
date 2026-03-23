"""
Extended tests for Faza 2 Requirements — edge cases + unit tests
=================================================================
Run alongside existing test_requirements.py:
    pytest tests/test_requirements_extended.py -v
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── Helpers (reuse pattern from test_requirements.py) ────────────────────────

def _create_project(app_client, name: str = "req-ext-test") -> str:
    r = app_client.post("/api/projects/", json={"name": name})
    assert r.status_code in (200, 201)
    return r.json()["project_id"]


def _mock_llm(extraction_json: str, validation_json: str | None = None):
    """Build mock LLM. First acomplete → extraction, second → validation."""
    if validation_json is None:
        validation_json = json.dumps({
            "validated_requirements": [], "duplicates": [],
            "additional_gaps": [], "overall_assessment": {
                "completeness_rating": "high", "testability_rating": "high",
                "recommendation": "OK",
            },
        })
    call_count = 0
    async def _side(prompt, **kwargs):
        nonlocal call_count
        call_count += 1
        return extraction_json if call_count == 1 else validation_json
    m = MagicMock()
    m.acomplete = AsyncMock(side_effect=_side)
    return m


def _run_extraction(app_client, project_id: str, mock_llm=None) -> dict:
    if mock_llm is None:
        mock_llm = _mock_llm(_STANDARD_EXTRACTION)
    with patch("app.api.routes.requirements.get_llm", return_value=mock_llm), \
         patch("app.agents.requirements_workflow.ContextBuilder.is_indexed",
               new_callable=AsyncMock, return_value=True), \
         patch("app.agents.requirements_workflow.ContextBuilder.build_with_sources",
               new_callable=AsyncMock, return_value=("Docs with FR-001 FR-002.", [])):
        r = app_client.post(f"/api/requirements/{project_id}/extract", json={"message": ""})
    assert r.status_code == 200
    for line in r.text.splitlines():
        if not line.startswith("data: "): continue
        payload = line[6:].strip()
        if payload == "[DONE]": break
        try:
            ev = json.loads(payload)
            if ev.get("type") == "result": return ev["data"]
        except json.JSONDecodeError: continue
    return {}


_STANDARD_EXTRACTION = json.dumps({
    "features": [{
        "title": "Payments", "description": "Payment module", "module": "payments",
        "requirements": [
            {"external_id": "FR-001", "title": "Bank transfer", "description": "Initiate transfers.",
             "level": "functional_req", "source_type": "formal",
             "taxonomy": {"module": "payments", "risk_level": "high", "business_domain": "business_logic"},
             "testability": "high", "confidence": 0.95, "needs_review": False,
             "review_reason": None, "acceptance_criteria": [
                 {"title": "Transfer within limit", "description": "Amount <= limit OK", "testability": "high", "confidence": 0.95}
             ]},
            {"external_id": "FR-002", "title": "History", "description": "Show 12 months history.",
             "level": "functional_req", "source_type": "formal",
             "taxonomy": {"module": "payments", "risk_level": "medium", "business_domain": "data_integrity"},
             "testability": "high", "confidence": 0.90, "needs_review": False,
             "review_reason": None, "acceptance_criteria": []},
        ],
    }, {
        "title": "Auth", "description": "Authentication", "module": "auth",
        "requirements": [
            {"external_id": None, "title": "Password complexity", "description": "Min 8 chars.",
             "level": "functional_req", "source_type": "implicit",
             "taxonomy": {"module": "auth", "risk_level": "high", "business_domain": "security"},
             "testability": "medium", "confidence": 0.55, "needs_review": True,
             "review_reason": "Implicit requirement", "acceptance_criteria": []},
        ],
    }],
    "gaps": [{"area": "Session timeout", "description": "No timeout spec", "severity": "high"}],
    "metadata": {"total_features": 2, "total_requirements": 3,
                 "total_acceptance_criteria": 1, "formal_count": 2,
                 "implicit_count": 1, "avg_confidence": 0.80, "low_confidence_count": 1},
})


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_extraction_no_m1_context(app_client):
    """When M1 hasn't been run, extraction returns empty features gracefully."""
    project_id = _create_project(app_client, "no-m1")
    with patch("app.api.routes.requirements.get_llm", return_value=None), \
         patch("app.agents.requirements_workflow.ContextBuilder.is_indexed",
               new_callable=AsyncMock, return_value=False):
        r = app_client.post(f"/api/requirements/{project_id}/extract", json={"message": ""})
    assert r.status_code == 200
    result = {}
    for line in r.text.splitlines():
        if not line.startswith("data: "): continue
        p = line[6:].strip()
        if p == "[DONE]": break
        try:
            ev = json.loads(p)
            if ev.get("type") == "result": result = ev["data"]
        except: continue
    assert result.get("features") == [] or result.get("requirements_flat") == []


def test_re_extraction_overwrites(app_client):
    """Running extraction twice replaces previous requirements."""
    project_id = _create_project(app_client, "re-extract")

    # First extraction
    _run_extraction(app_client, project_id)
    resp1 = app_client.get(f"/api/requirements/{project_id}/stats")
    total_1 = resp1.json()["total"]
    assert total_1 > 0

    # Second extraction with different data
    small_llm = _mock_llm(json.dumps({
        "features": [{"title": "Tiny", "module": "x", "description": "",
            "requirements": [{"external_id": "FR-099", "title": "Only one",
             "description": "d", "level": "functional_req", "source_type": "formal",
             "taxonomy": {}, "testability": "high", "confidence": 0.9,
             "needs_review": False, "review_reason": None, "acceptance_criteria": []}]}],
        "gaps": [], "metadata": {"total_features": 1, "total_requirements": 1,
         "total_acceptance_criteria": 0, "formal_count": 1, "implicit_count": 0,
         "avg_confidence": 0.9, "low_confidence_count": 0},
    }))
    _run_extraction(app_client, project_id, small_llm)

    resp2 = app_client.get(f"/api/requirements/{project_id}/stats")
    total_2 = resp2.json()["total"]
    # Should have fewer requirements (1 feature + 1 FR = 2 rows)
    assert total_2 < total_1, f"Expected fewer reqs after re-extract: {total_2} vs {total_1}"


def test_delete_requirements(app_client):
    """DELETE /api/requirements/{project_id} wipes all requirements."""
    project_id = _create_project(app_client, "delete-test")
    _run_extraction(app_client, project_id)

    # Verify we have data
    stats = app_client.get(f"/api/requirements/{project_id}/stats").json()
    assert stats["total"] > 0

    # Delete
    r = app_client.delete(f"/api/requirements/{project_id}")
    assert r.status_code == 200
    assert r.json()["deleted"] > 0

    # Verify empty
    stats2 = app_client.get(f"/api/requirements/{project_id}/stats").json()
    assert stats2.get("has_requirements") is False


def test_gaps_endpoint(app_client):
    """GET /api/requirements/{project_id}/gaps returns gaps from extraction."""
    project_id = _create_project(app_client, "gaps-test")
    # Need to create a project in DB first
    _run_extraction(app_client, project_id)

    resp = app_client.get(f"/api/requirements/{project_id}/gaps")
    assert resp.status_code == 200
    data = resp.json()
    assert "gaps" in data
    # Our mock extraction includes 1 gap
    assert isinstance(data["gaps"], list)


def test_filter_by_level(app_client):
    """GET /api/requirements?level=functional_req returns only FRs."""
    project_id = _create_project(app_client, "filter-level")
    _run_extraction(app_client, project_id)

    resp = app_client.get(f"/api/requirements/{project_id}?level=functional_req")
    assert resp.status_code == 200
    data = resp.json()
    for req in data["requirements"]:
        assert req["level"] == "functional_req"


def test_filter_needs_review(app_client):
    """GET /api/requirements?needs_review=true returns only flagged items."""
    project_id = _create_project(app_client, "filter-review")
    _run_extraction(app_client, project_id)

    resp = app_client.get(f"/api/requirements/{project_id}?needs_review=true")
    assert resp.status_code == 200
    data = resp.json()
    # Our mock has 1 implicit requirement with confidence 0.55 → needs_review
    for req in data.get("requirements", []):
        assert req["needs_review"] is True


def test_hierarchy_has_children(app_client):
    """Hierarchical listing builds parent-children relationships."""
    project_id = _create_project(app_client, "hierarchy-test")
    _run_extraction(app_client, project_id)

    resp = app_client.get(f"/api/requirements/{project_id}")
    assert resp.status_code == 200
    data = resp.json()

    features = data.get("features", [])
    assert len(features) >= 1, "Should have at least 1 feature"

    # At least one feature should have children (requirements)
    has_children = any("children" in f and len(f["children"]) > 0 for f in features)
    assert has_children, "At least one feature should have child requirements"


def test_human_review_clears_flags(app_client):
    """Marking human_reviewed=true should clear needs_review and review_reason."""
    project_id = _create_project(app_client, "review-clear")
    _run_extraction(app_client, project_id)

    # Find a needs_review item
    flat = app_client.get(f"/api/requirements/{project_id}/flat").json()
    flagged = [r for r in flat["requirements"] if r["needs_review"]]

    if not flagged:
        pytest.skip("No flagged requirements in mock data")

    req_id = flagged[0]["id"]
    resp = app_client.patch(
        f"/api/requirements/{project_id}/{req_id}",
        json={"human_reviewed": True},
    )
    assert resp.status_code == 200
    updated = resp.json()
    assert updated["human_reviewed"] is True
    assert updated["needs_review"] is False
    assert updated["review_reason"] is None


def test_patch_nonexistent_returns_404(app_client):
    """PATCH with fake requirement_id returns 404."""
    project_id = _create_project(app_client, "patch-404")
    resp = app_client.patch(
        f"/api/requirements/{project_id}/fake-id-does-not-exist",
        json={"title": "Updated"},
    )
    assert resp.status_code == 404


def test_stats_by_source_type(app_client):
    """Stats should report formal vs implicit counts."""
    project_id = _create_project(app_client, "stats-source")
    _run_extraction(app_client, project_id)

    stats = app_client.get(f"/api/requirements/{project_id}/stats").json()
    by_source = stats.get("by_source_type", {})
    # Our mock has 2 formal + 1 implicit
    assert "formal" in by_source or "implicit" in by_source


def test_stats_empty_project(app_client):
    """Stats for project with no requirements returns has_requirements=False."""
    project_id = _create_project(app_client, "stats-empty")
    stats = app_client.get(f"/api/requirements/{project_id}/stats").json()
    assert stats.get("has_requirements") is False


# ─── Unit tests: workflow internals ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_workflow_mock_mode():
    """RequirementsWorkflow with llm=None returns mock data without error."""
    from app.agents.requirements_workflow import RequirementsWorkflow

    with patch("app.agents.requirements_workflow.ContextBuilder.is_indexed",
               new_callable=AsyncMock, return_value=True), \
         patch("app.agents.requirements_workflow.ContextBuilder.build_with_sources",
               new_callable=AsyncMock, return_value=("Mock docs.", [])):
        wf = RequirementsWorkflow(llm=None, timeout=30)
        handler = wf.run(project_id="unit-test", user_message="")
        async for _ in handler.stream_events():
            pass
        result = await handler

    assert "features" in result
    assert "requirements_flat" in result
    assert len(result["features"]) > 0
    assert result["metadata"]["total_requirements"] > 0


@pytest.mark.asyncio
async def test_workflow_compute_metadata():
    """_compute_metadata correctly aggregates stats."""
    from app.agents.requirements_workflow import RequirementsWorkflow

    wf = RequirementsWorkflow(llm=None, timeout=10)
    features = [
        {"requirements": [
            {"source_type": "formal", "confidence": 0.9, "acceptance_criteria": [{"a": 1}]},
            {"source_type": "implicit", "confidence": 0.5, "acceptance_criteria": []},
        ]},
        {"requirements": [
            {"source_type": "formal", "confidence": 0.8, "acceptance_criteria": []},
        ]},
    ]
    meta = wf._compute_metadata(features)

    assert meta["total_features"] == 2
    assert meta["total_requirements"] == 3
    assert meta["total_acceptance_criteria"] == 1
    assert meta["formal_count"] == 2
    assert meta["implicit_count"] == 1
    assert meta["low_confidence_count"] == 1  # 0.5 < 0.7
    assert 0.7 <= meta["avg_confidence"] <= 0.75  # avg(0.9, 0.5, 0.8) ≈ 0.73


@pytest.mark.asyncio
async def test_workflow_deduplicate_context():
    """_deduplicate_context removes duplicate paragraphs."""
    from app.agents.requirements_workflow import RequirementsWorkflow

    wf = RequirementsWorkflow(llm=None, timeout=10)
    text = "Paragraph one.\n\nParagraph two.\n\nParagraph one.\n\nParagraph three."
    result = wf._deduplicate_context(text, max_chars=10000)

    # "Paragraph one." should appear only once
    assert result.count("Paragraph one.") == 1
    assert "Paragraph two." in result
    assert "Paragraph three." in result
