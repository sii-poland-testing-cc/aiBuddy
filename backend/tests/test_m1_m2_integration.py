"""
M1 → M2 integration test
=========================
Runs M1 context build for "test-project", then sends an audit
request with a small test CSV, and validates the response
references domain concepts from the .docx.

Usage (from backend/):
    python tests/test_m1_m2_integration.py
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx

BASE = "http://localhost:8000"
DOCX = Path(__file__).parent / "fixtures" / "sample_domain.docx"
CSV  = Path(__file__).parent / "fixtures" / "sample_tests.csv"

DOMAIN_KEYWORDS = [
    "test", "defect", "coverage", "regression", "severity",
    "qa", "role", "process", "tag", "priority",
]


async def create_project(client: httpx.AsyncClient) -> str:
    print("\n" + "=" * 60)
    print("STEP 0 — Create project")
    print("=" * 60)
    r = await client.post("/api/projects/", json={"name": "test-project-integration"})
    r.raise_for_status()
    project_id = r.json()["project_id"]
    print(f"  project_id = {project_id}")
    return project_id


async def run_m1(client: httpx.AsyncClient, project_id: str) -> bool:
    print("\n" + "=" * 60)
    print(f"STEP 1 — M1 Context Build  ({DOCX.name})")
    print("=" * 60)

    with DOCX.open("rb") as fh:
        r = await client.post(
            f"/api/context/{project_id}/build",
            files={"files": (DOCX.name, fh,
                   "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )

    if r.status_code != 200:
        print(f"  ERROR {r.status_code}: {r.text[:300]}")
        return False

    for line in r.text.splitlines():
        if not line.startswith("data: "):
            continue
        p = line[6:].strip()
        if p == "[DONE]":
            break
        try:
            ev = json.loads(p)
        except Exception:
            continue
        if ev["type"] == "progress":
            pct = int(ev["data"]["progress"] * 100)
            print(f"  [{pct:3d}%] {ev['data']['stage']:8s}  {ev['data']['message']}")
        elif ev["type"] == "result":
            s = ev["data"].get("stats", {})
            print(f"  [RESULT] entities={s.get('entity_count')} "
                  f"relations={s.get('relation_count')} terms={s.get('term_count')}")
        elif ev["type"] == "error":
            print(f"  [ERROR] {ev['data']['message']}")
            return False
    return True


async def upload_test_file(client: httpx.AsyncClient, project_id: str) -> list[str]:
    print("\n" + "=" * 60)
    print(f"STEP 2 — Upload test suite  ({CSV.name})")
    print("=" * 60)

    with CSV.open("rb") as fh:
        r = await client.post(
            f"/api/files/{project_id}/upload",
            files={"files": (CSV.name, fh, "text/csv")},
        )
    if r.status_code != 200:
        print(f"  ERROR {r.status_code}: {r.text[:300]}")
        return []
    data = r.json()
    items = data if isinstance(data, list) else data.get("file_paths", [])
    # API returns list of file objects: extract file_path strings
    paths = [
        item["file_path"] if isinstance(item, dict) else item
        for item in items
    ]
    print(f"  Uploaded: {paths}")
    return paths


async def run_audit(client: httpx.AsyncClient, project_id: str, file_paths: list[str]) -> dict:
    print("\n" + "=" * 60)
    print("STEP 3 — Audit chat  (Jakie luki w pokryciu widzisz?)")
    print("=" * 60)

    payload = {
        "project_id": project_id,
        "message":    "Jakie luki w pokryciu widzisz?",
        "file_paths": file_paths,
        "tier":       "audit",
    }
    r = await client.post("/api/chat/stream", json=payload)
    if r.status_code != 200:
        print(f"  ERROR {r.status_code}: {r.text[:300]}")
        return {}

    result = {}
    for line in r.text.splitlines():
        if not line.startswith("data: "):
            continue
        p = line[6:].strip()
        if p == "[DONE]":
            break
        try:
            ev = json.loads(p)
        except Exception:
            continue
        if ev["type"] == "progress":
            pct = int(ev["data"]["progress"] * 100)
            print(f"  [{pct:3d}%] {ev['data']['message']}")
        elif ev["type"] == "result":
            result = ev["data"]
        elif ev["type"] == "error":
            print(f"  [ERROR] {ev['data']['message']}")
    return result


def analyse_result(result: dict) -> None:
    print("\n" + "=" * 60)
    print("STEP 4 — Analysis")
    print("=" * 60)

    summary = result.get("summary", {})
    recs    = result.get("recommendations", [])
    sources = result.get("rag_sources", [])

    print(f"\n  Summary:")
    print(f"    duplicates_found : {summary.get('duplicates_found', '?')}")
    print(f"    untagged_cases   : {summary.get('untagged_cases', '?')}")
    print(f"    coverage_pct     : {summary.get('coverage_pct', '?')}%")

    print(f"\n  Recommendations ({len(recs)}):")
    for i, r in enumerate(recs, 1):
        print(f"    {i}. {r}")

    print(f"\n  RAG sources ({len(sources)}):")
    for s in sources:
        print(f"    • {s['filename']}")
        print(f"      \"{s['excerpt'][:100]}…\"")

    # Check whether domain knowledge leaked into recommendations
    all_text = " ".join(recs).lower()
    hits = [kw for kw in DOMAIN_KEYWORDS if kw in all_text]

    print(f"\n  Domain keyword hits in recommendations: {hits}")

    if sources:
        print("\n  ✅ RAG sources present — M1 context was used")
    else:
        print("\n  ⚠️  No RAG sources returned — audit ran without domain context")

    if hits:
        print(f"  ✅ Recommendations reference domain concepts: {hits}")
    else:
        print("  ⚠️  Recommendations appear generic (no domain keywords found)")


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=180) as client:
        project_id = await create_project(client)

        ok = await run_m1(client, project_id)
        if not ok:
            print("\nM1 failed — aborting")
            sys.exit(1)

        file_paths = await upload_test_file(client, project_id)
        if not file_paths:
            print("\nUpload failed — aborting")
            sys.exit(1)

        result = await run_audit(client, project_id, file_paths)
        if not result:
            print("\nAudit returned no result")
            sys.exit(1)

        analyse_result(result)


if __name__ == "__main__":
    asyncio.run(main())


# ─────────────────────────────────────────────────────────────────────────────
# pytest: audit workflow triggered automatically when project has uploaded files
# ─────────────────────────────────────────────────────────────────────────────

def test_chat_triggers_audit_when_project_has_files(app_client):
    """
    Files uploaded to a project via POST /api/files/{project_id}/upload must be
    auto-loaded and used to trigger AuditWorkflow when /api/chat/stream is called
    with an empty file_paths list.
    """
    from pathlib import Path
    from unittest.mock import AsyncMock, MagicMock, patch

    CSV = Path(__file__).parent / "fixtures" / "sample_tests.csv"
    assert CSV.exists(), f"Fixture missing: {CSV}"

    # 1. Create project
    r = app_client.post("/api/projects/", json={"name": "audit-auto-files-test"})
    assert r.status_code in (200, 201)
    project_id = r.json()["project_id"]

    # 2. Upload test file via the files API (simulates Sidebar upload)
    with CSV.open("rb") as fh:
        upload_r = app_client.post(
            f"/api/files/{project_id}/upload",
            files={"files": (CSV.name, fh, "text/csv")},
        )
    assert upload_r.status_code == 200

    # 3. Mock LLM — returns a simple string; workflow falls back to [raw] for recs
    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(return_value='["Add more edge case tests."]')

    with patch("app.api.routes.chat.get_llm", return_value=mock_llm):
        chat_r = app_client.post(
            "/api/chat/stream",
            json={
                "project_id": project_id,
                "message": "run audit",
                "file_paths": [],      # intentionally empty — backend must auto-load
            },
        )
    assert chat_r.status_code == 200

    result_data: dict = {}
    for line in chat_r.text.splitlines():
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

    assert result_data, "No result event received — workflow was not triggered"
    assert "summary" in result_data, (
        f"Expected audit result with 'summary' key, got: {list(result_data.keys())}"
    )
    assert "coverage_pct" in result_data["summary"], (
        f"Expected 'coverage_pct' in summary, got: {result_data['summary']}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Shared mock LLM for M1 context builds (avoids real API calls in tests)
# ─────────────────────────────────────────────────────────────────────────────

from unittest.mock import AsyncMock, MagicMock, patch as _patch


def _make_m1_mock_llm():
    _entities = json.dumps({
        "entities": [
            {"id": "e1", "name": "PayFlow",     "type": "system", "description": "Payment processing system"},
            {"id": "e2", "name": "Chargeback",  "type": "process","description": "Transaction reversal process"},
            {"id": "e3", "name": "Test Case",   "type": "data",   "description": "A test scenario"},
        ],
        "relations": [{"source": "e3", "target": "e1", "label": "validates"}],
    })
    _glossary = json.dumps([
        {"term": "Chargeback",  "definition": "Reversal of a payment transaction.", "related_terms": ["Dispute"], "source": "docs"},
        {"term": "Test Case",   "definition": "Conditions to verify behaviour.",    "related_terms": [],          "source": "docs"},
    ])
    _approved = json.dumps({"verdict": "APPROVED"})
    mock = MagicMock()

    async def _side(prompt, **kwargs):
        if "entities and their relationships" in prompt:
            return _entities
        if "domain-specific term" in prompt:  # _enumerate_term_names (phase 1)
            return json.dumps(["Test Case", "Defect", "QA Engineer", "Test Suite"])
        if "Write glossary definitions" in prompt:  # _define_term_group (phase 2)
            return _glossary
        return _approved

    mock.acomplete = AsyncMock(side_effect=_side)
    return mock


# ─────────────────────────────────────────────────────────────────────────────
# pytest: RAG chat uses indexed context, not generic LLM knowledge
# ─────────────────────────────────────────────────────────────────────────────

def test_context_chat_uses_rag(app_client):
    """
    After M1 context is built with srs_payment_module.docx, a chat request
    with no file_paths must:
      - take the RAG path (is_indexed → True → build_with_sources called)
      - include rag_sources pointing to srs_payment_module.docx
      - pass a Context: block to the LLM (not the generic fallback prompt)
      - return the mocked LLM response which mentions "chargeback"
    """
    from pathlib import Path
    from unittest.mock import AsyncMock, MagicMock, patch

    _SYNTHETIC = Path(__file__).parent / "fixtures" / "synthetic_docs"
    _DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    docx_path = _SYNTHETIC / "srs_payment_module.docx"
    assert docx_path.exists(), f"Fixture missing: {docx_path}"

    # 1. Create project
    r = app_client.post("/api/projects/", json={"name": "rag-chat-test"})
    assert r.status_code in (200, 201)
    project_id = r.json()["project_id"]

    # 2. Build M1 context (indexes document into Chroma) — mock LLM for extraction
    with _patch("app.api.routes.context.get_llm", return_value=_make_m1_mock_llm()), \
         docx_path.open("rb") as fh:
        build_r = app_client.post(
            f"/api/context/{project_id}/build",
            files={"files": (docx_path.name, fh, _DOCX_MIME)},
        )
    assert build_r.status_code == 200

    # Confirm indexed
    status = app_client.get(f"/api/context/{project_id}/status").json()
    assert status["rag_ready"] is True

    # 3. Mock LLM — controlled response so test doesn't need a real API key
    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(
        return_value="A Chargeback is a reversal of a transaction as defined in the documentation."
    )

    with _patch("app.api.routes.chat.get_llm", return_value=mock_llm):
        chat_r = app_client.post(
            "/api/chat/stream",
            json={"project_id": project_id, "message": "What is a Chargeback?", "file_paths": []},
        )
    assert chat_r.status_code == 200

    result_data: dict = {}
    for line in chat_r.text.splitlines():
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

    assert result_data, "No result event received from chat stream"

    message = result_data.get("message", "")
    rag_sources = result_data.get("rag_sources", [])

    # RAG path must have been taken: sources non-empty
    assert rag_sources, "Expected rag_sources non-empty — RAG path should have been used"
    source_files = [s.get("filename", "") for s in rag_sources]
    assert any("srs_payment" in f or "payment" in f.lower() for f in source_files), (
        f"Expected srs_payment_module.docx in sources, got: {source_files}"
    )

    # LLM must have been called with a RAG context prompt (not the generic fallback)
    assert mock_llm.acomplete.called, "LLM was not called"
    called_prompt = str(mock_llm.acomplete.call_args[0][0])
    assert "Context:" in called_prompt, (
        "LLM prompt did not include 'Context:' — generic fallback may have been used"
    )

    # Mocked response makes it through to the result
    assert "chargeback" in message.lower(), (
        f"Expected 'chargeback' in response, got: {message[:300]}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# pytest: term explanation query uses enriched RAG prompt
# ─────────────────────────────────────────────────────────────────────────────

def test_term_explanation_uses_rag(app_client):
    """
    A 'Wyjaśnij termin:' message must:
      - use the term name as the RAG query (not the raw message)
      - use the structured three-section prompt (not the generic one)
      - return rag_sources non-empty (RAG path taken)
      - not contain "nie mam informacji" when the term IS in the docs
    """
    from pathlib import Path
    from unittest.mock import AsyncMock, MagicMock, patch

    _SYNTHETIC = Path(__file__).parent / "fixtures" / "synthetic_docs"
    _DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    docx_path = _SYNTHETIC / "srs_payment_module.docx"
    assert docx_path.exists(), f"Fixture missing: {docx_path}"

    # 1. Create project and build M1 context
    r = app_client.post("/api/projects/", json={"name": "term-explain-test"})
    assert r.status_code in (200, 201)
    project_id = r.json()["project_id"]

    with _patch("app.api.routes.context.get_llm", return_value=_make_m1_mock_llm()), \
         docx_path.open("rb") as fh:
        build_r = app_client.post(
            f"/api/context/{project_id}/build",
            files={"files": (docx_path.name, fh, _DOCX_MIME)},
        )
    assert build_r.status_code == 200

    status = app_client.get(f"/api/context/{project_id}/status").json()
    assert status["rag_ready"] is True

    # 2. Mock LLM with a response that contains Settlement-related keywords
    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(
        return_value=(
            "**Opis** — Settlement is the process by which funds are transferred from the acquirer "
            "to the merchant after a transaction is approved.\n\n"
            "**Kontekst** — Used in PayFlow after authorization to complete the payment cycle.\n\n"
            "**Powiązane terminy** — Authorization, Acquirer, Merchant, Capture"
        )
    )

    with patch("app.api.routes.chat.get_llm", return_value=mock_llm):
        chat_r = app_client.post(
            "/api/chat/stream",
            json={
                "project_id": project_id,
                "message": 'Wyjaśnij termin: "Settlement"',
                "file_paths": [],
            },
        )
    assert chat_r.status_code == 200

    result_data: dict = {}
    for line in chat_r.text.splitlines():
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

    assert result_data, "No result event received"

    message = result_data.get("message", "")
    rag_sources = result_data.get("rag_sources", [])

    # RAG sources must be present
    assert rag_sources, "Expected rag_sources non-empty — RAG path should have been used"

    # Response contains "settlement"
    assert "settlement" in message.lower(), (
        f"Expected 'settlement' in response, got: {message[:300]}"
    )

    # Response contains at least one of the expected domain keywords
    domain_hits = [kw for kw in ["acquirer", "merchant", "funds"] if kw in message.lower()]
    assert domain_hits, (
        f"Expected domain keywords (acquirer/merchant/funds) in response, got: {message[:300]}"
    )

    # Must NOT say "nie mam informacji" — the term is in the docs
    assert "nie mam informacji" not in message.lower(), (
        "Response claims no information found, but term should be in docs"
    )

    # LLM must have been called with the structured term-explanation prompt
    assert mock_llm.acomplete.called, "LLM was not called"
    called_prompt = str(mock_llm.acomplete.call_args[0][0])
    assert "Opis" in called_prompt, (
        "LLM prompt did not include structured sections — generic prompt may have been used"
    )
    assert "Settlement" in called_prompt, (
        "LLM prompt did not include the term name"
    )


# ─────────────────────────────────────────────────────────────────────────────
# pytest: requirement-based coverage_pct
# ─────────────────────────────────────────────────────────────────────────────

def test_coverage_reflects_requirement_gaps(app_client):
    """
    With srs_payment_module.docx indexed and sample_tests.csv uploaded,
    coverage_pct must be well below 50% — sample CSV only touches FR-002/FR-003.
    _extract_requirements is patched to return 10 deterministic FRs so the
    test does not depend on real LLM extraction quality.
    """
    from pathlib import Path
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.agents.audit_workflow import AuditWorkflow

    _SYNTHETIC = Path(__file__).parent / "fixtures" / "synthetic_docs"
    _DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    docx_path = _SYNTHETIC / "srs_payment_module.docx"
    csv_path  = Path(__file__).parent / "fixtures" / "sample_tests.csv"
    assert docx_path.exists() and csv_path.exists()

    # 1. Create project and build M1 context
    r = app_client.post("/api/projects/", json={"name": "coverage-gap-test"})
    assert r.status_code in (200, 201)
    project_id = r.json()["project_id"]

    with _patch("app.api.routes.context.get_llm", return_value=_make_m1_mock_llm()), \
         docx_path.open("rb") as fh:
        build_r = app_client.post(
            f"/api/context/{project_id}/build",
            files={"files": (docx_path.name, fh, _DOCX_MIME)},
        )
    assert build_r.status_code == 200
    assert app_client.get(f"/api/context/{project_id}/status").json()["rag_ready"] is True

    # 2. Upload test CSV
    with csv_path.open("rb") as fh:
        up = app_client.post(
            f"/api/files/{project_id}/upload",
            files={"files": (csv_path.name, fh, "text/csv")},
        )
    assert up.status_code == 200

    # 3. Patch compute_registry_coverage to return 10 deterministic FRs.
    #    FR-002 and FR-003 are covered; the other 8 are uncovered.
    FAKE_REQS = [
        "FR-001", "FR-002", "FR-003", "FR-004", "FR-005",
        "FR-006", "FR-007", "FR-008", "FR-009", "FR-010",
    ]
    FAKE_COVERAGE_RESULT = {
        "requirements_from_docs": FAKE_REQS,
        "requirements_covered": ["FR-002", "FR-003"],
        "coverage_pct": 20.0,
        "requirements_total": 10,
        "requirements_covered_count": 2,
        "requirements_uncovered": [r for r in FAKE_REQS if r not in ("FR-002", "FR-003")],
        "registry_available": False,
        "per_requirement_scores": [],
    }
    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(
        return_value='["Add tests for uncovered FRs","Improve tag coverage",'
                     '"Review FR-001 scenarios","Add negative tests","Add integration tests"]'
    )

    with patch(
             "app.agents.audit_workflow.compute_registry_coverage",
             AsyncMock(return_value=FAKE_COVERAGE_RESULT),
         ), \
         patch("app.api.routes.chat.get_llm", return_value=mock_llm):
        chat_r = app_client.post(
            "/api/chat/stream",
            json={"project_id": project_id, "message": "audit", "file_paths": []},
        )
    assert chat_r.status_code == 200

    result_data: dict = {}
    for line in chat_r.text.splitlines():
        if not line.startswith("data: "): continue
        payload = line[6:].strip()
        if payload == "[DONE]": break
        try:
            ev = json.loads(payload)
            if ev.get("type") == "result":
                result_data = ev["data"]
        except Exception:
            continue

    assert result_data, "No result event received"
    summary = result_data.get("summary", {})

    assert summary.get("requirements_total", 0) >= 10, (
        f"Expected ≥10 requirements from docs, got: {summary}"
    )
    assert summary.get("coverage_pct", 100.0) < 50.0, (
        f"Expected coverage_pct < 50%, got: {summary.get('coverage_pct')}"
    )
    assert summary.get("requirements_covered", 99) <= 3, (
        f"Expected ≤3 covered requirements, got: {summary.get('requirements_covered')}"
    )
    assert len(summary.get("requirements_uncovered", [])) >= 7, (
        f"Expected ≥7 uncovered requirements, got: {summary.get('requirements_uncovered')}"
    )


def test_coverage_zero_without_m1_context(app_client):
    """
    Without M1 context (no docs indexed), coverage_pct must be 0.0
    and recommendations must include a hint to run Context Builder.
    compute_registry_coverage is patched to return empty (simulates no context/registry).
    """
    from pathlib import Path
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.agents.audit_workflow import AuditWorkflow

    csv_path = Path(__file__).parent / "fixtures" / "sample_tests.csv"
    assert csv_path.exists()

    # 1. Create project — intentionally NO context build
    r = app_client.post("/api/projects/", json={"name": "no-context-coverage-test"})
    assert r.status_code in (200, 201)
    project_id = r.json()["project_id"]

    # 2. Upload test CSV
    with csv_path.open("rb") as fh:
        up = app_client.post(
            f"/api/files/{project_id}/upload",
            files={"files": (csv_path.name, fh, "text/csv")},
        )
    assert up.status_code == 200

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(
        return_value='["Add more edge case tests."]'
    )

    EMPTY_COVERAGE_RESULT = {
        "requirements_from_docs": [],
        "requirements_covered": [],
        "coverage_pct": 0.0,
        "requirements_total": 0,
        "requirements_covered_count": 0,
        "requirements_uncovered": [],
        "registry_available": False,
        "per_requirement_scores": [],
    }

    with patch(
             "app.agents.audit_workflow.compute_registry_coverage",
             AsyncMock(return_value=EMPTY_COVERAGE_RESULT),
         ), \
         patch("app.api.routes.chat.get_llm", return_value=mock_llm):
        chat_r = app_client.post(
            "/api/chat/stream",
            json={"project_id": project_id, "message": "audit", "file_paths": []},
        )
    assert chat_r.status_code == 200

    result_data: dict = {}
    for line in chat_r.text.splitlines():
        if not line.startswith("data: "): continue
        payload = line[6:].strip()
        if payload == "[DONE]": break
        try:
            ev = json.loads(payload)
            if ev.get("type") == "result":
                result_data = ev["data"]
        except Exception:
            continue

    assert result_data, "No result event received"
    summary = result_data.get("summary", {})
    recs    = result_data.get("recommendations", [])

    assert summary.get("coverage_pct") == 0.0, (
        f"Expected coverage_pct == 0.0 without context, got: {summary.get('coverage_pct')}"
    )
    assert any("Context Builder" in r for r in recs), (
        f"Expected fallback recommendation mentioning Context Builder, got: {recs}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# pytest: AuditSnapshot persistence
# ─────────────────────────────────────────────────────────────────────────────

def _run_audit(app_client, project_id: str, mock_llm,
               file_paths: list | None = None) -> dict:
    """Helper: run one audit on a project, return result_data dict.

    Pass ``file_paths`` explicitly to bypass auto-selection (needed when
    re-auditing a file that was already used in a previous audit).
    """
    from unittest.mock import patch
    with patch("app.api.routes.chat.get_llm", return_value=mock_llm):
        r = app_client.post(
            "/api/chat/stream",
            json={
                "project_id": project_id,
                "message": "audit",
                "file_paths": file_paths or [],
            },
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


def _setup_project_with_csv(app_client) -> tuple[str, str]:
    """Helper: create project and upload sample_tests.csv.
    Returns (project_id, file_path).
    """
    from pathlib import Path
    csv_path = Path(__file__).parent / "fixtures" / "sample_tests.csv"
    r = app_client.post("/api/projects/", json={"name": "snapshot-test"})
    assert r.status_code in (200, 201)
    project_id = r.json()["project_id"]
    with csv_path.open("rb") as fh:
        up = app_client.post(
            f"/api/files/{project_id}/upload",
            files={"files": (csv_path.name, fh, "text/csv")},
        )
    file_path = up.json()[0]["file_path"]
    return project_id, file_path


def _make_mock_llm():
    """Helper: mock LLM that always returns a valid recommendations array."""
    from unittest.mock import AsyncMock, MagicMock
    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(return_value='["Add more edge case tests."]')
    return mock_llm


def test_snapshot_saved_after_audit(app_client):
    """After one audit, exactly one AuditSnapshot must exist for the project."""
    import asyncio
    from app.db.engine import AsyncSessionLocal
    from app.db.models import AuditSnapshot
    from sqlalchemy import select

    project_id, _ = _setup_project_with_csv(app_client)
    result_data = _run_audit(app_client, project_id, _make_mock_llm())

    assert result_data, "No result event received"
    assert "snapshot_id" in result_data, "snapshot_id missing from result"

    async def _query():
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(AuditSnapshot).where(AuditSnapshot.project_id == project_id)
            )).scalars().all()
            return list(rows)

    snapshots = asyncio.get_event_loop().run_until_complete(_query())
    assert len(snapshots) == 1, f"Expected 1 snapshot, got {len(snapshots)}"

    snap = snapshots[0]
    assert snap.summary is not None
    summary = snap.summary
    assert "coverage_pct" in summary, f"summary missing coverage_pct: {summary}"
    assert any("sample_tests.csv" in p for p in snap.files_used or [])
    assert snap.diff is None, "First audit must have diff=None"


def test_diff_computed_on_second_audit(app_client):
    """Second audit on same project must have a non-null diff with expected keys."""
    import asyncio
    from app.db.engine import AsyncSessionLocal
    from app.db.models import AuditSnapshot
    from sqlalchemy import select

    project_id, file_path = _setup_project_with_csv(app_client)
    mock_llm = _make_mock_llm()
    _run_audit(app_client, project_id, mock_llm, file_paths=[file_path])
    _run_audit(app_client, project_id, mock_llm, file_paths=[file_path])

    async def _query():
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(AuditSnapshot)
                .where(AuditSnapshot.project_id == project_id)
                .order_by(AuditSnapshot.created_at.desc())
            )).scalars().all()
            return list(rows)

    snapshots = asyncio.get_event_loop().run_until_complete(_query())
    assert len(snapshots) == 2

    newest = snapshots[0]
    assert newest.diff is not None, "Second audit must have a diff"
    diff = newest.diff
    assert "coverage_delta" in diff
    assert "new_covered" in diff
    assert "files_added" in diff


def test_max_5_snapshots_enforced(app_client):
    """Running 6 audits must leave exactly 5 snapshots (oldest pruned)."""
    import asyncio
    from app.db.engine import AsyncSessionLocal
    from app.db.models import AuditSnapshot
    from sqlalchemy import select

    project_id, file_path = _setup_project_with_csv(app_client)
    mock_llm = _make_mock_llm()
    for _ in range(6):
        _run_audit(app_client, project_id, mock_llm, file_paths=[file_path])

    async def _query():
        async with AsyncSessionLocal() as db:
            rows = (await db.execute(
                select(AuditSnapshot).where(AuditSnapshot.project_id == project_id)
            )).scalars().all()
            return list(rows)

    snapshots = asyncio.get_event_loop().run_until_complete(_query())
    assert len(snapshots) == 5, f"Expected 5 snapshots, got {len(snapshots)}"


# ─────────────────────────────────────────────────────────────────────────────
# pytest: no false duplicates when CSV uses "title" column instead of "name"
# ─────────────────────────────────────────────────────────────────────────────

def test_no_false_duplicates_on_title_field(app_client):
    """
    synthetic_testcases_fr002_fr003.csv has 18 rows with a 'title' column
    (not 'name'). _find_duplicates must fall back to 'title' and report 0
    duplicates — all 18 titles are unique.
    """
    from pathlib import Path
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.agents.audit_workflow import AuditWorkflow

    csv_path = Path(__file__).parent / "fixtures" / "synthetic_docs" / "synthetic_testcases_fr002_fr003.csv"
    assert csv_path.exists(), f"Fixture missing: {csv_path}"

    # Create project — no M1 context needed for this test
    r = app_client.post("/api/projects/", json={"name": "no-false-dup-test"})
    assert r.status_code in (200, 201)
    project_id = r.json()["project_id"]

    with csv_path.open("rb") as fh:
        up = app_client.post(
            f"/api/files/{project_id}/upload",
            files={"files": (csv_path.name, fh, "text/csv")},
        )
    assert up.status_code == 200
    file_path = up.json()[0]["file_path"]

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(return_value='["Improve coverage."]')

    _EMPTY_COVERAGE = {
        "requirements_from_docs": [], "requirements_covered": [],
        "coverage_pct": 0.0, "requirements_total": 0,
        "requirements_covered_count": 0, "requirements_uncovered": [],
        "registry_available": False, "per_requirement_scores": [],
    }
    with patch("app.agents.audit_workflow.compute_registry_coverage", AsyncMock(return_value=_EMPTY_COVERAGE)), \
         patch("app.api.routes.chat.get_llm", return_value=mock_llm):
        chat_r = app_client.post(
            "/api/chat/stream",
            json={"project_id": project_id, "message": "audit", "file_paths": [file_path]},
        )
    assert chat_r.status_code == 200

    result_data: dict = {}
    for line in chat_r.text.splitlines():
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

    assert result_data, "No result event received"
    summary = result_data.get("summary", {})
    duplicates = result_data.get("duplicates", [])

    assert summary.get("duplicates_found") == 0, (
        f"Expected 0 duplicates for 18 unique titles, got: {summary.get('duplicates_found')}"
    )
    assert len(duplicates) == 0, (
        f"Expected empty duplicates list, got {len(duplicates)} entries"
    )


# ─────────────────────────────────────────────────────────────────────────────
# pytest: embedding-based duplicate detection — FR-002/FR-003 corpus
# ─────────────────────────────────────────────────────────────────────────────

def test_no_false_duplicates_fr002_fr003(app_client):
    """
    18 test cases covering FR-002 and FR-003.  Structurally similar tests
    (e.g. Visa vs Mastercard authorisation) must NOT be flagged as duplicates
    because their card numbers, scheme names, and expected responses differ.
    """
    from pathlib import Path
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.agents.audit_workflow import AuditWorkflow

    csv_path = (
        Path(__file__).parent / "fixtures" / "synthetic_docs" / "synthetic_testcases_fr002_fr003.csv"
    )
    assert csv_path.exists(), f"Fixture missing: {csv_path}"

    r = app_client.post("/api/projects/", json={"name": "emb-dup-fr002-test"})
    assert r.status_code in (200, 201)
    project_id = r.json()["project_id"]

    with csv_path.open("rb") as fh:
        up = app_client.post(
            f"/api/files/{project_id}/upload",
            files={"files": (csv_path.name, fh, "text/csv")},
        )
    assert up.status_code == 200
    file_path = up.json()[0]["file_path"]

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(return_value='["Improve coverage."]')

    _EMPTY_COVERAGE = {
        "requirements_from_docs": [], "requirements_covered": [],
        "coverage_pct": 0.0, "requirements_total": 0,
        "requirements_covered_count": 0, "requirements_uncovered": [],
        "registry_available": False, "per_requirement_scores": [],
    }
    with patch("app.agents.audit_workflow.compute_registry_coverage", AsyncMock(return_value=_EMPTY_COVERAGE)), \
         patch("app.api.routes.chat.get_llm", return_value=mock_llm):
        chat_r = app_client.post(
            "/api/chat/stream",
            json={"project_id": project_id, "message": "audit", "file_paths": [file_path]},
        )
    assert chat_r.status_code == 200

    result_data: dict = {}
    for line in chat_r.text.splitlines():
        if not line.startswith("data: "): continue
        payload = line[6:].strip()
        if payload == "[DONE]": break
        try:
            ev = json.loads(payload)
            if ev.get("type") == "result":
                result_data = ev["data"]
        except Exception:
            continue

    assert result_data, "No result event received"
    summary = result_data.get("summary", {})
    certain = result_data.get("certain_duplicates", [])

    assert summary.get("duplicates_found") == 0, (
        f"Expected 0 duplicates for 18 functionally distinct tests, "
        f"got: {summary.get('duplicates_found')} — certain: {certain}"
    )


def test_identical_tc_detected_as_certain_duplicate(app_client, tmp_path):
    """
    A CSV with two rows that have identical title, steps, and expected_result
    must be detected as a certain duplicate (similarity >= 0.98).
    """
    import csv as csv_mod
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.agents.audit_workflow import AuditWorkflow

    # Build a CSV with one genuine pair of identical test cases + one unique one
    csv_file = tmp_path / "dup_test.csv"
    rows = [
        {"test_id": "TC-001", "title": "Login with valid credentials",
         "steps": "1. Navigate to login page; 2. Enter username admin; 3. Enter password secret; 4. Click Submit",
         "expected_result": "User is redirected to dashboard; session token set in cookie"},
        {"test_id": "TC-002", "title": "Login with valid credentials",
         "steps": "1. Navigate to login page; 2. Enter username admin; 3. Enter password secret; 4. Click Submit",
         "expected_result": "User is redirected to dashboard; session token set in cookie"},
        {"test_id": "TC-003", "title": "Logout clears session",
         "steps": "1. Click logout button",
         "expected_result": "Session cookie deleted; user redirected to login page"},
    ]
    with csv_file.open("w", newline="") as f:
        writer = csv_mod.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    r = app_client.post("/api/projects/", json={"name": "dup-detection-test"})
    assert r.status_code in (200, 201)
    project_id = r.json()["project_id"]

    with csv_file.open("rb") as fh:
        up = app_client.post(
            f"/api/files/{project_id}/upload",
            files={"files": (csv_file.name, fh, "text/csv")},
        )
    assert up.status_code == 200
    file_path = up.json()[0]["file_path"]

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(return_value='["Add more tests."]')

    _EMPTY_COVERAGE = {
        "requirements_from_docs": [], "requirements_covered": [],
        "coverage_pct": 0.0, "requirements_total": 0,
        "requirements_covered_count": 0, "requirements_uncovered": [],
        "registry_available": False, "per_requirement_scores": [],
    }
    with patch("app.agents.audit_workflow.compute_registry_coverage", AsyncMock(return_value=_EMPTY_COVERAGE)), \
         patch("app.api.routes.chat.get_llm", return_value=mock_llm):
        chat_r = app_client.post(
            "/api/chat/stream",
            json={"project_id": project_id, "message": "audit", "file_paths": [file_path]},
        )
    assert chat_r.status_code == 200

    result_data: dict = {}
    for line in chat_r.text.splitlines():
        if not line.startswith("data: "): continue
        payload = line[6:].strip()
        if payload == "[DONE]": break
        try:
            ev = json.loads(payload)
            if ev.get("type") == "result":
                result_data = ev["data"]
        except Exception:
            continue

    assert result_data, "No result event received"
    summary = result_data.get("summary", {})
    certain = result_data.get("certain_duplicates", [])

    assert summary.get("duplicates_found", 0) >= 1, (
        f"Expected at least 1 duplicate for identical TC-001/TC-002, got 0"
    )
    assert len(certain) >= 1, (
        f"Expected TC-001/TC-002 pair in certain_duplicates, got: {certain}"
    )
    # Verify the right pair was flagged
    pair = certain[0]
    ids = {pair["tc_a"].get("test_id"), pair["tc_b"].get("test_id")}
    assert ids == {"TC-001", "TC-002"}, f"Wrong pair flagged: {ids}"
    assert pair["similarity"] >= 0.98, f"Expected sim >= 0.98, got {pair['similarity']}"


# ─────────────────────────────────────────────────────────────────────────────
# pytest: LLM judgment of embedding candidates
# ─────────────────────────────────────────────────────────────────────────────

def test_llm_judges_visa_mastercard_as_different(app_client):
    """
    Visa vs Mastercard authorisation tests have high embedding similarity
    but are functionally different. LLM verdict DIFFERENT → not in confirmed.
    """
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.agents.audit_workflow import AuditWorkflow

    tc_visa = {
        "test_id": "TC-FR002-001",
        "title": "Visa card authorisation accepted",
        "steps": "1. Submit authorisation request with Visa card number (4111111111111111); 2. Include valid expiry and CVV; 3. Send to POST /api/transactions/authorise",
        "expected_result": "Response HTTP 200; status=authorised; scheme=VISA returned in response body",
    }
    tc_mc = {
        "test_id": "TC-FR002-002",
        "title": "Mastercard authorisation accepted",
        "steps": "1. Submit authorisation request with Mastercard number (5500005555555559); 2. Include valid expiry and CVV; 3. Send to POST /api/transactions/authorise",
        "expected_result": "Response HTTP 200; status=authorised; scheme=MASTERCARD returned in response body",
    }
    candidate_pair = [{"tc_a": tc_visa, "tc_b": tc_mc, "similarity": 0.925}]

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(
        return_value='{"verdict": "DIFFERENT", "reason": "Tests target distinct card schemes with different card numbers and expected scheme values."}'
    )

    async def run():
        wf = AuditWorkflow.__new__(AuditWorkflow)
        wf.llm = mock_llm
        return await wf._judge_candidates_with_llm(candidate_pair)

    import asyncio
    confirmed = asyncio.get_event_loop().run_until_complete(run())

    assert len(confirmed) == 0, (
        f"Visa vs Mastercard must NOT be confirmed duplicate, got: {confirmed}"
    )
    mock_llm.acomplete.assert_called_once()


def test_report_includes_duplicate_pairs(app_client, tmp_path):
    """
    result['duplicates'] must be a list of formatted pairs with
    tc_a, tc_b, similarity, source keys (string labels, not raw dicts).
    """
    import csv as csv_mod
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.agents.audit_workflow import AuditWorkflow

    csv_file = tmp_path / "dup_pairs_format_test.csv"
    rows = [
        {"test_id": "TC-001", "title": "Login with valid credentials",
         "steps": "1. Navigate to login page; 2. Enter username admin; 3. Enter password secret; 4. Click Submit",
         "expected_result": "User is redirected to dashboard; session token set in cookie"},
        {"test_id": "TC-002", "title": "Login with valid credentials",
         "steps": "1. Navigate to login page; 2. Enter username admin; 3. Enter password secret; 4. Click Submit",
         "expected_result": "User is redirected to dashboard; session token set in cookie"},
        {"test_id": "TC-003", "title": "Logout clears session",
         "steps": "1. Click logout button",
         "expected_result": "Session cookie deleted; user redirected to login page"},
    ]
    with csv_file.open("w", newline="") as f:
        writer = csv_mod.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    r = app_client.post("/api/projects/", json={"name": "dup-pairs-format-test"})
    assert r.status_code in (200, 201)
    project_id = r.json()["project_id"]

    with csv_file.open("rb") as fh:
        up = app_client.post(
            f"/api/files/{project_id}/upload",
            files={"files": (csv_file.name, fh, "text/csv")},
        )
    assert up.status_code == 200
    file_path = up.json()[0]["file_path"]

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(return_value='["Add more tests."]')

    _EMPTY_COVERAGE = {
        "requirements_from_docs": [], "requirements_covered": [],
        "coverage_pct": 0.0, "requirements_total": 0,
        "requirements_covered_count": 0, "requirements_uncovered": [],
        "registry_available": False, "per_requirement_scores": [],
    }
    with patch("app.agents.audit_workflow.compute_registry_coverage", AsyncMock(return_value=_EMPTY_COVERAGE)), \
         patch("app.api.routes.chat.get_llm", return_value=mock_llm):
        chat_r = app_client.post(
            "/api/chat/stream",
            json={"project_id": project_id, "message": "audit", "file_paths": [file_path]},
        )
    assert chat_r.status_code == 200

    result_data: dict = {}
    for line in chat_r.text.splitlines():
        if not line.startswith("data: "): continue
        payload = line[6:].strip()
        if payload == "[DONE]": break
        try:
            ev = json.loads(payload)
            if ev.get("type") == "result":
                result_data = ev["data"]
        except Exception:
            continue

    assert result_data, "No result event received"
    duplicates = result_data.get("duplicates", [])
    summary = result_data.get("summary", {})

    assert summary.get("duplicates_found") == 1, (
        f"Expected duplicates_found=1, got {summary.get('duplicates_found')}"
    )
    assert len(duplicates) == 1, f"Expected 1 formatted duplicate pair, got {len(duplicates)}"

    pair = duplicates[0]
    for key in ("tc_a", "tc_b", "similarity", "source"):
        assert key in pair, f"Missing key '{key}' in duplicate pair: {pair}"

    assert isinstance(pair["tc_a"], str), f"tc_a must be a string label, got {type(pair['tc_a'])}"
    assert isinstance(pair["tc_b"], str), f"tc_b must be a string label, got {type(pair['tc_b'])}"
    assert pair["source"] == "certain", f"Expected source='certain', got {pair['source']}"
    assert pair["similarity"] >= 0.98, f"Expected similarity >= 0.98, got {pair['similarity']}"


def test_report_zero_duplicates_on_fr002_fr003(app_client):
    """
    FR-002/FR-003 test suite: summary must report duplicates_found=0
    and similar_pairs_found <= 3 (structurally related but functionally distinct).
    """
    from pathlib import Path
    from unittest.mock import AsyncMock, MagicMock, patch
    from app.agents.audit_workflow import AuditWorkflow

    csv_path = (
        Path(__file__).parent / "fixtures" / "synthetic_docs" / "synthetic_testcases_fr002_fr003.csv"
    )
    assert csv_path.exists(), f"Fixture missing: {csv_path}"

    r = app_client.post("/api/projects/", json={"name": "fr002-fr003-summary-test"})
    assert r.status_code in (200, 201)
    project_id = r.json()["project_id"]

    with csv_path.open("rb") as fh:
        up = app_client.post(
            f"/api/files/{project_id}/upload",
            files={"files": (csv_path.name, fh, "text/csv")},
        )
    assert up.status_code == 200
    file_path = up.json()[0]["file_path"]

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(return_value='["Improve coverage."]')

    _EMPTY_COVERAGE = {
        "requirements_from_docs": [], "requirements_covered": [],
        "coverage_pct": 0.0, "requirements_total": 0,
        "requirements_covered_count": 0, "requirements_uncovered": [],
        "registry_available": False, "per_requirement_scores": [],
    }
    with patch("app.agents.audit_workflow.compute_registry_coverage", AsyncMock(return_value=_EMPTY_COVERAGE)), \
         patch("app.api.routes.chat.get_llm", return_value=mock_llm):
        chat_r = app_client.post(
            "/api/chat/stream",
            json={"project_id": project_id, "message": "audit", "file_paths": [file_path]},
        )
    assert chat_r.status_code == 200

    result_data: dict = {}
    for line in chat_r.text.splitlines():
        if not line.startswith("data: "): continue
        payload = line[6:].strip()
        if payload == "[DONE]": break
        try:
            ev = json.loads(payload)
            if ev.get("type") == "result":
                result_data = ev["data"]
        except Exception:
            continue

    assert result_data, "No result event received"
    summary = result_data.get("summary", {})

    assert summary.get("duplicates_found") == 0, (
        f"Expected duplicates_found=0 for 18 functionally distinct tests, "
        f"got {summary.get('duplicates_found')}"
    )
    similar = summary.get("similar_pairs_found", 0)
    assert similar <= 3, (
        f"Expected similar_pairs_found <= 3, got {similar}"
    )


def test_llm_judges_identical_steps_as_duplicate(app_client):
    """
    Two test cases with identical title, steps, and expected_result but
    different test_id. LLM verdict DUPLICATE → appears in confirmed list.
    """
    from unittest.mock import AsyncMock, MagicMock
    from app.agents.audit_workflow import AuditWorkflow

    shared = {
        "title": "Login with valid credentials",
        "steps": "1. Navigate to login page; 2. Enter username admin; 3. Enter password secret; 4. Click Submit",
        "expected_result": "User is redirected to dashboard; session token set in cookie",
    }
    tc_a = {**shared, "test_id": "TC-001"}
    tc_b = {**shared, "test_id": "TC-002"}
    candidate_pair = [{"tc_a": tc_a, "tc_b": tc_b, "similarity": 0.997}]

    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(
        return_value='{"verdict": "DUPLICATE", "reason": "Both test cases have identical steps and expected outcomes."}'
    )

    async def run():
        wf = AuditWorkflow.__new__(AuditWorkflow)
        wf.llm = mock_llm
        return await wf._judge_candidates_with_llm(candidate_pair)

    import asyncio
    confirmed = asyncio.get_event_loop().run_until_complete(run())

    assert len(confirmed) == 1, (
        f"Identical TC-001/TC-002 must be confirmed duplicate, got: {confirmed}"
    )
    assert confirmed[0]["tc_a"]["test_id"] == "TC-001"
    assert confirmed[0]["tc_b"]["test_id"] == "TC-002"
    assert confirmed[0]["similarity"] == 0.997
    assert "reason" in confirmed[0]
