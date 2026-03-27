"""
test_migration_006.py — Phase 8: backfill migration tests (D10 REVISIT).

These tests run the migration logic (upgrade / downgrade functions) against
an in-memory SQLite database that has been seeded with realistic pre-migration
data. They do NOT use the app's test DB (conftest) — they build their own
clean SQLAlchemy connection so the migration functions are called in isolation.

All manifest rows now go into artifact_visibility (not artifact_lifecycle).
"""

import importlib.util
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

# ── Load the migration module (name starts with a digit — can't use from-import) ──
_MIGRATION_PATH = Path(__file__).parent.parent / "migrations" / "versions" / "006_backfill_work_context.py"
_spec = importlib.util.spec_from_file_location("migration_006", _MIGRATION_PATH)
_migration = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(_migration)  # type: ignore[union-attr]

_insert_visibility_item = _migration._insert_visibility_item
_insert_audit_log = _migration._insert_audit_log
_now_iso = _migration._now_iso

# ─── Build a synchronous in-memory SQLite engine for migration tests ──────────
# Alembic migrations run synchronously (via greenlet) so we use a sync engine.

def _make_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    return engine


def _build_schema(conn):
    """Create the schema that exists AFTER migration 005 (before 006)."""
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
        CREATE TABLE IF NOT EXISTS audit_snapshots (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            created_at TEXT,
            files_used TEXT,
            summary TEXT,
            requirements_uncovered TEXT,
            recommendations TEXT,
            diff TEXT,
            work_context_id TEXT REFERENCES work_contexts(id) ON DELETE SET NULL,
            lifecycle_status TEXT NOT NULL DEFAULT 'promoted'
        )
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS requirements (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            parent_id TEXT REFERENCES requirements(id) ON DELETE SET NULL,
            level TEXT NOT NULL,
            external_id TEXT,
            title TEXT NOT NULL,
            description TEXT,
            source_type TEXT NOT NULL DEFAULT 'reconstructed',
            source_references TEXT,
            taxonomy TEXT,
            completeness_score REAL,
            confidence REAL,
            human_reviewed INTEGER NOT NULL DEFAULT 0,
            needs_review INTEGER NOT NULL DEFAULT 0,
            review_reason TEXT,
            created_at TEXT,
            updated_at TEXT,
            work_context_id TEXT REFERENCES work_contexts(id) ON DELETE SET NULL,
            lifecycle_status TEXT NOT NULL DEFAULT 'promoted'
        )
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS artifact_visibility (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            artifact_type TEXT NOT NULL,
            artifact_item_id TEXT NOT NULL,
            source_context_id TEXT REFERENCES work_contexts(id) ON DELETE SET NULL,
            visible_in_context_id TEXT REFERENCES work_contexts(id) ON DELETE SET NULL,
            lifecycle_status TEXT NOT NULL DEFAULT 'draft',
            sibling_of TEXT,
            source_origin TEXT,
            source_origin_type TEXT,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(project_id, artifact_type, artifact_item_id, visible_in_context_id)
        )
    """))
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS artifact_audit_log (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            artifact_type TEXT NOT NULL,
            artifact_item_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            work_context_id TEXT REFERENCES work_contexts(id) ON DELETE SET NULL,
            old_value TEXT,
            new_value TEXT,
            actor TEXT NOT NULL,
            actor_id TEXT,
            note TEXT,
            created_at TEXT
        )
    """))
    conn.commit()


def _insert_project(conn, mind_map=None, glossary=None, context_files=None):
    pid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        text(
            "INSERT INTO projects (id, name, description, created_at, mind_map, glossary, context_built_at, context_files) "
            "VALUES (:id, :name, NULL, :now, :mm, :gl, :cba, :cf)"
        ),
        {
            "id": pid,
            "name": f"Project {pid[:8]}",
            "now": now,
            "mm": json.dumps(mind_map) if mind_map else None,
            "gl": json.dumps(glossary) if glossary else None,
            "cba": now if (mind_map or glossary) else None,
            "cf": json.dumps(context_files) if context_files else None,
        },
    )
    conn.commit()
    return pid


def _insert_requirement(conn, project_id, source_references=None):
    rid = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO requirements (id, project_id, level, title, created_at, lifecycle_status, source_references) "
            "VALUES (:id, :pid, 'functional_req', 'Test Req', :now, 'promoted', :sr)"
        ),
        {
            "id": rid,
            "pid": project_id,
            "now": datetime.now(timezone.utc).isoformat(),
            "sr": json.dumps(source_references) if source_references else None,
        },
    )
    conn.commit()
    return rid


def _insert_snapshot(conn, project_id):
    sid = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO audit_snapshots (id, project_id, created_at, files_used, summary, lifecycle_status) "
            "VALUES (:id, :pid, :now, '[]', '{}', 'promoted')"
        ),
        {"id": sid, "pid": project_id, "now": datetime.now(timezone.utc).isoformat()},
    )
    conn.commit()
    return sid


def _run_migration_logic(conn):
    """Execute the same logic as the 006 upgrade() using the provided connection."""

    projects = conn.execute(
        text("SELECT id, mind_map, glossary, context_built_at, created_at, context_files FROM projects")
    ).fetchall()

    promoted_at_default = _now_iso()

    for project in projects:
        project_id = project[0]
        mind_map_raw = project[1]
        glossary_raw = project[2]
        context_built_at = project[3]
        created_at = project[4]
        context_files_raw = project[5]

        # Derive source_origin for graph/glossary items from context_files
        context_source_origin = None
        context_source_origin_type = None
        if context_files_raw:
            try:
                cf = json.loads(context_files_raw) if isinstance(context_files_raw, str) else context_files_raw
                if cf and isinstance(cf, list):
                    first = cf[0]
                    if isinstance(first, dict):
                        context_source_origin = first.get("name")
                    else:
                        context_source_origin = str(first)
                    if context_source_origin:
                        context_source_origin_type = "file"
            except (json.JSONDecodeError, TypeError):
                pass

        existing_domain = conn.execute(
            text("SELECT id FROM work_contexts WHERE project_id = :pid AND level = 'domain' LIMIT 1"),
            {"pid": project_id},
        ).fetchone()

        if existing_domain:
            domain_id = existing_domain[0]
        else:
            domain_id = str(uuid.uuid4())
            promoted_at = context_built_at or created_at or promoted_at_default
            conn.execute(
                text(
                    "INSERT INTO work_contexts "
                    "(id, project_id, parent_id, level, name, description, status, created_at, updated_at, promoted_at) "
                    "VALUES (:id, :pid, NULL, 'domain', 'Default Domain', NULL, 'promoted', :now, NULL, :pat)"
                ),
                {"id": domain_id, "pid": project_id, "now": _now_iso(), "pat": promoted_at},
            )

        conn.execute(
            text(
                "UPDATE requirements SET work_context_id = :did, lifecycle_status = 'promoted' "
                "WHERE project_id = :pid AND work_context_id IS NULL"
            ),
            {"did": domain_id, "pid": project_id},
        )
        conn.execute(
            text(
                "UPDATE audit_snapshots SET work_context_id = :did, lifecycle_status = 'promoted' "
                "WHERE project_id = :pid AND work_context_id IS NULL"
            ),
            {"did": domain_id, "pid": project_id},
        )

        now_str = _now_iso()

        if mind_map_raw:
            try:
                mind_map = json.loads(mind_map_raw) if isinstance(mind_map_raw, str) else mind_map_raw
                nodes = mind_map.get("nodes", [])
                edges = mind_map.get("edges", [])
            except Exception:
                nodes, edges = [], []

            for node in nodes:
                item_id = node.get("id")
                if item_id:
                    _insert_visibility_item(
                        conn, project_id, "graph_node", item_id, domain_id,
                        context_source_origin, context_source_origin_type, now_str,
                    )
                    _insert_audit_log(conn, project_id, "graph_node", item_id, domain_id, now_str)

            for edge in edges:
                src, tgt = edge.get("source"), edge.get("target")
                if src and tgt:
                    item_id = f"{src}→{tgt}"
                    _insert_visibility_item(
                        conn, project_id, "graph_edge", item_id, domain_id,
                        context_source_origin, context_source_origin_type, now_str,
                    )
                    _insert_audit_log(conn, project_id, "graph_edge", item_id, domain_id, now_str)

        if glossary_raw:
            try:
                glossary = json.loads(glossary_raw) if isinstance(glossary_raw, str) else glossary_raw
            except Exception:
                glossary = []

            for term_obj in glossary:
                term = term_obj.get("term")
                if term:
                    item_id = term.lower().replace(" ", "_")
                    _insert_visibility_item(
                        conn, project_id, "glossary_term", item_id, domain_id,
                        context_source_origin, context_source_origin_type, now_str,
                    )
                    _insert_audit_log(conn, project_id, "glossary_term", item_id, domain_id, now_str)

        # Backfill requirement visibility rows
        req_rows = conn.execute(
            text("SELECT id, source_references FROM requirements WHERE project_id = :pid"),
            {"pid": project_id},
        ).fetchall()

        for req_row in req_rows:
            req_id = req_row[0]
            source_refs_raw = req_row[1]
            req_origin, req_origin_type = _migration._derive_source_origin_from_refs(source_refs_raw)
            _insert_visibility_item(
                conn, project_id, "requirement", req_id, domain_id,
                req_origin, req_origin_type, now_str,
            )
            _insert_audit_log(conn, project_id, "requirement", req_id, domain_id, now_str)

        conn.commit()


# ─── Tests ────────────────────────────────────────────────────────────────────


class TestMigration006:

    def _fresh(self):
        """Return a fresh engine+connection with 005-era schema."""
        engine = _make_engine()
        conn = engine.connect()
        _build_schema(conn)
        return engine, conn

    def test_default_domain_created_for_each_project(self):
        """Each project gets exactly one Default Domain after migration."""
        _, conn = self._fresh()
        pid1 = _insert_project(conn)
        pid2 = _insert_project(conn)

        _run_migration_logic(conn)

        for pid in (pid1, pid2):
            domains = conn.execute(
                text("SELECT id, status FROM work_contexts WHERE project_id = :pid AND level = 'domain'"),
                {"pid": pid},
            ).fetchall()
            assert len(domains) == 1, f"Expected 1 domain for {pid}, got {len(domains)}"
            assert domains[0][1] == "promoted"

    def test_requirements_backfilled(self):
        """Requirements get work_context_id and lifecycle_status='promoted'."""
        _, conn = self._fresh()
        pid = _insert_project(conn)
        rid = _insert_requirement(conn, pid)

        _run_migration_logic(conn)

        row = conn.execute(
            text("SELECT work_context_id, lifecycle_status FROM requirements WHERE id = :id"),
            {"id": rid},
        ).fetchone()
        assert row is not None
        assert row[0] is not None, "work_context_id should be set"
        assert row[1] == "promoted"

    def test_snapshots_backfilled(self):
        """AuditSnapshot rows get work_context_id and lifecycle_status='promoted'."""
        _, conn = self._fresh()
        pid = _insert_project(conn)
        sid = _insert_snapshot(conn, pid)

        _run_migration_logic(conn)

        row = conn.execute(
            text("SELECT work_context_id, lifecycle_status FROM audit_snapshots WHERE id = :id"),
            {"id": sid},
        ).fetchone()
        assert row is not None
        assert row[0] is not None, "work_context_id should be set"
        assert row[1] == "promoted"

    def test_visibility_rows_created_for_mind_map(self):
        """ArtifactVisibility rows created for graph nodes + edges."""
        _, conn = self._fresh()
        mind_map = {
            "nodes": [{"id": "n1", "label": "Payment", "type": "process"},
                      {"id": "n2", "label": "Auth", "type": "actor"}],
            "edges": [{"source": "n1", "target": "n2", "label": "uses"}],
        }
        pid = _insert_project(conn, mind_map=mind_map)

        _run_migration_logic(conn)

        nodes_count = conn.execute(
            text("SELECT COUNT(*) FROM artifact_visibility WHERE project_id = :pid AND artifact_type = 'graph_node'"),
            {"pid": pid},
        ).scalar()
        assert nodes_count == 2

        edges_count = conn.execute(
            text("SELECT COUNT(*) FROM artifact_visibility WHERE project_id = :pid AND artifact_type = 'graph_edge'"),
            {"pid": pid},
        ).scalar()
        assert edges_count == 1

    def test_visibility_rows_created_for_glossary(self):
        """ArtifactVisibility rows created for glossary terms."""
        _, conn = self._fresh()
        glossary = [
            {"term": "Payment Gateway", "definition": "System for processing payments."},
            {"term": "SLA", "definition": "Service level agreement."},
        ]
        pid = _insert_project(conn, glossary=glossary)

        _run_migration_logic(conn)

        count = conn.execute(
            text("SELECT COUNT(*) FROM artifact_visibility WHERE project_id = :pid AND artifact_type = 'glossary_term'"),
            {"pid": pid},
        ).scalar()
        assert count == 2

    def test_visibility_lifecycle_status_is_promoted(self):
        """All visibility rows have lifecycle_status='promoted'."""
        _, conn = self._fresh()
        mind_map = {"nodes": [{"id": "e1", "label": "Auth"}], "edges": []}
        pid = _insert_project(conn, mind_map=mind_map)

        _run_migration_logic(conn)

        rows = conn.execute(
            text("SELECT lifecycle_status FROM artifact_visibility WHERE project_id = :pid"),
            {"pid": pid},
        ).fetchall()
        assert all(r[0] == "promoted" for r in rows)

    def test_audit_log_emitted_per_visibility_item(self):
        """ArtifactAuditLog rows emitted for each backfilled artifact."""
        _, conn = self._fresh()
        mind_map = {"nodes": [{"id": "n1", "label": "A"}, {"id": "n2", "label": "B"}], "edges": []}
        glossary = [{"term": "Foo", "definition": "bar"}]
        pid = _insert_project(conn, mind_map=mind_map, glossary=glossary)

        _run_migration_logic(conn)

        count = conn.execute(
            text(
                "SELECT COUNT(*) FROM artifact_audit_log "
                "WHERE project_id = :pid AND event_type = 'created' AND actor = 'system'"
            ),
            {"pid": pid},
        ).scalar()
        assert count == 3  # 2 nodes + 1 glossary term

    def test_idempotent_no_duplicates(self):
        """Running the migration twice produces no duplicate rows."""
        _, conn = self._fresh()
        mind_map = {"nodes": [{"id": "n1", "label": "A"}], "edges": []}
        pid = _insert_project(conn, mind_map=mind_map)

        _run_migration_logic(conn)
        _run_migration_logic(conn)

        domain_count = conn.execute(
            text("SELECT COUNT(*) FROM work_contexts WHERE project_id = :pid AND level = 'domain'"),
            {"pid": pid},
        ).scalar()
        assert domain_count == 1, "Should have exactly 1 domain after idempotent run"

        visibility_count = conn.execute(
            text("SELECT COUNT(*) FROM artifact_visibility WHERE project_id = :pid"),
            {"pid": pid},
        ).scalar()
        assert visibility_count == 1, "Should have exactly 1 visibility row after idempotent run"

        audit_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM artifact_audit_log "
                "WHERE project_id = :pid AND event_type = 'created' AND actor = 'system'"
            ),
            {"pid": pid},
        ).scalar()
        assert audit_count == 1, "Should have exactly 1 audit log entry after idempotent run"

    def test_null_mind_map_no_error(self):
        """Project with NULL mind_map and NULL glossary → no crash, domain still created."""
        _, conn = self._fresh()
        pid = _insert_project(conn, mind_map=None, glossary=None)

        # Should not raise
        _run_migration_logic(conn)

        domain_count = conn.execute(
            text("SELECT COUNT(*) FROM work_contexts WHERE project_id = :pid AND level = 'domain'"),
            {"pid": pid},
        ).scalar()
        assert domain_count == 1

        visibility_count = conn.execute(
            text("SELECT COUNT(*) FROM artifact_visibility WHERE project_id = :pid"),
            {"pid": pid},
        ).scalar()
        assert visibility_count == 0, "No visibility rows for project with no artefacts"

    def test_artifacts_reachable_via_domain_query(self):
        """After migration, all visibility items can be joined to their domain."""
        _, conn = self._fresh()
        mind_map = {"nodes": [{"id": "n1", "label": "A"}, {"id": "n2", "label": "B"}], "edges": []}
        pid = _insert_project(conn, mind_map=mind_map)

        _run_migration_logic(conn)

        # Join artifact_visibility to work_contexts via visible_in_context_id
        rows = conn.execute(
            text("""
                SELECT av.artifact_item_id, wc.level, wc.name
                FROM artifact_visibility av
                JOIN work_contexts wc ON av.visible_in_context_id = wc.id
                WHERE av.project_id = :pid
            """),
            {"pid": pid},
        ).fetchall()

        assert len(rows) == 2
        for row in rows:
            assert row[1] == "domain"
            assert row[2] == "Default Domain"

    def test_no_pre_existing_domain_creates_one(self):
        """Project with no existing domain gets a new Default Domain."""
        _, conn = self._fresh()
        pid = _insert_project(conn)

        existing = conn.execute(
            text("SELECT COUNT(*) FROM work_contexts WHERE project_id = :pid"),
            {"pid": pid},
        ).scalar()
        assert existing == 0, "No contexts before migration"

        _run_migration_logic(conn)

        domain = conn.execute(
            text("SELECT name, status FROM work_contexts WHERE project_id = :pid AND level = 'domain'"),
            {"pid": pid},
        ).fetchone()
        assert domain is not None
        assert domain[0] == "Default Domain"
        assert domain[1] == "promoted"

    def test_pre_existing_domain_is_reused(self):
        """Project with an existing domain does not get a second one."""
        _, conn = self._fresh()
        pid = _insert_project(conn)

        # Pre-create a domain (simulates a new project created after Phase 2)
        existing_domain_id = str(uuid.uuid4())
        conn.execute(
            text(
                "INSERT INTO work_contexts (id, project_id, level, name, status, created_at) "
                "VALUES (:id, :pid, 'domain', 'My Domain', 'promoted', :now)"
            ),
            {"id": existing_domain_id, "pid": pid, "now": datetime.now(timezone.utc).isoformat()},
        )
        conn.commit()

        _run_migration_logic(conn)

        domain_count = conn.execute(
            text("SELECT COUNT(*) FROM work_contexts WHERE project_id = :pid AND level = 'domain'"),
            {"pid": pid},
        ).scalar()
        assert domain_count == 1, "Should still have exactly 1 domain"

    # ── New D10 tests ─────────────────────────────────────────────────────────

    def test_visibility_has_source_and_visible_context_ids(self):
        """Each visibility row has source_context_id = visible_in_context_id = domain."""
        _, conn = self._fresh()
        mind_map = {"nodes": [{"id": "n1", "label": "A"}], "edges": []}
        pid = _insert_project(conn, mind_map=mind_map)

        _run_migration_logic(conn)

        row = conn.execute(
            text(
                "SELECT source_context_id, visible_in_context_id FROM artifact_visibility "
                "WHERE project_id = :pid AND artifact_type = 'graph_node'"
            ),
            {"pid": pid},
        ).fetchone()
        assert row is not None
        assert row[0] is not None, "source_context_id should be set"
        assert row[1] is not None, "visible_in_context_id should be set"
        assert row[0] == row[1], "source and visible should both point to domain"

        # Verify it's actually the domain
        domain_id = conn.execute(
            text("SELECT id FROM work_contexts WHERE project_id = :pid AND level = 'domain'"),
            {"pid": pid},
        ).scalar()
        assert row[0] == domain_id

    def test_source_origin_populated_from_context_files(self):
        """Graph/glossary visibility rows get source_origin from context_files."""
        _, conn = self._fresh()
        mind_map = {"nodes": [{"id": "n1", "label": "A"}], "edges": []}
        pid = _insert_project(conn, mind_map=mind_map, context_files=["srs_v3.docx", "design.pdf"])

        _run_migration_logic(conn)

        row = conn.execute(
            text(
                "SELECT source_origin, source_origin_type FROM artifact_visibility "
                "WHERE project_id = :pid AND artifact_type = 'graph_node'"
            ),
            {"pid": pid},
        ).fetchone()
        assert row is not None
        assert row[0] == "srs_v3.docx"
        assert row[1] == "file"

    def test_source_origin_populated_from_context_files_dict_format(self):
        """context_files in [{name: ...}] format also works."""
        _, conn = self._fresh()
        mind_map = {"nodes": [{"id": "n1", "label": "A"}], "edges": []}
        pid = _insert_project(conn, mind_map=mind_map, context_files=[{"name": "spec.docx", "indexed_at": "2026-01-01"}])

        _run_migration_logic(conn)

        row = conn.execute(
            text(
                "SELECT source_origin FROM artifact_visibility "
                "WHERE project_id = :pid AND artifact_type = 'graph_node'"
            ),
            {"pid": pid},
        ).fetchone()
        assert row is not None
        assert row[0] == "spec.docx"

    def test_requirement_visibility_rows_created(self):
        """Requirements get their own visibility rows in artifact_visibility."""
        _, conn = self._fresh()
        pid = _insert_project(conn)
        rid = _insert_requirement(conn, pid, source_references=["srs_v3.docx"])

        _run_migration_logic(conn)

        row = conn.execute(
            text(
                "SELECT artifact_item_id, artifact_type, lifecycle_status, "
                "       source_origin, source_origin_type, source_context_id, visible_in_context_id "
                "FROM artifact_visibility "
                "WHERE project_id = :pid AND artifact_type = 'requirement'"
            ),
            {"pid": pid},
        ).fetchone()
        assert row is not None
        assert row[0] == rid, "artifact_item_id should be requirement id"
        assert row[1] == "requirement"
        assert row[2] == "promoted"
        assert row[3] == "srs_v3.docx", "source_origin from source_references"
        assert row[4] == "file"
        assert row[5] == row[6], "source == visible (home row)"

    def test_requirement_source_origin_url(self):
        """Requirement with URL source_references gets source_origin_type='url'."""
        _, conn = self._fresh()
        pid = _insert_project(conn)
        rid = _insert_requirement(conn, pid, source_references=["https://jira.example.com/PROJ-123"])

        _run_migration_logic(conn)

        row = conn.execute(
            text(
                "SELECT source_origin, source_origin_type FROM artifact_visibility "
                "WHERE project_id = :pid AND artifact_type = 'requirement'"
            ),
            {"pid": pid},
        ).fetchone()
        assert row is not None
        assert row[0] == "https://jira.example.com/PROJ-123"
        assert row[1] == "url"

    def test_requirement_no_source_references(self):
        """Requirement with no source_references gets NULL source_origin."""
        _, conn = self._fresh()
        pid = _insert_project(conn)
        _insert_requirement(conn, pid, source_references=None)

        _run_migration_logic(conn)

        row = conn.execute(
            text(
                "SELECT source_origin, source_origin_type FROM artifact_visibility "
                "WHERE project_id = :pid AND artifact_type = 'requirement'"
            ),
            {"pid": pid},
        ).fetchone()
        assert row is not None
        assert row[0] is None
        assert row[1] is None

    def test_unified_query_returns_correct_results(self):
        """The Phase 7 unified query pattern works on backfilled data."""
        _, conn = self._fresh()
        mind_map = {
            "nodes": [{"id": "n1", "label": "A"}, {"id": "n2", "label": "B"}],
            "edges": [{"source": "n1", "target": "n2", "label": "uses"}],
        }
        glossary = [{"term": "SLA", "definition": "Service level agreement."}]
        pid = _insert_project(conn, mind_map=mind_map, glossary=glossary)
        rid = _insert_requirement(conn, pid, source_references=["doc.docx"])

        _run_migration_logic(conn)

        domain_id = conn.execute(
            text("SELECT id FROM work_contexts WHERE project_id = :pid AND level = 'domain'"),
            {"pid": pid},
        ).scalar()

        # Simulate the Phase 7 query: "show me all graph_nodes visible in domain"
        nodes = conn.execute(
            text("""
                SELECT av.artifact_item_id
                FROM artifact_visibility av
                WHERE av.project_id = :pid
                  AND av.visible_in_context_id = :ctx
                  AND av.artifact_type = 'graph_node'
                  AND av.lifecycle_status NOT IN ('archived', 'conflict_pending', 'superseded')
            """),
            {"pid": pid, "ctx": domain_id},
        ).fetchall()
        assert len(nodes) == 2
        assert {r[0] for r in nodes} == {"n1", "n2"}

        # Requirements via visibility JOIN
        reqs = conn.execute(
            text("""
                SELECT r.id
                FROM requirements r
                JOIN artifact_visibility av
                  ON av.artifact_item_id = r.id
                  AND av.artifact_type = 'requirement'
                  AND av.project_id = r.project_id
                WHERE av.visible_in_context_id = :ctx
                  AND av.lifecycle_status = 'promoted'
            """),
            {"ctx": domain_id},
        ).fetchall()
        assert len(reqs) == 1
        assert reqs[0][0] == rid

    def test_no_source_origin_when_no_context_files(self):
        """Graph nodes get NULL source_origin when project has no context_files."""
        _, conn = self._fresh()
        mind_map = {"nodes": [{"id": "n1", "label": "A"}], "edges": []}
        pid = _insert_project(conn, mind_map=mind_map, context_files=None)

        _run_migration_logic(conn)

        row = conn.execute(
            text(
                "SELECT source_origin, source_origin_type FROM artifact_visibility "
                "WHERE project_id = :pid AND artifact_type = 'graph_node'"
            ),
            {"pid": pid},
        ).fetchone()
        assert row is not None
        assert row[0] is None
        assert row[1] is None
