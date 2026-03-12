"""
Tests for /api/mapping endpoints (Faza 5+6).
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── Helpers ──────────────────────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_CSV = FIXTURES_DIR / "sample_tests.csv"


def _create_project(app_client, name: str = "mapping-test-project") -> str:
    r = app_client.post("/api/projects/", json={"name": name})
    assert r.status_code in (200, 201)
    return r.json()["project_id"]


def _upload_csv(app_client, project_id: str) -> str:
    """Upload sample_tests.csv and return the file path stored on disk."""
    with SAMPLE_CSV.open("rb") as fh:
        r = app_client.post(
            f"/api/files/{project_id}/upload?source_type=file",
            files={"files": ("sample_tests.csv", fh, "text/csv")},
        )
    assert r.status_code == 200, f"Upload failed: {r.text}"
    uploaded = r.json()
    # Return the first uploaded file path
    if isinstance(uploaded, list) and uploaded:
        return uploaded[0].get("file_path", "")
    return ""


def _mock_llm_for_requirements():
    """Return a MagicMock LLM that produces valid extraction/validation JSON."""
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
                        "acceptance_criteria": [],
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
            "total_acceptance_criteria": 0,
            "formal_count": 2,
            "implicit_count": 0,
            "avg_confidence": 0.925,
            "low_confidence_count": 0,
        },
    })

    validation_response = json.dumps({
        "validated_requirements": [],
        "duplicates": [],
        "additional_gaps": [],
        "overall_assessment": {
            "completeness_rating": "high",
            "testability_rating": "high",
            "recommendation": "Requirements look good.",
        },
    })

    call_count = 0

    async def _side_effect(prompt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return extraction_response
        return validation_response

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(side_effect=_side_effect)
    return mock_llm


def _run_requirements_extraction(app_client, project_id: str) -> dict:
    mock_llm = _mock_llm_for_requirements()
    with patch("app.api.routes.requirements.get_llm", return_value=mock_llm), \
         patch(
             "app.agents.requirements_workflow.ContextBuilder.is_indexed",
             new_callable=AsyncMock,
             return_value=True,
         ), \
         patch(
             "app.agents.requirements_workflow.ContextBuilder.build_with_sources",
             new_callable=AsyncMock,
             return_value=("Sample project documentation with requirements.", []),
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
        except json.JSONDecodeError:
            continue
    return result_data


def _run_mapping(app_client, project_id: str, file_path: str = "") -> dict:
    """Run mapping workflow with mocked LLM."""
    # Mapping workflow uses LLM for fine matching — no LLM means embedding-only mode
    # which still produces results (pattern match + embedding similarity).
    # We use no LLM mock here so the workflow runs in embedding-only mode.
    with patch("app.api.routes.mapping.get_llm", return_value=None):
        payload = {"file_paths": [file_path] if file_path else [], "message": ""}
        r = app_client.post(f"/api/mapping/{project_id}/run", json=payload)
    assert r.status_code == 200, f"Mapping run failed: {r.text}"

    result_data: dict = {}
    for line in r.text.splitlines():
        if not line.startswith("data: "):
            continue
        payload_str = line[6:].strip()
        if payload_str == "[DONE]":
            break
        try:
            ev = json.loads(payload_str)
            if ev.get("type") == "result":
                result_data = ev["data"]
        except json.JSONDecodeError:
            continue
    return result_data


def _run_audit(app_client, project_id: str) -> dict:
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
        except json.JSONDecodeError:
            continue
    return result_data


# ─── Tests ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
def test_mapping_workflow_mock(app_client):
    """
    POST /api/mapping/{project_id}/run should:
    - Run without error
    - Return a result with mappings and/or scores
    - GET /api/mapping/{project_id}/coverage should return 200
    """
    project_id = _create_project(app_client)
    file_path = _upload_csv(app_client, project_id)

    # Run Faza 2 extraction first
    _run_requirements_extraction(app_client, project_id)

    # Run mapping
    result = _run_mapping(app_client, project_id, file_path)
    assert result, "No result data received from mapping workflow"

    # Result should have mappings and scores keys
    assert "mappings" in result, f"'mappings' key missing from result: {result.keys()}"
    assert "scores" in result, f"'scores' key missing from result: {result.keys()}"
    assert isinstance(result["mappings"], list)
    assert isinstance(result["scores"], list)

    # Coverage endpoint should be accessible
    resp = app_client.get(f"/api/mapping/{project_id}/coverage")
    assert resp.status_code == 200


@pytest.mark.asyncio
def test_coverage_scoring(app_client):
    """
    After running mapping, GET /api/mapping/{project_id}/coverage should return
    score items with total_score (float) and requirement_id (str).
    total_score must be between 0 and 100.
    """
    project_id = _create_project(app_client)
    file_path = _upload_csv(app_client, project_id)

    _run_requirements_extraction(app_client, project_id)
    result = _run_mapping(app_client, project_id, file_path)

    # If no scores were persisted (no matches found), we can still check the endpoint shape
    resp = app_client.get(f"/api/mapping/{project_id}/coverage")
    assert resp.status_code == 200
    data = resp.json()
    assert "scores" in data
    assert isinstance(data["scores"], list)

    for score in data["scores"]:
        assert "total_score" in score, f"Missing total_score: {score}"
        assert "requirement_id" in score, f"Missing requirement_id: {score}"
        assert isinstance(score["total_score"], (int, float))
        assert 0 <= score["total_score"] <= 100, (
            f"total_score out of range: {score['total_score']}"
        )


@pytest.mark.asyncio
def test_heatmap_endpoint(app_client):
    """
    GET /api/mapping/{project_id}/heatmap should return 200 with a list
    (may be empty if no modules/scores).
    """
    project_id = _create_project(app_client)
    file_path = _upload_csv(app_client, project_id)

    _run_requirements_extraction(app_client, project_id)
    _run_mapping(app_client, project_id, file_path)

    resp = app_client.get(f"/api/mapping/{project_id}/heatmap")
    assert resp.status_code == 200
    data = resp.json()
    assert "modules" in data
    assert isinstance(data["modules"], list)


@pytest.mark.asyncio
def test_audit_uses_persisted_scores(app_client):
    """
    After running Faza 2 + mapping, an audit via /api/chat/stream should:
    - Return registry_available in the result (True when Faza 2 data exists)
    - Return per_requirement_scores key in the result
    """
    project_id = _create_project(app_client)
    file_path = _upload_csv(app_client, project_id)

    # Run Faza 2 + mapping to populate the registry and persisted scores
    _run_requirements_extraction(app_client, project_id)
    _run_mapping(app_client, project_id, file_path)

    # Run audit
    result = _run_audit(app_client, project_id)
    assert result, "No result from audit"

    # registry_available must be present
    assert "registry_available" in result, (
        f"'registry_available' missing from audit result keys: {list(result.keys())}"
    )

    # per_requirement_scores must be present (may be empty list)
    assert "per_requirement_scores" in result, (
        f"'per_requirement_scores' missing from audit result keys: {list(result.keys())}"
    )
    assert isinstance(result["per_requirement_scores"], list)
