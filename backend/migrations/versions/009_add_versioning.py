"""Add artifact_versions table and version FK on artifact_visibility.

Revision ID: 009
Revises: 008
Create Date: 2026-03-27

New tables:
  artifact_versions — immutable version history for all artifact items (D12).
    Each edit creates a new version row. Visibility rows point to a specific
    version via artifact_version_id FK.

Altered tables:
  artifact_visibility — ADD artifact_version_id (UUID FK → artifact_versions.id)

Backfill:
  For each unique (project_id, artifact_type, artifact_item_id) in
  artifact_visibility, create a v1 ArtifactVersion with content_snapshot read
  from the authoritative source (requirement row / mind_map JSON / glossary JSON).
  Then set artifact_version_id on all visibility rows for that item.
"""

import json
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_requirement_content(bind, item_id: str) -> dict | None:
    """Read requirement row as content snapshot."""
    row = bind.execute(
        sa.text(
            "SELECT id, title, description, level, external_id, source_type, "
            "source_references, taxonomy, confidence, completeness_score "
            "FROM requirements WHERE id = :rid"
        ),
        {"rid": item_id},
    ).fetchone()
    if not row:
        return None
    return {
        "id": row[0],
        "title": row[1],
        "description": row[2],
        "level": row[3],
        "external_id": row[4],
        "source_type": row[5],
        "source_references": _safe_json(row[6]),
        "taxonomy": _safe_json(row[7]),
        "confidence": row[8],
        "completeness_score": row[9],
    }


def _safe_json(val):
    """Parse JSON string if needed, return None on failure."""
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return val
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return val


def _read_graph_node_content(bind, project_id: str, node_id: str) -> dict | None:
    """Read a single graph node from the project's mind_map JSON blob."""
    row = bind.execute(
        sa.text("SELECT mind_map FROM projects WHERE id = :pid"),
        {"pid": project_id},
    ).fetchone()
    if not row or not row[0]:
        return None
    mind_map = _safe_json(row[0])
    if not isinstance(mind_map, dict):
        return None
    nodes = mind_map.get("nodes", [])
    for n in nodes:
        if isinstance(n, dict) and n.get("id") == node_id:
            return {
                "id": n.get("id"),
                "label": n.get("label"),
                "type": n.get("type"),
                "description": n.get("description"),
            }
    return None


def _read_graph_edge_content(bind, project_id: str, edge_id: str) -> dict | None:
    """Read a single graph edge from the project's mind_map JSON blob."""
    row = bind.execute(
        sa.text("SELECT mind_map FROM projects WHERE id = :pid"),
        {"pid": project_id},
    ).fetchone()
    if not row or not row[0]:
        return None
    mind_map = _safe_json(row[0])
    if not isinstance(mind_map, dict):
        return None
    edges = mind_map.get("edges", [])
    # edge_id format is "source→target"
    parts = edge_id.split("→") if "→" in edge_id else None
    if parts and len(parts) == 2:
        src, tgt = parts[0], parts[1]
        for e in edges:
            if isinstance(e, dict) and e.get("source") == src and e.get("target") == tgt:
                return {
                    "source": e.get("source"),
                    "target": e.get("target"),
                    "label": e.get("label"),
                }
    return None


def _read_glossary_term_content(bind, project_id: str, term_id: str) -> dict | None:
    """Read a single glossary term from the project's glossary JSON blob."""
    row = bind.execute(
        sa.text("SELECT glossary FROM projects WHERE id = :pid"),
        {"pid": project_id},
    ).fetchone()
    if not row or not row[0]:
        return None
    glossary = _safe_json(row[0])
    if not isinstance(glossary, list):
        return None
    # term_id is the normalized term name
    for t in glossary:
        if isinstance(t, dict):
            term_name = t.get("term", "")
            normalized = term_name.strip().lower().replace(" ", "_")
            if normalized == term_id or term_name == term_id:
                return {
                    "term": t.get("term"),
                    "definition": t.get("definition"),
                    "related_terms": t.get("related_terms"),
                    "source": t.get("source"),
                }
    return None


def _read_content(bind, project_id: str, artifact_type: str, item_id: str) -> dict | None:
    """Dispatch to type-specific content reader."""
    if artifact_type == "requirement":
        return _read_requirement_content(bind, item_id)
    if artifact_type == "graph_node":
        return _read_graph_node_content(bind, project_id, item_id)
    if artifact_type == "graph_edge":
        return _read_graph_edge_content(bind, project_id, item_id)
    if artifact_type == "glossary_term":
        return _read_glossary_term_content(bind, project_id, item_id)
    # audit_snapshot or unknown — return minimal stub
    return {"id": item_id, "type": artifact_type}


def upgrade() -> None:
    # ── 1. CREATE artifact_versions table ────────────────────────────────────
    op.create_table(
        "artifact_versions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("artifact_type", sa.String(), nullable=False),
        sa.Column("artifact_item_id", sa.String(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("content_snapshot", sa.Text(), nullable=True),
        sa.Column("created_in_context_id", sa.String(), nullable=True),
        sa.Column("change_summary", sa.String(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=False, server_default="system"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["created_in_context_id"], ["work_contexts.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id", "artifact_type", "artifact_item_id", "version_number",
            name="uq_artifact_version_item_ver",
        ),
    )
    op.create_index(
        "ix_artifact_ver_item_version_desc",
        "artifact_versions",
        ["project_id", "artifact_type", "artifact_item_id", "version_number"],
    )

    # ── 2. ALTER artifact_visibility: add artifact_version_id FK ─────────────
    with op.batch_alter_table("artifact_visibility", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("artifact_version_id", sa.String(), nullable=True)
        )
        batch_op.create_foreign_key(
            "fk_artifact_vis_version",
            "artifact_versions",
            ["artifact_version_id"],
            ["id"],
            ondelete="SET NULL",
        )

    # ── 3. BACKFILL: create v1 for each unique item in artifact_visibility ───
    bind = op.get_bind()
    now = _now_iso()

    # Gather distinct items
    items = bind.execute(
        sa.text(
            "SELECT DISTINCT project_id, artifact_type, artifact_item_id, "
            "source_context_id "
            "FROM artifact_visibility"
        )
    ).fetchall()

    backfilled = 0
    for row in items:
        project_id, artifact_type, item_id, source_ctx_id = row[0], row[1], row[2], row[3]

        content = _read_content(bind, project_id, artifact_type, item_id)
        if content is None:
            continue

        version_id = str(uuid.uuid4())
        bind.execute(
            sa.text(
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

        # Update all visibility rows for this item
        bind.execute(
            sa.text(
                "UPDATE artifact_visibility "
                "SET artifact_version_id = :vid "
                "WHERE project_id = :pid AND artifact_type = :atype "
                "  AND artifact_item_id = :item_id"
            ),
            {
                "vid": version_id,
                "pid": project_id,
                "atype": artifact_type,
                "item_id": item_id,
            },
        )
        backfilled += 1


def downgrade() -> None:
    # ── Remove FK column from artifact_visibility ────────────────────────────
    with op.batch_alter_table("artifact_visibility", schema=None) as batch_op:
        batch_op.drop_constraint("fk_artifact_vis_version", type_="foreignkey")
        batch_op.drop_column("artifact_version_id")

    # ── Drop artifact_versions ───────────────────────────────────────────────
    op.drop_index("ix_artifact_ver_item_version_desc", table_name="artifact_versions")
    op.drop_table("artifact_versions")
