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

    # 2. Build M1 context (indexes document into Chroma)
    with docx_path.open("rb") as fh:
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

    with patch("app.api.routes.chat.get_llm", return_value=mock_llm):
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

    with docx_path.open("rb") as fh:
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

    with docx_path.open("rb") as fh:
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

    # 3. Patch _extract_requirements to return 10 deterministic FRs.
    #    Pattern matching in _requirements_in_tests will find FR-002 and FR-003
    #    from the sample CSV test case names — the other 8 are uncovered.
    FAKE_REQS = [
        "FR-001", "FR-002", "FR-003", "FR-004", "FR-005",
        "FR-006", "FR-007", "FR-008", "FR-009", "FR-010",
    ]
    mock_llm = MagicMock()
    mock_llm.acomplete = AsyncMock(
        return_value='["Add tests for uncovered FRs","Improve tag coverage",'
                     '"Review FR-001 scenarios","Add negative tests","Add integration tests"]'
    )

    with patch.object(AuditWorkflow, "_extract_requirements", AsyncMock(return_value=FAKE_REQS)), \
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
    _extract_requirements is patched to return [] (simulates empty RAG context).
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

    with patch.object(AuditWorkflow, "_extract_requirements", AsyncMock(return_value=[])), \
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
    summary = json.loads(snap.summary)
    assert "coverage_pct" in summary, f"summary missing coverage_pct: {summary}"
    assert any("sample_tests.csv" in p for p in json.loads(snap.files_used or "[]"))
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
    diff = json.loads(newest.diff)
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
