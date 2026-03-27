"""
test_migration_009.py — Phase 8.1: versioning table + backfill tests.

These tests run the migration 009 logic against an in-memory SQLite database
seeded with pre-migration data. They verify:
  - artifact_versions table is created with correct schema
  - artifact_visibility gains artifact_version_id column
  - Backfill creates exactly one v1 per unique item
  - All visibility rows get artifact_version_id set
  - Content snapshots are read from authoritative sources
  - Items with no readable content are skipped
"""

import importlib.util
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

# ── Load the migration module ────────────────────────────────────────────────

_MIGRATION_PATH = Path(__file__).parent.parent / "migrations" / "versions" / "009_add_versioning.py"
_spec = importlib.util.spec_from_file_location("migration_009", _MIGRATION_PATH)
_migration = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_migration)  # type: ignore[union-attr]

_read_content = _migration._read_content
_safe_json = _migration._safe_json

# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_engine():
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )


def _build_schema(conn):
    """Create schema as it exists AFTER migration 008 (before 009)."""
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            created_at TEXT,
            mind_map TEXT,
            glossary TEXT,
            context_stats TEXT,
            context_built_at TEXT,
            context_files TEXT,
            requirement_gaps TEXT,
            settings TEXT
        )
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS work_contexts (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            parent_id TEXT REFERENCES work_contexts(id) ON DELETE SET NULL,
            level TEXT NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'draft',
            created_at TEXT,
            updated_at TEXT,
            promoted_at TEXT
        )
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS requirements (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            parent_id TEXT,
            level TEXT NOT NULL DEFAULT 'functional_req',
            external_id TEXT,
            title TEXT NOT NULL,
            description TEXT,
            source_type TEXT NOT NULL DEFAULT 'formal',
            source_references TEXT,
            taxonomy TEXT,
            completeness_score REAL,
            confidence REAL,
            human_reviewed INTEGER DEFAULT 0,
            needs_review INTEGER DEFAULT 0,
            review_reason TEXT,
            created_at TEXT,
            updated_at TEXT,
            work_context_id TEXT,
            lifecycle_status TEXT DEFAULT 'promoted',
            source_origin TEXT,
            source_origin_type TEXT,
            promoted_to_context_id TEXT
        )
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS artifact_visibility (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            artifact_type TEXT NOT NULL,
            artifact_item_id TEXT NOT NULL,
            source_context_id TEXT,
            visible_in_context_id TEXT,
            lifecycle_status TEXT NOT NULL DEFAULT 'draft',
            sibling_of TEXT,
            source_origin TEXT,
            source_origin_type TEXT,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(project_id, artifact_type, artifact_item_id, visible_in_context_id)
        )
    """))


def _seed_project(conn, project_id="proj1", mind_map=None, glossary=None):
    conn.execute(
        text("INSERT INTO projects (id, name, mind_map, glossary) VALUES (:id, :name, :mm, :gl)"),
        {
            "id": project_id,
            "name": "Test Project",
            "mm": json.dumps(mind_map) if mind_map else None,
            "gl": json.dumps(glossary) if glossary else None,
        },
    )


def _seed_domain(conn, project_id="proj1", domain_id="dom1"):
    conn.execute(
        text("INSERT INTO work_contexts (id, project_id, level, name, status) VALUES (:id, :pid, 'domain', 'Domain', 'draft')"),
        {"id": domain_id, "pid": project_id},
    )


def _seed_requirement(conn, req_id, project_id="proj1", title="Test Req", description="Desc",
                       source_refs=None, taxonomy=None, confidence=0.9):
    conn.execute(
        text(
            "INSERT INTO requirements (id, project_id, title, description, source_references, "
            "taxonomy, confidence, level, source_type, created_at) "
            "VALUES (:id, :pid, :title, :desc, :sr, :tax, :conf, 'functional_req', 'formal', :now)"
        ),
        {
            "id": req_id,
            "pid": project_id,
            "title": title,
            "desc": description,
            "sr": json.dumps(source_refs) if source_refs else None,
            "tax": json.dumps(taxonomy) if taxonomy else None,
            "conf": confidence,
            "now": datetime.now(timezone.utc).isoformat(),
        },
    )


def _seed_visibility(conn, project_id, artifact_type, item_id, source_ctx_id=None, visible_ctx_id=None):
    conn.execute(
        text(
            "INSERT INTO artifact_visibility (id, project_id, artifact_type, artifact_item_id, "
            "source_context_id, visible_in_context_id, lifecycle_status, created_at) "
            "VALUES (:id, :pid, :at, :iid, :scid, :vcid, 'promoted', :now)"
        ),
        {
            "id": str(uuid.uuid4()),
            "pid": project_id,
            "at": artifact_type,
            "iid": item_id,
            "scid": source_ctx_id,
            "vcid": visible_ctx_id,
            "now": datetime.now(timezone.utc).isoformat(),
        },
    )


def _run_upgrade(conn):
    """Run the backfill logic from migration 009 directly."""
    now = _migration._now_iso()

    items = conn.execute(
        text(
            "SELECT DISTINCT project_id, artifact_type, artifact_item_id, "
            "source_context_id FROM artifact_visibility"
        )
    ).fetchall()

    for row in items:
        project_id, artifact_type, item_id, source_ctx_id = row[0], row[1], row[2], row[3]
        content = _read_content(conn, project_id, artifact_type, item_id)
        if content is None:
            continue

        version_id = str(uuid.uuid4())
        conn.execute(
            text(
                "INSERT INTO artifact_versions "
                "(id, project_id, artifact_type, artifact_item_id, version_number, "
                " content_snapshot, created_in_context_id, change_summary, "
                " created_by, created_at) "
                "VALUES (:id, :pid, :atype, :item_id, 1, :content, :ctx_id, "
                "        :summary, 'system', :now)"
            ),
            {
                "id": version_id,
                "pid": project_id,
                "atype": artifact_type,
                "item_id": item_id,
                "content": json.dumps(content),
                "ctx_id": source_ctx_id,
                "summary": "initial version (backfill)",
                "now": now,
            },
        )
        conn.execute(
            text(
                "UPDATE artifact_visibility SET artifact_version_id = :vid "
                "WHERE project_id = :pid AND artifact_type = :atype "
                "AND artifact_item_id = :item_id"
            ),
            {"vid": version_id, "pid": project_id, "atype": artifact_type, "item_id": item_id},
        )


def _create_versions_table(conn):
    """Create artifact_versions table (DDL portion of migration 009)."""
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS artifact_versions (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            artifact_type TEXT NOT NULL,
            artifact_item_id TEXT NOT NULL,
            version_number INTEGER NOT NULL,
            content_snapshot TEXT,
            created_in_context_id TEXT REFERENCES work_contexts(id) ON DELETE SET NULL,
            change_summary TEXT,
            created_by TEXT NOT NULL DEFAULT 'system',
            created_at TEXT,
            UNIQUE(project_id, artifact_type, artifact_item_id, version_number)
        )
    """))
    # Add artifact_version_id to artifact_visibility
    conn.execute(text(
        "ALTER TABLE artifact_visibility ADD COLUMN artifact_version_id TEXT "
        "REFERENCES artifact_versions(id) ON DELETE SET NULL"
    ))


# ── Tests ────────────────────────────────────────────────────────────────────

class TestMigration009Schema:
    """Verify artifact_versions table creation and FK on visibility."""

    def test_artifact_versions_table_created(self):
        engine = _make_engine()
        with engine.begin() as conn:
            _build_schema(conn)
            _create_versions_table(conn)
            tables = [r[0] for r in conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()]
            assert "artifact_versions" in tables

    def test_artifact_versions_columns(self):
        engine = _make_engine()
        with engine.begin() as conn:
            _build_schema(conn)
            _create_versions_table(conn)
            cols = {r[1] for r in conn.execute(text("PRAGMA table_info(artifact_versions)")).fetchall()}
            expected = {"id", "project_id", "artifact_type", "artifact_item_id",
                        "version_number", "content_snapshot", "created_in_context_id",
                        "change_summary", "created_by", "created_at"}
            assert expected.issubset(cols)

    def test_artifact_visibility_has_version_fk(self):
        engine = _make_engine()
        with engine.begin() as conn:
            _build_schema(conn)
            _create_versions_table(conn)
            cols = {r[1] for r in conn.execute(text("PRAGMA table_info(artifact_visibility)")).fetchall()}
            assert "artifact_version_id" in cols

    def test_unique_constraint_on_versions(self):
        engine = _make_engine()
        with engine.begin() as conn:
            _build_schema(conn)
            _create_versions_table(conn)
            _seed_project(conn)
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(text(
                "INSERT INTO artifact_versions (id, project_id, artifact_type, artifact_item_id, "
                "version_number, created_by, created_at) "
                "VALUES (:id, 'proj1', 'requirement', 'r1', 1, 'system', :now)"
            ), {"id": str(uuid.uuid4()), "now": now})
            with pytest.raises(Exception):
                conn.execute(text(
                    "INSERT INTO artifact_versions (id, project_id, artifact_type, artifact_item_id, "
                    "version_number, created_by, created_at) "
                    "VALUES (:id, 'proj1', 'requirement', 'r1', 1, 'system', :now)"
                ), {"id": str(uuid.uuid4()), "now": now})


class TestMigration009BackfillRequirements:
    """Backfill for requirement items."""

    def test_requirement_gets_v1(self):
        engine = _make_engine()
        with engine.begin() as conn:
            _build_schema(conn)
            _create_versions_table(conn)
            _seed_project(conn)
            _seed_domain(conn)
            _seed_requirement(conn, "r1", title="Login Feature", description="Users can log in",
                              source_refs=["srs.docx"], taxonomy={"module": "Auth"}, confidence=0.95)
            _seed_visibility(conn, "proj1", "requirement", "r1", "dom1", "dom1")
            _run_upgrade(conn)

            versions = conn.execute(text("SELECT * FROM artifact_versions")).fetchall()
            assert len(versions) == 1
            v = versions[0]
            # Check column values by name
            v_dict = dict(zip([c[1] for c in conn.execute(text("PRAGMA table_info(artifact_versions)")).fetchall()], v))
            assert v_dict["project_id"] == "proj1"
            assert v_dict["artifact_type"] == "requirement"
            assert v_dict["artifact_item_id"] == "r1"
            assert v_dict["version_number"] == 1
            assert v_dict["change_summary"] == "initial version (backfill)"
            assert v_dict["created_by"] == "system"
            content = json.loads(v_dict["content_snapshot"])
            assert content["title"] == "Login Feature"
            assert content["description"] == "Users can log in"
            assert content["source_references"] == ["srs.docx"]
            assert content["taxonomy"] == {"module": "Auth"}
            assert content["confidence"] == 0.95

    def test_visibility_rows_updated(self):
        engine = _make_engine()
        with engine.begin() as conn:
            _build_schema(conn)
            _create_versions_table(conn)
            _seed_project(conn)
            _seed_domain(conn)
            _seed_requirement(conn, "r1")
            _seed_visibility(conn, "proj1", "requirement", "r1", "dom1", "dom1")
            _run_upgrade(conn)

            vis = conn.execute(text("SELECT artifact_version_id FROM artifact_visibility")).fetchall()
            assert len(vis) == 1
            assert vis[0][0] is not None

    def test_multiple_visibility_rows_same_version(self):
        """Same item visible in two contexts → both point to the same v1."""
        engine = _make_engine()
        with engine.begin() as conn:
            _build_schema(conn)
            _create_versions_table(conn)
            _seed_project(conn)
            _seed_domain(conn)
            conn.execute(text(
                "INSERT INTO work_contexts (id, project_id, level, name, status) "
                "VALUES ('epic1', 'proj1', 'epic', 'Epic', 'active')"
            ), {})
            _seed_requirement(conn, "r1")
            _seed_visibility(conn, "proj1", "requirement", "r1", "dom1", "dom1")
            _seed_visibility(conn, "proj1", "requirement", "r1", "dom1", "epic1")
            _run_upgrade(conn)

            vis_rows = conn.execute(text("SELECT artifact_version_id FROM artifact_visibility")).fetchall()
            assert len(vis_rows) == 2
            version_ids = {r[0] for r in vis_rows}
            assert len(version_ids) == 1  # same version for both
            assert None not in version_ids

            versions = conn.execute(text("SELECT * FROM artifact_versions")).fetchall()
            assert len(versions) == 1


class TestMigration009BackfillGraphNodes:
    """Backfill for graph_node items."""

    def test_graph_node_gets_v1(self):
        mind_map = {
            "nodes": [
                {"id": "n1", "label": "Payment", "type": "concept", "description": "Payment processing"},
                {"id": "n2", "label": "User", "type": "actor"},
            ],
            "edges": [{"source": "n1", "target": "n2"}],
        }
        engine = _make_engine()
        with engine.begin() as conn:
            _build_schema(conn)
            _create_versions_table(conn)
            _seed_project(conn, mind_map=mind_map)
            _seed_domain(conn)
            _seed_visibility(conn, "proj1", "graph_node", "n1", "dom1", "dom1")
            _run_upgrade(conn)

            versions = conn.execute(text("SELECT content_snapshot FROM artifact_versions")).fetchall()
            assert len(versions) == 1
            content = json.loads(versions[0][0])
            assert content["label"] == "Payment"
            assert content["type"] == "concept"
            assert content["description"] == "Payment processing"


class TestMigration009BackfillGraphEdges:
    """Backfill for graph_edge items."""

    def test_graph_edge_gets_v1(self):
        mind_map = {
            "nodes": [{"id": "n1", "label": "A"}, {"id": "n2", "label": "B"}],
            "edges": [{"source": "n1", "target": "n2", "label": "depends_on"}],
        }
        engine = _make_engine()
        with engine.begin() as conn:
            _build_schema(conn)
            _create_versions_table(conn)
            _seed_project(conn, mind_map=mind_map)
            _seed_domain(conn)
            _seed_visibility(conn, "proj1", "graph_edge", "n1→n2", "dom1", "dom1")
            _run_upgrade(conn)

            versions = conn.execute(text("SELECT content_snapshot FROM artifact_versions")).fetchall()
            assert len(versions) == 1
            content = json.loads(versions[0][0])
            assert content["source"] == "n1"
            assert content["target"] == "n2"
            assert content["label"] == "depends_on"


class TestMigration009BackfillGlossary:
    """Backfill for glossary_term items."""

    def test_glossary_term_gets_v1(self):
        glossary = [
            {"term": "API Gateway", "definition": "Entry point for API requests", "related_terms": ["REST"], "source": "srs.docx"},
        ]
        engine = _make_engine()
        with engine.begin() as conn:
            _build_schema(conn)
            _create_versions_table(conn)
            _seed_project(conn, glossary=glossary)
            _seed_domain(conn)
            _seed_visibility(conn, "proj1", "glossary_term", "api_gateway", "dom1", "dom1")
            _run_upgrade(conn)

            versions = conn.execute(text("SELECT content_snapshot FROM artifact_versions")).fetchall()
            assert len(versions) == 1
            content = json.loads(versions[0][0])
            assert content["term"] == "API Gateway"
            assert content["definition"] == "Entry point for API requests"
            assert content["related_terms"] == ["REST"]


class TestMigration009EdgeCases:
    """Edge cases: missing content, empty DB, multiple items."""

    def test_item_with_no_content_skipped(self):
        """Requirement deleted from requirements table but still in visibility → skip."""
        engine = _make_engine()
        with engine.begin() as conn:
            _build_schema(conn)
            _create_versions_table(conn)
            _seed_project(conn)
            _seed_domain(conn)
            # Visibility row exists but requirement row does not
            _seed_visibility(conn, "proj1", "requirement", "r_deleted", "dom1", "dom1")
            _run_upgrade(conn)

            versions = conn.execute(text("SELECT * FROM artifact_versions")).fetchall()
            assert len(versions) == 0
            # Visibility row still exists but version_id is NULL
            vis = conn.execute(text("SELECT artifact_version_id FROM artifact_visibility")).fetchall()
            assert vis[0][0] is None

    def test_empty_database_no_errors(self):
        engine = _make_engine()
        with engine.begin() as conn:
            _build_schema(conn)
            _create_versions_table(conn)
            _run_upgrade(conn)
            assert conn.execute(text("SELECT COUNT(*) FROM artifact_versions")).scalar() == 0

    def test_multiple_items_multiple_types(self):
        """Multiple items of different types all get v1."""
        mind_map = {
            "nodes": [{"id": "n1", "label": "Node1", "type": "data"}],
            "edges": [],
        }
        glossary = [{"term": "Term A", "definition": "Def A"}]
        engine = _make_engine()
        with engine.begin() as conn:
            _build_schema(conn)
            _create_versions_table(conn)
            _seed_project(conn, mind_map=mind_map, glossary=glossary)
            _seed_domain(conn)
            _seed_requirement(conn, "r1", title="Req1")
            _seed_visibility(conn, "proj1", "requirement", "r1", "dom1", "dom1")
            _seed_visibility(conn, "proj1", "graph_node", "n1", "dom1", "dom1")
            _seed_visibility(conn, "proj1", "glossary_term", "term_a", "dom1", "dom1")
            _run_upgrade(conn)

            versions = conn.execute(text("SELECT artifact_type FROM artifact_versions ORDER BY artifact_type")).fetchall()
            types = [v[0] for v in versions]
            assert "requirement" in types
            assert "graph_node" in types
            assert "glossary_term" in types
            assert len(versions) == 3

            # All visibility rows have version_id set
            null_count = conn.execute(
                text("SELECT COUNT(*) FROM artifact_visibility WHERE artifact_version_id IS NULL")
            ).scalar()
            assert null_count == 0

    def test_audit_snapshot_gets_stub_version(self):
        """audit_snapshot type gets a minimal stub content snapshot."""
        engine = _make_engine()
        with engine.begin() as conn:
            _build_schema(conn)
            _create_versions_table(conn)
            _seed_project(conn)
            _seed_domain(conn)
            _seed_visibility(conn, "proj1", "audit_snapshot", "snap1", "dom1", "dom1")
            _run_upgrade(conn)

            versions = conn.execute(text("SELECT content_snapshot FROM artifact_versions")).fetchall()
            assert len(versions) == 1
            content = json.loads(versions[0][0])
            assert content["id"] == "snap1"
            assert content["type"] == "audit_snapshot"

    def test_source_context_id_carried_to_version(self):
        """created_in_context_id should match the source_context_id from visibility."""
        engine = _make_engine()
        with engine.begin() as conn:
            _build_schema(conn)
            _create_versions_table(conn)
            _seed_project(conn)
            _seed_domain(conn)
            _seed_requirement(conn, "r1")
            _seed_visibility(conn, "proj1", "requirement", "r1", "dom1", "dom1")
            _run_upgrade(conn)

            cols = [c[1] for c in conn.execute(text("PRAGMA table_info(artifact_versions)")).fetchall()]
            row = conn.execute(text("SELECT * FROM artifact_versions")).fetchone()
            v = dict(zip(cols, row))
            assert v["created_in_context_id"] == "dom1"

    def test_version_number_is_always_one(self):
        """All backfilled versions should be version_number=1."""
        engine = _make_engine()
        with engine.begin() as conn:
            _build_schema(conn)
            _create_versions_table(conn)
            _seed_project(conn)
            _seed_domain(conn)
            _seed_requirement(conn, "r1")
            _seed_requirement(conn, "r2", title="Second Req")
            _seed_visibility(conn, "proj1", "requirement", "r1", "dom1", "dom1")
            _seed_visibility(conn, "proj1", "requirement", "r2", "dom1", "dom1")
            _run_upgrade(conn)

            versions = conn.execute(
                text("SELECT version_number FROM artifact_versions")
            ).fetchall()
            assert all(v[0] == 1 for v in versions)
            assert len(versions) == 2


class TestMigration009ContentReaders:
    """Unit tests for the content reader helpers."""

    def test_safe_json_with_string(self):
        assert _safe_json('{"a": 1}') == {"a": 1}

    def test_safe_json_with_dict(self):
        assert _safe_json({"a": 1}) == {"a": 1}

    def test_safe_json_with_none(self):
        assert _safe_json(None) is None

    def test_safe_json_with_invalid(self):
        assert _safe_json("not json{") == "not json{"

    def test_read_content_unknown_type(self):
        engine = _make_engine()
        with engine.begin() as conn:
            _build_schema(conn)
            _seed_project(conn)
            result = _read_content(conn, "proj1", "unknown_type", "item1")
            assert result == {"id": "item1", "type": "unknown_type"}
