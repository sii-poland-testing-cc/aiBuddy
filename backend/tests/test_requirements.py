"""
Tests for /api/requirements endpoints (Faza 2).
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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
    # Mock build_with_sources to return dummy context
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
