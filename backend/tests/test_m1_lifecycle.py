"""
Phase 4 — ArtifactLifecycle manifest tests for M1 context build.

Tests verify that:
- Graph nodes/edges and glossary terms are registered in artifact_lifecycle
- lifecycle_status is "promoted" when no work_context_id
- lifecycle_status is "draft" when work_context_id provided
- Append mode upserts (no duplicates)
- Rebuild mode clears and re-registers manifest rows
- ArtifactAuditLog rows emitted for new items
- GraphNodeAdapter, GraphEdgeAdapter, GlossaryAdapter conflict detection
"""

import asyncio
import json
from io import BytesIO
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sqlalchemy import select as sa_select

_SYNTHETIC = Path(__file__).parent / "fixtures" / "synthetic_docs"
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

# ─── Mock LLM ────────────────────────────────────────────────────────────────

_MOCK_ENTITIES = json.dumps({
    "entities": [
        {"id": "e1", "name": "Payment Gateway", "type": "system", "description": "Processes payments"},
        {"id": "e2", "name": "QA Engineer", "type": "actor", "description": "Runs tests"},
    ],
    "relations": [
        {"source": "e1", "target": "e2", "label": "tested by"},
    ],
})
_MOCK_TERMS = json.dumps(["Payment Gateway", "QA Engineer"])
_MOCK_DEFINITIONS = json.dumps([
    {"term": "Payment Gateway", "definition": "A system that processes financial transactions.", "related_terms": [], "source": "docs"},
    {"term": "QA Engineer", "definition": "A professional responsible for quality assurance.", "related_terms": [], "source": "docs"},
])
_MOCK_APPROVED = json.dumps({"verdict": "APPROVED"})


def _make_mock_llm():
    mock = MagicMock()

    async def _side(prompt, **kwargs):
        if "entities and their relationships" in prompt:
            return _MOCK_ENTITIES
        if "domain-specific term" in prompt:
            return _MOCK_TERMS
        if "Write glossary definitions" in prompt:
            return _MOCK_DEFINITIONS
        return _MOCK_APPROVED

    mock.acomplete = AsyncMock(side_effect=_side)
    return mock


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _create_project(app_client, name: str = "lifecycle-test") -> str:
    r = app_client.post("/api/projects/", json={"name": name})
    assert r.status_code in (200, 201)
    return r.json()["project_id"]


def _build(client, project_id: str, work_context_id=None, mode: str = "append"):
    path = _SYNTHETIC / "srs_payment_module.docx"
    assert path.exists(), f"Fixture missing: {path}"
    url = f"/api/context/{project_id}/build?mode={mode}"
    if work_context_id:
        url += f"&work_context_id={work_context_id}"
    with patch("app.api.routes.context.get_llm", return_value=_make_mock_llm()), \
         path.open("rb") as fh:
        r = client.post(url, files={"files": (path.name, fh, _DOCX_MIME)})
    assert r.status_code == 200, f"Build failed: {r.text[:300]}"
    # Consume SSE stream
    for line in r.text.splitlines():
        if line.startswith("data: "):
            payload = line[6:].strip()
            if payload == "[DONE]":
                break
            try:
                ev = json.loads(payload)
                if ev.get("type") == "error":
                    raise AssertionError(f"M1 build returned error: {ev['data']}")
            except json.JSONDecodeError:
                pass


def _get_manifest_rows(project_id: str) -> list:
    from app.db.engine import AsyncSessionLocal
    from app.db.models import ArtifactLifecycle

    async def _q():
        async with AsyncSessionLocal() as db:
            stmt = sa_select(ArtifactLifecycle).where(
                ArtifactLifecycle.project_id == project_id
            )
            return (await db.execute(stmt)).scalars().all()

    return asyncio.get_event_loop().run_until_complete(_q())


def _get_audit_log_rows(project_id: str) -> list:
    from app.db.engine import AsyncSessionLocal
    from app.db.models import ArtifactAuditLog

    async def _q():
        async with AsyncSessionLocal() as db:
            stmt = sa_select(ArtifactAuditLog).where(
                ArtifactAuditLog.project_id == project_id,
                ArtifactAuditLog.event_type == "created",
                ArtifactAuditLog.artifact_type.in_(["graph_node", "graph_edge", "glossary_term"]),
            )
            return (await db.execute(stmt)).scalars().all()

    return asyncio.get_event_loop().run_until_complete(_q())


# ─── Tests: lifecycle_status ─────────────────────────────────────────────────

def test_build_without_work_context_id_registers_promoted(app_client):
    """M1 build without work_context_id → all manifest rows have lifecycle_status='promoted'."""
    pid = _create_project(app_client, "test-promoted")
    _build(app_client, pid)

    rows = _get_manifest_rows(pid)
    assert len(rows) > 0, "Expected manifest rows after M1 build"
    for r in rows:
        assert r.lifecycle_status == "promoted", (
            f"Expected 'promoted' for {r.artifact_type}:{r.artifact_item_id}, got {r.lifecycle_status!r}"
        )
        assert r.work_context_id is None


def test_build_with_work_context_id_registers_draft(app_client):
    """M1 build with work_context_id → all manifest rows have lifecycle_status='draft'."""
    pid = _create_project(app_client, "test-draft")

    # Get the auto-created default domain
    domain_resp = app_client.get(f"/api/work-contexts/{pid}")
    assert domain_resp.status_code == 200
    domains = domain_resp.json()["contexts"]
    assert len(domains) > 0
    domain_id = domains[0]["id"]

    # Create an epic under the domain
    epic_resp = app_client.post(
        f"/api/work-contexts/{pid}",
        json={"level": "epic", "name": "M1 Context Epic", "parent_id": domain_id},
    )
    assert epic_resp.status_code == 201
    epic_id = epic_resp.json()["id"]

    _build(app_client, pid, work_context_id=epic_id)

    rows = _get_manifest_rows(pid)
    assert len(rows) > 0, "Expected manifest rows"
    for r in rows:
        assert r.lifecycle_status == "draft", (
            f"Expected 'draft', got {r.lifecycle_status!r} for {r.artifact_type}:{r.artifact_item_id}"
        )
        assert r.work_context_id == epic_id


def test_manifest_has_graph_nodes_edges_and_glossary(app_client):
    """Manifest rows must cover all three artifact types after a build."""
    pid = _create_project(app_client, "test-types")
    _build(app_client, pid)

    rows = _get_manifest_rows(pid)
    types = {r.artifact_type for r in rows}
    assert "graph_node" in types, f"Missing graph_node in {types}"
    assert "graph_edge" in types, f"Missing graph_edge in {types}"
    assert "glossary_term" in types, f"Missing glossary_term in {types}"


def test_audit_log_emitted_for_new_items(app_client):
    """ArtifactAuditLog rows with event_type='created' exist after M1 build."""
    pid = _create_project(app_client, "test-auditlog")
    _build(app_client, pid)

    rows = _get_audit_log_rows(pid)
    assert len(rows) > 0, "Expected AuditLog rows after M1 build"
    types = {r.artifact_type for r in rows}
    assert "graph_node" in types
    assert "glossary_term" in types


def test_append_mode_no_duplicates(app_client):
    """Append mode upserts — building twice with same docs must not double manifest rows."""
    pid = _create_project(app_client, "test-append-upsert")
    _build(app_client, pid, mode="append")
    count_after_first = len(_get_manifest_rows(pid))

    _build(app_client, pid, mode="append")
    count_after_second = len(_get_manifest_rows(pid))

    assert count_after_second == count_after_first, (
        f"Manifest grew on second append: {count_after_first} → {count_after_second} (expected same)"
    )


def test_rebuild_mode_clears_and_reregisters(app_client):
    """Rebuild mode clears all manifest rows then re-registers fresh ones."""
    pid = _create_project(app_client, "test-rebuild-manifest")
    _build(app_client, pid, mode="append")
    count_after_append = len(_get_manifest_rows(pid))
    assert count_after_append > 0

    _build(app_client, pid, mode="rebuild")
    count_after_rebuild = len(_get_manifest_rows(pid))
    assert count_after_rebuild > 0, "Expected manifest rows after rebuild"
    # After rebuild the count should equal the re-registered count
    # (same mock data → same count as after first append)
    assert count_after_rebuild == count_after_append, (
        f"Expected {count_after_append} manifest rows after rebuild, got {count_after_rebuild}"
    )


# ─── Tests: adapter detect_conflict ──────────────────────────────────────────

def test_graph_node_adapter_conflict_label_mismatch():
    """GraphNodeAdapter: same id, different label → conflict."""
    from app.lifecycle.graph_adapter import GraphNodeAdapter
    adapter = GraphNodeAdapter(db=None)  # type: ignore[arg-type]

    incoming = {"id": "e1", "label": "Payment Service", "type": "system"}
    existing = {"id": "e1", "label": "Legacy Billing Module", "type": "system"}

    has_conflict, reason = adapter.detect_conflict(incoming, existing)
    assert has_conflict is True
    assert "label_mismatch" in reason


def test_graph_node_adapter_conflict_type_mismatch():
    """GraphNodeAdapter: same id, different type → conflict."""
    from app.lifecycle.graph_adapter import GraphNodeAdapter
    adapter = GraphNodeAdapter(db=None)  # type: ignore[arg-type]

    incoming = {"id": "e1", "label": "QA Engineer", "type": "actor"}
    existing = {"id": "e1", "label": "QA Engineer", "type": "process"}

    has_conflict, reason = adapter.detect_conflict(incoming, existing)
    assert has_conflict is True
    assert "type_mismatch" in reason


def test_graph_node_adapter_no_conflict_same_node():
    """GraphNodeAdapter: same id, same label, same type → no conflict."""
    from app.lifecycle.graph_adapter import GraphNodeAdapter
    adapter = GraphNodeAdapter(db=None)  # type: ignore[arg-type]

    node = {"id": "e1", "label": "Payment Gateway", "type": "system"}
    has_conflict, reason = adapter.detect_conflict(node, dict(node))
    assert has_conflict is False
    assert reason == ""


def test_graph_node_adapter_no_conflict_different_ids():
    """GraphNodeAdapter: different ids → always no conflict."""
    from app.lifecycle.graph_adapter import GraphNodeAdapter
    adapter = GraphNodeAdapter(db=None)  # type: ignore[arg-type]

    incoming = {"id": "e1", "label": "A", "type": "system"}
    existing = {"id": "e2", "label": "B", "type": "actor"}
    has_conflict, _ = adapter.detect_conflict(incoming, existing)
    assert has_conflict is False


def test_graph_edge_adapter_conflict_label_mismatch():
    """GraphEdgeAdapter: same source/target pair, different label → conflict."""
    from app.lifecycle.graph_adapter import GraphEdgeAdapter
    adapter = GraphEdgeAdapter(db=None)  # type: ignore[arg-type]

    incoming = {"source": "e1", "target": "e2", "label": "tests"}
    existing = {"source": "e1", "target": "e2", "label": "verifies"}

    has_conflict, reason = adapter.detect_conflict(incoming, existing)
    assert has_conflict is True
    assert "label_mismatch" in reason


def test_graph_edge_adapter_no_conflict_same_label():
    """GraphEdgeAdapter: same source/target/label → no conflict."""
    from app.lifecycle.graph_adapter import GraphEdgeAdapter
    adapter = GraphEdgeAdapter(db=None)  # type: ignore[arg-type]

    edge = {"source": "e1", "target": "e2", "label": "tests"}
    has_conflict, reason = adapter.detect_conflict(edge, dict(edge))
    assert has_conflict is False
    assert reason == ""


def test_graph_edge_adapter_no_conflict_different_pairs():
    """GraphEdgeAdapter: different source/target pairs → no conflict."""
    from app.lifecycle.graph_adapter import GraphEdgeAdapter
    adapter = GraphEdgeAdapter(db=None)  # type: ignore[arg-type]

    incoming = {"source": "e1", "target": "e2", "label": "tests"}
    existing = {"source": "e3", "target": "e4", "label": "verifies"}
    has_conflict, _ = adapter.detect_conflict(incoming, existing)
    assert has_conflict is False


def test_glossary_adapter_conflict_definition_mismatch():
    """GlossaryAdapter: same term, low definition similarity < 0.85 → conflict (D9)."""
    from app.lifecycle.glossary_adapter import GlossaryAdapter
    adapter = GlossaryAdapter(db=None)  # type: ignore[arg-type]

    incoming = {
        "term": "Test Case",
        "definition": "A test case is a set of conditions to validate system correctness.",
    }
    existing = {
        "term": "test case",
        "definition": "A financial instrument used in payment processing workflows.",
    }

    has_conflict, reason = adapter.detect_conflict(incoming, existing)
    assert has_conflict is True
    assert "definition_mismatch" in reason


def test_glossary_adapter_no_conflict_similar_definition():
    """GlossaryAdapter: same term, similar definitions (ratio ≥ 0.85) → no conflict."""
    from app.lifecycle.glossary_adapter import GlossaryAdapter
    adapter = GlossaryAdapter(db=None)  # type: ignore[arg-type]

    incoming = {
        "term": "QA Engineer",
        "definition": "A professional responsible for quality assurance of software.",
    }
    existing = {
        "term": "QA Engineer",
        "definition": "A professional responsible for quality assurance of software products.",
    }

    has_conflict, reason = adapter.detect_conflict(incoming, existing)
    assert has_conflict is False
    assert reason == ""


def test_glossary_adapter_no_conflict_different_terms():
    """GlossaryAdapter: different terms → no conflict regardless of definitions."""
    from app.lifecycle.glossary_adapter import GlossaryAdapter
    adapter = GlossaryAdapter(db=None)  # type: ignore[arg-type]

    incoming = {"term": "Test Case", "definition": "A test condition."}
    existing = {"term": "Defect", "definition": "A bug in software."}
    has_conflict, _ = adapter.detect_conflict(incoming, existing)
    assert has_conflict is False
