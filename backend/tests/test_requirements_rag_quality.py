"""
RAG Quality Tests for Faza 2 Requirements Extraction
=====================================================
These tests require a REAL LLM and pre-indexed M1 context.
They are skipped in CI (no API key) and run manually to validate
extraction quality against the synthetic payment-domain fixtures.

Run manually:
    LLM_PROVIDER=anthropic ANTHROPIC_API_KEY=sk-... \
        pytest tests/test_requirements_rag_quality.py -v -s

Fixtures required (already in tests/fixtures/synthetic_docs/):
  - srs_payment_module.docx   — 12 FRs, glossary, actors
  - test_plan_payment.docx    — test plan, environments, risks
  - qa_process.docx           — defect lifecycle, severity levels, roles
"""

import pytest

# ─── Skip guard ───────────────────────────────────────────────────────────────

def _has_real_llm() -> bool:
    """Return True when a real LLM is configured (non-empty API key or Bedrock creds)."""
    import os
    return bool(
        os.getenv("ANTHROPIC_API_KEY") or os.getenv("AWS_ACCESS_KEY_ID")
    )


pytestmark = pytest.mark.skipif(
    not _has_real_llm(),
    reason="Real LLM required — set ANTHROPIC_API_KEY or AWS credentials to run",
)


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def extraction_result(app_client):
    """
    Build M1 context from all three synthetic docs and run Faza 2 extraction.
    Result is cached for the module so the LLM is only called once.
    """
    import json
    from pathlib import Path

    SYNTHETIC = Path(__file__).parent / "fixtures" / "synthetic_docs"
    docs = [
        SYNTHETIC / "srs_payment_module.docx",
        SYNTHETIC / "test_plan_payment.docx",
        SYNTHETIC / "qa_process.docx",
    ]

    # 1. Create project
    r = app_client.post("/api/projects/", json={"name": "rag-quality-test"})
    assert r.status_code in (200, 201)
    project_id = r.json()["project_id"]

    # 2. Build M1 context (uploads all three docs)
    with (
        docs[0].open("rb") as f0,
        docs[1].open("rb") as f1,
        docs[2].open("rb") as f2,
    ):
        r = app_client.post(
            f"/api/context/{project_id}/build",
            files=[
                ("files", ("srs_payment_module.docx",  f0, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")),
                ("files", ("test_plan_payment.docx",   f1, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")),
                ("files", ("qa_process.docx",          f2, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")),
            ],
        )
    assert r.status_code == 200, f"M1 build failed: {r.text[:500]}"

    # 3. Run Faza 2 extraction
    r = app_client.post(
        f"/api/requirements/{project_id}/extract",
        json={"message": ""},
    )
    assert r.status_code == 200, f"Faza 2 extraction failed: {r.text[:500]}"

    result: dict = {}
    for line in r.text.splitlines():
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if payload == "[DONE]":
            break
        try:
            ev = json.loads(payload)
            if ev.get("type") == "result":
                result = ev["data"]
        except json.JSONDecodeError:
            continue

    assert result, "No result data from Faza 2 extraction"
    return result


# ─── Tests ────────────────────────────────────────────────────────────────────

def test_extracts_minimum_requirements(extraction_result):
    """Should extract at least 8 functional requirements from three rich docs."""
    flat = extraction_result.get("requirements_flat", [])
    functional = [r for r in flat if r.get("level") == "functional_req"]
    assert len(functional) >= 8, (
        f"Only {len(functional)} functional_req items found — expected ≥8 from 12-FR SRS"
    )


def test_formal_requirements_have_external_ids(extraction_result):
    """Formal requirements from srs_payment_module.docx should carry FR-xxx IDs."""
    flat = extraction_result.get("requirements_flat", [])
    formal = [r for r in flat if r.get("source_type") == "formal"]
    with_id = [r for r in formal if r.get("external_id")]
    assert len(with_id) >= 4, (
        f"Only {len(with_id)} formal requirements have external_id out of {len(formal)} formal items"
    )


def test_source_references_populated(extraction_result):
    """At least some requirements should reference the source document filenames."""
    flat = extraction_result.get("requirements_flat", [])
    reqs_with_sources = [
        r for r in flat
        if r.get("level") == "functional_req" and r.get("source_references")
    ]
    assert len(reqs_with_sources) >= 4, (
        f"Only {len(reqs_with_sources)} requirements have source_references populated — "
        "breadcrumb injection may not be working"
    )


def test_cross_document_coverage(extraction_result):
    """Requirements should be sourced from at least 2 of the 3 uploaded documents."""
    flat = extraction_result.get("requirements_flat", [])
    all_sources: set = set()
    for r in flat:
        for src in r.get("source_references", []):
            all_sources.add(src)

    # Fall back to checking rag_sources if source_references not populated
    if not all_sources:
        all_sources = {s["filename"] for s in extraction_result.get("rag_sources", [])}

    assert len(all_sources) >= 2, (
        f"Requirements only reference {len(all_sources)} document(s) — "
        "expected coverage from at least 2 of the 3 uploaded docs"
    )
