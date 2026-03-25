"""
test_audit_integration.py
=========================
Unit tests for app.agents.audit_workflow_integration

Covers all three priority-chain branches of compute_registry_coverage and
the helper functions that were previously only exercised indirectly through
test_m1_m2_integration.py (where compute_registry_coverage is always mocked).

Run from backend/ with:
    pytest tests/test_audit_integration.py -v
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ─── _legacy_extract ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_legacy_extract_no_llm_returns_empty():
    """No LLM → empty list, not phantom IDs."""
    from app.agents.audit_workflow_integration import _legacy_extract
    result = await _legacy_extract("some rag context", llm=None)
    assert result == []


@pytest.mark.asyncio
async def test_legacy_extract_parses_llm_json():
    """LLM returns a JSON array → parsed list, TC-* IDs filtered out."""
    from app.agents.audit_workflow_integration import _legacy_extract

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(return_value='["FR-001", "FR-002", "TC-001"]')
    result = await _legacy_extract("some docs", llm=mock_llm)
    assert "FR-001" in result
    assert "FR-002" in result
    assert "TC-001" not in result, "TC-* IDs must be filtered"


@pytest.mark.asyncio
async def test_legacy_extract_llm_failure_returns_empty():
    """LLM raises → graceful empty list, no exception propagated."""
    from app.agents.audit_workflow_integration import _legacy_extract

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(side_effect=RuntimeError("LLM timeout"))
    result = await _legacy_extract("docs", llm=mock_llm)
    assert result == []


# ─── _match_requirements_to_tests ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_match_reqs_pattern_hit():
    """Requirement ID found in a test case field → included in result."""
    from app.agents.audit_workflow_integration import _match_requirements_to_tests

    cases = [{"name": "Verify FR-042 payment flow", "steps": ""}]
    result = await _match_requirements_to_tests(cases, ["FR-042", "FR-099"], [], llm=None)
    assert "FR-042" in result
    assert "FR-099" not in result


@pytest.mark.asyncio
async def test_match_reqs_ignores_internal_keys():
    """_-prefixed internal keys (e.g. _source_file) must not cause false matches."""
    from app.agents.audit_workflow_integration import _match_requirements_to_tests

    # _source_file contains "FR-017" in filename, but no public field mentions it
    cases = [{"name": "Login test", "_source_file": "FR-017_suite.csv"}]
    result = await _match_requirements_to_tests(cases, ["FR-017"], [], llm=None)
    assert "FR-017" not in result, "_-prefixed fields must be excluded from pattern scan"


@pytest.mark.asyncio
async def test_match_reqs_llm_fuzzy_branch():
    """LLM fuzzy-match branch fires when < 50% covered; adds LLM-returned IDs."""
    from app.agents.audit_workflow_integration import _match_requirements_to_tests

    # 0/4 covered by pattern → below 50% threshold → LLM branch fires
    cases = [{"name": "some test"}]
    req_ids = ["FR-001", "FR-002", "FR-003", "FR-004"]
    req_details = [
        {"id": str(i), "external_id": f"FR-00{i}", "title": f"Req {i}",
         "description": "", "level": "functional_req", "confidence": 0.9,
         "taxonomy": {}, "needs_review": False}
        for i in range(1, 5)
    ]

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(return_value='["FR-001", "FR-002"]')

    result = await _match_requirements_to_tests(cases, req_ids, req_details, llm=mock_llm)
    assert "FR-001" in result
    assert "FR-002" in result
    mock_llm.acomplete.assert_called_once()


# ─── _build_live_coverage_result ─────────────────────────────────────────────

def test_build_live_coverage_result_basic():
    """Correct pct, counts, and per_req_scores for a simple covered/uncovered split."""
    from app.agents.audit_workflow_integration import _build_live_coverage_result

    req_ids = ["FR-001", "FR-002", "FR-003"]
    req_details = [
        {"id": "1", "external_id": "FR-001", "title": "A", "level": "functional_req",
         "confidence": 0.9, "taxonomy": {}, "needs_review": False},
        {"id": "2", "external_id": "FR-002", "title": "B", "level": "functional_req",
         "confidence": 0.9, "taxonomy": {}, "needs_review": False},
        {"id": "3", "external_id": "FR-003", "title": "C", "level": "functional_req",
         "confidence": 0.9, "taxonomy": {}, "needs_review": False},
    ]
    covered = ["FR-001"]

    result = _build_live_coverage_result(req_ids, req_details, covered)

    assert result["requirements_total"] == 3
    assert result["requirements_covered_count"] == 1
    assert result["coverage_pct"] == pytest.approx(33.3, abs=0.1)
    assert "FR-002" in result["requirements_uncovered"]
    assert "FR-003" in result["requirements_uncovered"]
    assert result["registry_available"] is True

    scores_by_id = {s["external_id"]: s for s in result["per_requirement_scores"]}
    assert scores_by_id["FR-001"]["is_covered"] is True
    assert scores_by_id["FR-001"]["score"] == pytest.approx(40.0)
    assert scores_by_id["FR-002"]["is_covered"] is False
    assert scores_by_id["FR-002"]["score"] == pytest.approx(0.0)


def test_build_live_coverage_result_empty():
    """Empty req_ids → all-zero result with registry_available False."""
    from app.agents.audit_workflow_integration import _build_live_coverage_result

    result = _build_live_coverage_result([], [], [])
    assert result["requirements_total"] == 0
    assert result["coverage_pct"] == 0.0
    assert result["registry_available"] is False


# ─── compute_registry_coverage — priority chain ───────────────────────────────

@pytest.mark.asyncio
async def test_priority1_persisted_scores_short_circuits():
    """When Faza 5+6 scores exist, they are returned immediately without hitting Faza 2."""
    from app.agents.audit_workflow_integration import compute_registry_coverage

    fake_persisted = {
        "requirements_from_docs": ["FR-001"], "requirements_covered": ["FR-001"],
        "coverage_pct": 100.0, "requirements_total": 1, "requirements_covered_count": 1,
        "requirements_uncovered": [], "registry_available": True, "per_requirement_scores": [],
    }

    with patch(
        "app.agents.audit_workflow_integration._load_persisted_scores",
        AsyncMock(return_value=fake_persisted),
    ) as mock_persisted, patch(
        "app.agents.audit_workflow_integration._load_faza2_requirements",
        AsyncMock(return_value=([], [])),
    ) as mock_faza2:
        result = await compute_registry_coverage("proj-1", [], "ctx")

    assert result["coverage_pct"] == 100.0
    mock_persisted.assert_called_once_with("proj-1")
    mock_faza2.assert_not_called()


@pytest.mark.asyncio
async def test_priority2_faza2_registry_used_when_no_persisted():
    """When no Faza 5+6 scores, Faza 2 registry is used for live matching."""
    from app.agents.audit_workflow_integration import compute_registry_coverage

    faza2_ids = ["FR-001", "FR-002"]
    faza2_details = [
        {"id": "1", "external_id": "FR-001", "title": "A", "level": "functional_req",
         "confidence": 0.9, "taxonomy": {}, "needs_review": False},
        {"id": "2", "external_id": "FR-002", "title": "B", "level": "functional_req",
         "confidence": 0.9, "taxonomy": {}, "needs_review": False},
    ]
    cases = [{"name": "Test FR-001 payment flow"}]

    with patch(
        "app.agents.audit_workflow_integration._load_persisted_scores",
        AsyncMock(return_value=None),
    ), patch(
        "app.agents.audit_workflow_integration._load_faza2_requirements",
        AsyncMock(return_value=(faza2_ids, faza2_details)),
    ):
        result = await compute_registry_coverage("proj-2", cases, "ctx", llm=None)

    assert result["requirements_total"] == 2
    assert "FR-001" in result["requirements_covered"]
    assert result["registry_available"] is True


@pytest.mark.asyncio
async def test_priority3_legacy_extraction_when_no_faza2():
    """When neither persisted scores nor Faza 2 exist, legacy LLM extraction fires."""
    from app.agents.audit_workflow_integration import compute_registry_coverage

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(return_value='["FR-010", "FR-011"]')
    cases = [{"name": "Test FR-010 flow"}]

    with patch(
        "app.agents.audit_workflow_integration._load_persisted_scores",
        AsyncMock(return_value=None),
    ), patch(
        "app.agents.audit_workflow_integration._load_faza2_requirements",
        AsyncMock(return_value=([], [])),
    ):
        result = await compute_registry_coverage("proj-3", cases, "context text", llm=mock_llm)

    assert result["requirements_total"] == 2
    assert "FR-010" in result["requirements_covered"]
    # No req_details available in legacy path → registry_available False
    assert result["registry_available"] is False


@pytest.mark.asyncio
async def test_priority3_no_llm_no_data_returns_zero_coverage():
    """No persisted scores, no Faza 2, no LLM → empty result (not phantom IDs)."""
    from app.agents.audit_workflow_integration import compute_registry_coverage

    with patch(
        "app.agents.audit_workflow_integration._load_persisted_scores",
        AsyncMock(return_value=None),
    ), patch(
        "app.agents.audit_workflow_integration._load_faza2_requirements",
        AsyncMock(return_value=([], [])),
    ):
        result = await compute_registry_coverage("proj-4", [], "ctx", llm=None)

    assert result["requirements_total"] == 0
    assert result["coverage_pct"] == 0.0
    assert result["requirements_from_docs"] == []
