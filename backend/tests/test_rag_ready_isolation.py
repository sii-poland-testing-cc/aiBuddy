"""
rag_ready isolation tests
==========================
Regression tests for the bug where uploading M2 audit files (CSV/XLSX)
caused rag_ready=True in /api/context/{project_id}/status even though M1
had never run (no mindmap, no glossary).

Root cause: both M2 index_files() and M1 index_from_docs() write to the
same Chroma collection.  is_indexed() sees count > 0 and status endpoint
returns rag_ready=True before any M1 build.

Expected behaviour after fix:
  - rag_ready is False until M1 /build completes (context_built_at set in DB)
  - rag_ready reflects M1 context readiness, not M2 test-file indexing
"""

import json as _json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch as _patch

import pytest


def _make_m1_mock_llm():
    _entities = _json.dumps({
        "entities": [{"id": "e1", "name": "Test Case", "type": "data", "description": "A test scenario"}],
        "relations": [],
    })
    _glossary = _json.dumps([
        {"term": "Test Case", "definition": "Conditions to verify behaviour.", "related_terms": [], "source": "docs"},
    ])
    _approved = _json.dumps({"verdict": "APPROVED"})
    mock = MagicMock()

    async def _side(prompt, **kwargs):
        if "entities and their relationships" in prompt:
            return _entities
        if "glossary" in prompt.lower() and "documentation" in prompt:
            return _glossary
        return _approved

    mock.acomplete = AsyncMock(side_effect=_side)
    return mock

_FIXTURES = Path(__file__).parent / "fixtures"
_SAMPLE_CSV = _FIXTURES / "sample_tests.csv"


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _create_project(client, name: str) -> str:
    r = client.post("/api/projects/", json={"name": name})
    assert r.status_code in (200, 201), r.text
    return r.json()["project_id"]


def _upload_m2_csv(client, project_id: str) -> None:
    """Upload a CSV test-file (M2 audit source) to the project."""
    assert _SAMPLE_CSV.exists(), f"Fixture missing: {_SAMPLE_CSV}"
    with _SAMPLE_CSV.open("rb") as fh:
        r = client.post(
            f"/api/files/{project_id}/upload",
            files={"files": ("sample_tests.csv", fh, "text/csv")},
            params={"source_type": "file"},
        )
    assert r.status_code == 200, f"CSV upload failed: {r.text}"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Uploading M2 files must NOT set rag_ready=True
# ─────────────────────────────────────────────────────────────────────────────

def test_rag_ready_false_when_only_m2_files_indexed(app_client):
    """
    After uploading M2 audit test files (CSV), status must return rag_ready=False
    because M1 context has never been built.
    """
    pid = _create_project(app_client, "m2-only-rag-ready-test")
    _upload_m2_csv(app_client, pid)

    # Chroma is now populated (M2 files indexed) but M1 never ran
    status = app_client.get(f"/api/context/{pid}/status").json()

    assert status["rag_ready"] is False, (
        f"rag_ready should be False before M1 runs, got {status['rag_ready']}. "
        "M2 file indexing must not influence rag_ready."
    )
    assert status["artefacts_ready"] is False


# ─────────────────────────────────────────────────────────────────────────────
# 2. Mindmap + glossary endpoints must 404 before M1 runs (even with M2 files)
# ─────────────────────────────────────────────────────────────────────────────

def test_mindmap_glossary_404_before_m1_build(app_client):
    """
    /mindmap and /glossary must return 404 when only M2 test files are indexed.
    """
    pid = _create_project(app_client, "m2-only-artefacts-test")
    _upload_m2_csv(app_client, pid)

    mm_r = app_client.get(f"/api/context/{pid}/mindmap")
    gl_r = app_client.get(f"/api/context/{pid}/glossary")

    assert mm_r.status_code == 404, (
        f"Expected 404 for mindmap before M1 build, got {mm_r.status_code}"
    )
    assert gl_r.status_code == 404, (
        f"Expected 404 for glossary before M1 build, got {gl_r.status_code}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. After M1 build, rag_ready becomes True and artefacts are available
# ─────────────────────────────────────────────────────────────────────────────

def test_rag_ready_true_after_m1_build_with_prior_m2_files(app_client):
    """
    After running M1 /build (on top of existing M2 file uploads), rag_ready
    becomes True and mindmap + glossary are available.
    """
    _DOCX = _FIXTURES / "sample_domain.docx"
    assert _DOCX.exists(), f"Fixture missing: {_DOCX}"
    _DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    pid = _create_project(app_client, "m2-then-m1-test")

    # Upload M2 files first
    _upload_m2_csv(app_client, pid)

    # Confirm still not RAG-ready
    pre = app_client.get(f"/api/context/{pid}/status").json()
    assert pre["rag_ready"] is False

    # Now run M1 build
    with _patch("app.api.routes.context.get_llm", return_value=_make_m1_mock_llm()), \
         _DOCX.open("rb") as fh:
        build_r = app_client.post(
            f"/api/context/{pid}/build",
            files={"files": (_DOCX.name, fh, _DOCX_MIME)},
        )
    assert build_r.status_code == 200, f"M1 build failed: {build_r.text[:200]}"

    # After M1 completes, rag_ready must be True
    post = app_client.get(f"/api/context/{pid}/status").json()
    assert post["rag_ready"] is True, (
        f"rag_ready should be True after M1 build, got {post['rag_ready']}"
    )
    assert post["artefacts_ready"] is True

    # Artefacts accessible
    mm_r = app_client.get(f"/api/context/{pid}/mindmap")
    assert mm_r.status_code == 200
    gl_r = app_client.get(f"/api/context/{pid}/glossary")
    assert gl_r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 4. Completely fresh project (no uploads at all) must also return rag_ready=False
# ─────────────────────────────────────────────────────────────────────────────

def test_rag_ready_false_fresh_project(app_client):
    """
    A brand-new project with no uploads whatsoever must return rag_ready=False.
    Sanity baseline to distinguish the M2-upload regression.
    """
    pid = _create_project(app_client, "fresh-project-rag-ready")
    status = app_client.get(f"/api/context/{pid}/status").json()

    assert status["rag_ready"] is False
    assert status["artefacts_ready"] is False
