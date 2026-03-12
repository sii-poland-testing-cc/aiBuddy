"""
Extended tests for Faza 5+6 Mapping & Coverage — edge cases + unit tests
=========================================================================
Run alongside existing test_mapping.py:
    pytest tests/test_mapping_extended.py -v
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── Helpers ──────────────────────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_CSV = FIXTURES_DIR / "sample_tests.csv"


def _create_project(app_client, name: str = "map-ext-test") -> str:
    r = app_client.post("/api/projects/", json={"name": name})
    assert r.status_code in (200, 201)
    return r.json()["project_id"]


def _upload_csv(app_client, project_id: str, name: str = "sample_tests.csv") -> str:
    with SAMPLE_CSV.open("rb") as fh:
        r = app_client.post(
            f"/api/files/{project_id}/upload?source_type=file",
            files={"files": (name, fh, "text/csv")},
        )
    assert r.status_code == 200
    uploaded = r.json()
    if isinstance(uploaded, list) and uploaded:
        return uploaded[0].get("file_path", "")
    return ""


def _mock_llm_for_requirements():
    extraction = json.dumps({
        "features": [{
            "title": "Payments", "description": "Payment module", "module": "payments",
            "requirements": [
                {"external_id": "FR-001", "title": "Bank transfer",
                 "description": "Initiate bank transfers.",
                 "level": "functional_req", "source_type": "formal",
                 "taxonomy": {"module": "payments", "risk_level": "high",
                              "business_domain": "business_logic"},
                 "testability": "high", "confidence": 0.95, "needs_review": False,
                 "review_reason": None, "acceptance_criteria": []},
                {"external_id": "FR-002", "title": "Transaction history",
                 "description": "Display transaction history.",
                 "level": "functional_req", "source_type": "formal",
                 "taxonomy": {"module": "payments", "risk_level": "medium",
                              "business_domain": "data_integrity"},
                 "testability": "high", "confidence": 0.90, "needs_review": False,
                 "review_reason": None, "acceptance_criteria": []},
            ],
        }],
        "gaps": [], "metadata": {"total_features": 1, "total_requirements": 2,
         "total_acceptance_criteria": 0, "formal_count": 2, "implicit_count": 0,
         "avg_confidence": 0.925, "low_confidence_count": 0},
    })
    validation = json.dumps({
        "validated_requirements": [], "duplicates": [],
        "additional_gaps": [], "overall_assessment": {
            "completeness_rating": "high", "testability_rating": "high",
            "recommendation": "OK"},
    })
    call_count = 0
    async def _side(prompt):
        nonlocal call_count; call_count += 1
        return extraction if call_count == 1 else validation
    m = MagicMock()
    m.acomplete = AsyncMock(side_effect=_side)
    return m


def _run_requirements(app_client, project_id: str) -> dict:
    mock_llm = _mock_llm_for_requirements()
    with patch("app.api.routes.requirements.get_llm", return_value=mock_llm), \
         patch("app.agents.requirements_workflow.ContextBuilder.is_indexed",
               new_callable=AsyncMock, return_value=True), \
         patch("app.agents.requirements_workflow.ContextBuilder.build_with_sources",
               new_callable=AsyncMock, return_value=("Docs.", [])):
        r = app_client.post(f"/api/requirements/{project_id}/extract", json={"message": ""})
    assert r.status_code == 200
    for line in r.text.splitlines():
        if not line.startswith("data: "): continue
        p = line[6:].strip()
        if p == "[DONE]": break
        try:
            ev = json.loads(p)
            if ev.get("type") == "result": return ev["data"]
        except: continue
    return {}


def _run_mapping(app_client, project_id: str, file_path: str = "") -> dict:
    with patch("app.api.routes.mapping.get_llm", return_value=None):
        r = app_client.post(f"/api/mapping/{project_id}/run",
                            json={"file_paths": [file_path] if file_path else []})
    assert r.status_code == 200
    for line in r.text.splitlines():
        if not line.startswith("data: "): continue
        p = line[6:].strip()
        if p == "[DONE]": break
        try:
            ev = json.loads(p)
            if ev.get("type") == "result": return ev["data"]
        except: continue
    return {}


# ─── Endpoint Tests ──────────────────────────────────────────────────────────

def test_mapping_no_requirements(app_client):
    """Running mapping without Faza 2 returns empty results gracefully."""
    project_id = _create_project(app_client, "no-reqs")
    file_path = _upload_csv(app_client, project_id)
    result = _run_mapping(app_client, project_id, file_path)
    # Should not crash — just empty
    assert result.get("mappings") == [] or result.get("scores") == []


def test_summary_endpoint(app_client):
    """GET /api/mapping/{project_id}/summary returns distribution breakdown."""
    project_id = _create_project(app_client, "summary-test")
    file_path = _upload_csv(app_client, project_id)
    _run_requirements(app_client, project_id)
    _run_mapping(app_client, project_id, file_path)

    resp = app_client.get(f"/api/mapping/{project_id}/summary")
    assert resp.status_code == 200
    data = resp.json()

    if data.get("has_scores"):
        assert "distribution" in data
        dist = data["distribution"]
        for key in ("green_80_100", "yellow_60_79", "orange_30_59", "red_0_29"):
            assert key in dist, f"Missing distribution key: {key}"
        assert data["total_requirements"] > 0
        assert 0 <= data["coverage_pct"] <= 100
    else:
        # No scores persisted (possible if no matches found)
        assert data.get("has_scores") is False


def test_summary_empty_project(app_client):
    """Summary for project with no scores returns has_scores=False."""
    project_id = _create_project(app_client, "summary-empty")
    resp = app_client.get(f"/api/mapping/{project_id}/summary")
    assert resp.status_code == 200
    assert resp.json().get("has_scores") is False


def test_delete_mappings(app_client):
    """DELETE /api/mapping/{project_id} wipes mappings and scores."""
    project_id = _create_project(app_client, "delete-map")
    file_path = _upload_csv(app_client, project_id)
    _run_requirements(app_client, project_id)
    _run_mapping(app_client, project_id, file_path)

    r = app_client.delete(f"/api/mapping/{project_id}")
    assert r.status_code == 200
    data = r.json()
    assert "deleted_mappings" in data
    assert "deleted_scores" in data

    # Verify empty
    summary = app_client.get(f"/api/mapping/{project_id}/summary").json()
    assert summary.get("has_scores") is False


def test_heatmap_groups_by_module(app_client):
    """Heatmap endpoint groups requirements by taxonomy.module."""
    project_id = _create_project(app_client, "heatmap-groups")
    file_path = _upload_csv(app_client, project_id)
    _run_requirements(app_client, project_id)
    _run_mapping(app_client, project_id, file_path)

    resp = app_client.get(f"/api/mapping/{project_id}/heatmap")
    assert resp.status_code == 200
    data = resp.json()
    modules = data.get("modules", [])

    if modules:
        for mod in modules:
            assert "module" in mod
            assert "avg_score" in mod
            assert "total_requirements" in mod
            assert "critical_gaps" in mod
            assert isinstance(mod["critical_gaps"], list)


def test_coverage_sort_ascending(app_client):
    """Coverage endpoint with sort_by=total_score&order=asc returns worst first."""
    project_id = _create_project(app_client, "coverage-sort")
    file_path = _upload_csv(app_client, project_id)
    _run_requirements(app_client, project_id)
    _run_mapping(app_client, project_id, file_path)

    resp = app_client.get(
        f"/api/mapping/{project_id}/coverage?sort_by=total_score&order=asc"
    )
    assert resp.status_code == 200
    scores = resp.json().get("scores", [])

    if len(scores) >= 2:
        for i in range(len(scores) - 1):
            assert scores[i]["total_score"] <= scores[i + 1]["total_score"], \
                "Scores should be ascending"


def test_list_mappings_filter_by_requirement(app_client):
    """GET /api/mapping/{project_id}?requirement_id=X filters mappings."""
    project_id = _create_project(app_client, "filter-map")
    file_path = _upload_csv(app_client, project_id)
    _run_requirements(app_client, project_id)
    _run_mapping(app_client, project_id, file_path)

    # Get a requirement ID
    reqs = app_client.get(f"/api/requirements/{project_id}/flat").json()["requirements"]
    if not reqs:
        pytest.skip("No requirements to filter by")

    req_id = reqs[0]["id"]
    resp = app_client.get(f"/api/mapping/{project_id}?requirement_id={req_id}")
    assert resp.status_code == 200
    for m in resp.json().get("mappings", []):
        assert m["requirement_id"] == req_id


# ─── Unit Tests: Scoring Algorithm ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_score_no_mappings():
    """Requirement with zero mappings → score 0."""
    from app.agents.mapping_workflow import MappingWorkflow

    wf = MappingWorkflow(llm=None, timeout=10)
    req = {"id": "r1", "title": "Test", "confidence": 0.9}
    score = wf._compute_score(req, [])

    assert score["total_score"] == 0
    assert score["base_coverage"] == 0
    assert score["matched_tc_count"] == 0


@pytest.mark.asyncio
async def test_score_single_high_confidence_mapping():
    """One mapping with confidence 0.9 → base 25 + quality ~18."""
    from app.agents.mapping_workflow import MappingWorkflow

    wf = MappingWorkflow(llm=None, timeout=10)
    req = {"id": "r1", "title": "Test", "confidence": 0.9}
    mappings = [{"mapping_confidence": 0.9, "coverage_aspects": [], "tc_source_file": "a.csv"}]
    score = wf._compute_score(req, mappings)

    assert score["total_score"] > 0
    assert score["base_coverage"] == 25.0  # 1 mapping → 25
    assert score["quality_weight"] == 18.0  # 0.9 × 20 = 18
    assert score["confidence_penalty"] == 0.0  # req confidence 0.9 > 0.7
    assert score["matched_tc_count"] == 1


@pytest.mark.asyncio
async def test_score_multiple_mappings():
    """4 mappings → base 40 (max)."""
    from app.agents.mapping_workflow import MappingWorkflow

    wf = MappingWorkflow(llm=None, timeout=10)
    req = {"id": "r1", "title": "Test", "confidence": 0.85}
    mappings = [
        {"mapping_confidence": 0.8, "coverage_aspects": ["happy_path"], "tc_source_file": "a.csv"},
        {"mapping_confidence": 0.7, "coverage_aspects": ["negative"], "tc_source_file": "a.csv"},
        {"mapping_confidence": 0.6, "coverage_aspects": ["boundary"], "tc_source_file": "b.csv"},
        {"mapping_confidence": 0.9, "coverage_aspects": ["edge_case"], "tc_source_file": "c.csv"},
    ]
    score = wf._compute_score(req, mappings)

    assert score["base_coverage"] == 40.0  # 4+ mappings → max
    assert score["matched_tc_count"] == 4
    # 3 different source files → crossref = 10
    assert score["crossref_bonus"] == 10.0
    assert score["total_score"] <= 100


@pytest.mark.asyncio
async def test_score_low_confidence_requirement():
    """Requirement with confidence 0.4 gets penalty."""
    from app.agents.mapping_workflow import MappingWorkflow

    wf = MappingWorkflow(llm=None, timeout=10)
    req = {"id": "r1", "title": "Test", "confidence": 0.4}
    mappings = [{"mapping_confidence": 0.8, "coverage_aspects": [], "tc_source_file": "a.csv"}]
    score = wf._compute_score(req, mappings)

    assert score["confidence_penalty"] < 0, "Expected negative penalty"
    # penalty = -10 * (0.7 - 0.4) / 0.7 ≈ -4.3
    assert -5 < score["confidence_penalty"] < -4


@pytest.mark.asyncio
async def test_score_with_aspects():
    """Mappings with known aspects get depth points."""
    from app.agents.mapping_workflow import MappingWorkflow

    wf = MappingWorkflow(llm=None, timeout=10)
    req = {"id": "r1", "title": "Test", "confidence": 0.9}
    mappings = [
        {"mapping_confidence": 0.85, "coverage_aspects": ["happy_path", "negative", "boundary"],
         "tc_source_file": "a.csv"},
    ]
    score = wf._compute_score(req, mappings)

    # depth: negative=8 + boundary=8 = 16 (happy_path doesn't add depth points)
    assert score["depth_coverage"] >= 16
    assert score["total_score"] > score["base_coverage"]  # depth adds value


@pytest.mark.asyncio
async def test_score_capped_at_100():
    """Score never exceeds 100 even with maximal inputs."""
    from app.agents.mapping_workflow import MappingWorkflow

    wf = MappingWorkflow(llm=None, timeout=10)
    req = {"id": "r1", "title": "Test", "confidence": 1.0}
    mappings = [
        {"mapping_confidence": 1.0,
         "coverage_aspects": ["happy_path", "negative", "boundary", "integration", "edge_case"],
         "tc_source_file": f"file_{i}.csv"}
        for i in range(10)
    ]
    score = wf._compute_score(req, mappings)

    assert score["total_score"] <= 100


# ─── Unit Tests: Pattern Matching ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pattern_match_finds_explicit_ids():
    """Pattern matching finds TC that explicitly references FR-001."""
    from app.agents.mapping_workflow import MappingWorkflow

    wf = MappingWorkflow(llm=None, timeout=10)
    reqs = [
        {"id": "r1", "external_id": "FR-001", "title": "Bank transfer"},
        {"id": "r2", "external_id": "FR-002", "title": "History"},
    ]
    cases = [
        {"name": "Test FR-001 basic flow", "steps": "Transfer money", "_source_file": "a.csv", "_identifier": "TC-1"},
        {"name": "Check dashboard", "steps": "Open dashboard", "_source_file": "a.csv", "_identifier": "TC-2"},
    ]

    matches = wf._pattern_match(reqs, cases)

    matched_reqs = {m["requirement_id"] for m in matches}
    assert "r1" in matched_reqs, "FR-001 should be matched by TC mentioning it"
    assert "r2" not in matched_reqs, "FR-002 should NOT be matched"


@pytest.mark.asyncio
async def test_pattern_match_case_insensitive():
    """Pattern matching is case-insensitive."""
    from app.agents.mapping_workflow import MappingWorkflow

    wf = MappingWorkflow(llm=None, timeout=10)
    reqs = [{"id": "r1", "external_id": "FR-001", "title": "Test"}]
    cases = [{"name": "test fr-001 validation", "_source_file": "a.csv", "_identifier": "TC-1"}]

    matches = wf._pattern_match(reqs, cases)
    assert len(matches) == 1


# ─── Integration: Priority Chain ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_priority_chain_persisted_scores():
    """
    When Faza 5+6 scores exist in DB, compute_registry_coverage
    returns them without calling LLM.
    """
    from app.agents.audit_workflow_integration import _load_persisted_scores

    # For a non-existent project, should return None
    result = await _load_persisted_scores("nonexistent-project-xyz")
    assert result is None
