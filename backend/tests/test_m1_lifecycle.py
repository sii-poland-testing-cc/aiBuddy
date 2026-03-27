"""
Phase 4 — ArtifactVisibility manifest tests for M1 context build (D10 model).

Tests verify that:
- Graph nodes/edges and glossary terms are registered in artifact_visibility
- lifecycle_status is "promoted" when no work_context_id
- lifecycle_status is "draft" when work_context_id provided
- Visibility rows have correct source_context_id and visible_in_context_id
- source_origin is populated from source documents
- Append mode upserts (no duplicates)
- Rebuild mode clears and re-registers visibility rows
- ArtifactAuditLog rows emitted for new items
- find_by_source returns correct items
- GraphNodeAdapter, GraphEdgeAdapter, GlossaryAdapter conflict detection
- get_items_in_context queries via visibility manifest
"""

import asyncio
import json
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


def _get_visibility_rows(project_id: str) -> list:
    from app.db.engine import AsyncSessionLocal
    from app.db.models import ArtifactVisibility

    async def _q():
        async with AsyncSessionLocal() as db:
            stmt = sa_select(ArtifactVisibility).where(
                ArtifactVisibility.project_id == project_id,
                ArtifactVisibility.artifact_type.in_(["graph_node", "graph_edge", "glossary_term"]),
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
    """M1 build without work_context_id → all visibility rows have lifecycle_status='promoted'."""
    pid = _create_project(app_client, "test-promoted")
    _build(app_client, pid)

    rows = _get_visibility_rows(pid)
    assert len(rows) > 0, "Expected visibility rows after M1 build"
    for r in rows:
        assert r.lifecycle_status == "promoted", (
            f"Expected 'promoted' for {r.artifact_type}:{r.artifact_item_id}, got {r.lifecycle_status!r}"
        )
        assert r.source_context_id is None
        assert r.visible_in_context_id is None


def test_build_with_work_context_id_registers_draft(app_client):
    """M1 build with work_context_id → all visibility rows have lifecycle_status='draft'."""
    pid = _create_project(app_client, "test-draft")

    domain_resp = app_client.get(f"/api/work-contexts/{pid}")
    assert domain_resp.status_code == 200
    domains = domain_resp.json()["contexts"]
    assert len(domains) > 0
    domain_id = domains[0]["id"]

    epic_resp = app_client.post(
        f"/api/work-contexts/{pid}",
        json={"level": "epic", "name": "M1 Context Epic", "parent_id": domain_id},
    )
    assert epic_resp.status_code == 201
    epic_id = epic_resp.json()["id"]

    _build(app_client, pid, work_context_id=epic_id)

    rows = _get_visibility_rows(pid)
    assert len(rows) > 0, "Expected visibility rows"
    for r in rows:
        assert r.lifecycle_status == "draft", (
            f"Expected 'draft', got {r.lifecycle_status!r} for {r.artifact_type}:{r.artifact_item_id}"
        )
        assert r.source_context_id == epic_id
        assert r.visible_in_context_id == epic_id


def test_manifest_has_graph_nodes_edges_and_glossary(app_client):
    """Visibility rows must cover all three artifact types after a build."""
    pid = _create_project(app_client, "test-types")
    _build(app_client, pid)

    rows = _get_visibility_rows(pid)
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
    """Append mode upserts — building twice with same docs must not double visibility rows."""
    pid = _create_project(app_client, "test-append-upsert")
    _build(app_client, pid, mode="append")
    count_after_first = len(_get_visibility_rows(pid))

    _build(app_client, pid, mode="append")
    count_after_second = len(_get_visibility_rows(pid))

    assert count_after_second == count_after_first, (
        f"Visibility grew on second append: {count_after_first} → {count_after_second} (expected same)"
    )


def test_rebuild_mode_clears_and_reregisters(app_client):
    """Rebuild mode clears all visibility rows then re-registers fresh ones."""
    pid = _create_project(app_client, "test-rebuild-vis")
    _build(app_client, pid, mode="append")
    count_after_append = len(_get_visibility_rows(pid))
    assert count_after_append > 0

    _build(app_client, pid, mode="rebuild")
    count_after_rebuild = len(_get_visibility_rows(pid))
    assert count_after_rebuild > 0, "Expected visibility rows after rebuild"
    assert count_after_rebuild == count_after_append, (
        f"Expected {count_after_append} visibility rows after rebuild, got {count_after_rebuild}"
    )


# ─── Tests: source_origin populated ──────────────────────────────────────────

def test_source_origin_populated(app_client):
    """Visibility rows have source_origin set to the input document filename."""
    pid = _create_project(app_client, "test-source-origin")
    _build(app_client, pid)

    rows = _get_visibility_rows(pid)
    assert len(rows) > 0
    for r in rows:
        assert r.source_origin is not None, (
            f"source_origin not set for {r.artifact_type}:{r.artifact_item_id}"
        )
        assert r.source_origin.endswith(".docx"), (
            f"Expected .docx source_origin, got {r.source_origin!r}"
        )
        assert r.source_origin_type == "file"


# ─── Tests: find_by_source ───────────────────────────────────────────────────

def test_find_by_source_returns_items(app_client):
    """find_by_source returns graph/glossary items from a specific source file."""
    from app.db.engine import AsyncSessionLocal
    from app.services.context_lifecycle import find_by_source

    pid = _create_project(app_client, "test-find-source")
    _build(app_client, pid)

    async def _check():
        async with AsyncSessionLocal() as db:
            items = await find_by_source(db, pid, "srs_payment_module.docx")
            assert len(items) > 0
            types = {i["artifact_type"] for i in items}
            assert "graph_node" in types or "glossary_term" in types

            # Filter by type
            nodes_only = await find_by_source(db, pid, "srs_payment_module.docx", artifact_type="graph_node")
            for item in nodes_only:
                assert item["artifact_type"] == "graph_node"

            # Nonexistent source returns empty
            empty = await find_by_source(db, pid, "nonexistent.pdf")
            assert len(empty) == 0

    asyncio.get_event_loop().run_until_complete(_check())


# ─── Tests: get_items_in_context via visibility ──────────────────────────────

def test_graph_node_adapter_get_items_via_visibility(app_client):
    """GraphNodeAdapter.get_items_in_context queries via artifact_visibility + artifact_versions."""
    from app.db.engine import AsyncSessionLocal
    from app.db.models import ArtifactVersion, ArtifactVisibility, WorkContext, Project
    from app.lifecycle.graph_adapter import GraphNodeAdapter

    pid = _create_project(app_client, "test-node-vis-query")

    async def _run():
        async with AsyncSessionLocal() as db:
            # Create two contexts
            ctx_a = WorkContext(project_id=pid, level="epic", name="Epic A", status="active")
            db.add(ctx_a)
            await db.flush()
            ctx_b = WorkContext(project_id=pid, level="epic", name="Epic B", status="active")
            db.add(ctx_b)
            await db.flush()

            # Set up mind_map JSON on the project (kept for fallback compat)
            project = await db.get(Project, pid)
            project.mind_map = {
                "nodes": [
                    {"id": "n1", "label": "Node One", "type": "system"},
                    {"id": "n2", "label": "Node Two", "type": "actor"},
                ],
                "edges": [],
            }
            await db.flush()

            # D12: Create version snapshots for each node
            import uuid as _uuid
            ver_n1_id = str(_uuid.uuid4())
            db.add(ArtifactVersion(
                id=ver_n1_id, project_id=pid, artifact_type="graph_node",
                artifact_item_id="n1", version_number=1,
                content_snapshot={"id": "n1", "label": "Node One", "type": "system"},
                created_in_context_id=ctx_a.id, change_summary="initial version",
                created_by="system",
            ))
            ver_n2_id = str(_uuid.uuid4())
            db.add(ArtifactVersion(
                id=ver_n2_id, project_id=pid, artifact_type="graph_node",
                artifact_item_id="n2", version_number=1,
                content_snapshot={"id": "n2", "label": "Node Two", "type": "actor"},
                created_in_context_id=ctx_b.id, change_summary="initial version",
                created_by="system",
            ))

            # Visibility: n1 visible in ctx_a, n2 visible in ctx_b (with version IDs)
            db.add(ArtifactVisibility(
                project_id=pid, artifact_type="graph_node",
                artifact_item_id="n1",
                source_context_id=ctx_a.id, visible_in_context_id=ctx_a.id,
                lifecycle_status="draft",
                artifact_version_id=ver_n1_id,
            ))
            db.add(ArtifactVisibility(
                project_id=pid, artifact_type="graph_node",
                artifact_item_id="n2",
                source_context_id=ctx_b.id, visible_in_context_id=ctx_b.id,
                lifecycle_status="draft",
                artifact_version_id=ver_n2_id,
            ))
            await db.commit()

        async with AsyncSessionLocal() as db:
            adapter = GraphNodeAdapter(db)

            items_a = await adapter.get_items_in_context(pid, ctx_a.id)
            assert len(items_a) == 1
            assert items_a[0]["id"] == "n1"

            items_b = await adapter.get_items_in_context(pid, ctx_b.id)
            assert len(items_b) == 1
            assert items_b[0]["id"] == "n2"

    asyncio.get_event_loop().run_until_complete(_run())


def test_glossary_adapter_get_items_via_visibility(app_client):
    """GlossaryAdapter.get_items_in_context queries via artifact_visibility + artifact_versions."""
    from app.db.engine import AsyncSessionLocal
    from app.db.models import ArtifactVersion, ArtifactVisibility, WorkContext, Project
    from app.lifecycle.glossary_adapter import GlossaryAdapter

    pid = _create_project(app_client, "test-glossary-vis-query")

    async def _run():
        async with AsyncSessionLocal() as db:
            ctx = WorkContext(project_id=pid, level="epic", name="Epic", status="active")
            db.add(ctx)
            await db.flush()

            project = await db.get(Project, pid)
            project.glossary = [
                {"term": "Payment", "definition": "Money transfer"},
                {"term": "Refund", "definition": "Return of funds"},
            ]
            await db.flush()

            # D12: Create version snapshot for "payment"
            import uuid as _uuid
            ver_id = str(_uuid.uuid4())
            db.add(ArtifactVersion(
                id=ver_id, project_id=pid, artifact_type="glossary_term",
                artifact_item_id="payment", version_number=1,
                content_snapshot={"term": "Payment", "definition": "Money transfer",
                                  "related_terms": None, "source": None},
                created_in_context_id=ctx.id, change_summary="initial version",
                created_by="system",
            ))

            # Only "payment" visible in ctx (with version ID)
            db.add(ArtifactVisibility(
                project_id=pid, artifact_type="glossary_term",
                artifact_item_id="payment",
                source_context_id=ctx.id, visible_in_context_id=ctx.id,
                lifecycle_status="draft",
                artifact_version_id=ver_id,
            ))
            await db.commit()

        async with AsyncSessionLocal() as db:
            adapter = GlossaryAdapter(db)
            items = await adapter.get_items_in_context(pid, ctx.id)
            assert len(items) == 1
            assert items[0]["term"] == "Payment"

    asyncio.get_event_loop().run_until_complete(_run())


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
