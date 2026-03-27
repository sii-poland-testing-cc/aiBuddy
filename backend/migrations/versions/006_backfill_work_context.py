"""Backfill existing project data into the visibility model (Phase 8 — D10 REVISIT).

Revision ID: 006
Revises: 005
Create Date: 2026-03-26 (original) → 2026-03-27 (D10 revisit)

For every existing project that has context artefacts (mind_map / glossary)
or requirements, this migration:

  1. Creates a "Default Domain" WorkContext (level="domain", status="promoted",
     promoted_at = project.context_built_at OR project.created_at).
     IDEMPOTENT — skipped if a domain already exists for the project.

  2. Updates all Requirement rows for the project:
       work_context_id = domain.id
       lifecycle_status = "promoted"
     Only rows where work_context_id IS NULL are updated (idempotent).

  3. Updates all AuditSnapshot rows for the project:
       work_context_id = domain.id
       lifecycle_status = "promoted"
     Only rows where work_context_id IS NULL are updated (idempotent).

  4. Inserts ArtifactVisibility rows for every graph node, graph edge,
     and glossary term found in Project.mind_map / Project.glossary.
     source_context_id = visible_in_context_id = domain.id (home row).
     Uses SELECT-then-INSERT for idempotency.

  5. Inserts ArtifactVisibility rows for every Requirement in the project.
     source_context_id = visible_in_context_id = domain.id.
     source_origin derived from source_references[0] (if available).

  6. Emits one ArtifactAuditLog row per visibility item:
       event_type="created", actor="system", note="backfill migration"
     Skipped if an audit-log entry for the same (project_id, artifact_type,
     artifact_item_id) already exists (idempotent).

  7. Populates source_origin on visibility rows:
     - Graph nodes/edges/glossary: first file from context_files
     - Requirements: first entry from source_references JSON

Projects with NULL mind_map / glossary are handled gracefully (skipped).
"""

import json
import uuid
import logging
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None

logger = logging.getLogger("alembic.006_backfill")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _derive_source_origin_from_refs(source_references_raw) -> tuple:
    """Derive (source_origin, source_origin_type) from source_references JSON."""
    if not source_references_raw:
        return None, None
    try:
        refs = json.loads(source_references_raw) if isinstance(source_references_raw, str) else source_references_raw
    except (json.JSONDecodeError, TypeError):
        return None, None
    if not refs or not isinstance(refs, list):
        return None, None
    first_ref = str(refs[0]).strip()
    if not first_ref:
        return None, None
    if first_ref.startswith("http://") or first_ref.startswith("https://"):
        return first_ref, "url"
    return first_ref, "file"


def upgrade() -> None:
    bind = op.get_bind()

    # ── Fetch all projects ────────────────────────────────────────────────────
    projects = bind.execute(
        sa.text(
            "SELECT id, mind_map, glossary, context_built_at, created_at, context_files "
            "FROM projects"
        )
    ).fetchall()

    promoted_at_default = datetime.now(timezone.utc).isoformat()
    total_domains = 0
    total_requirements = 0
    total_snapshots = 0
    total_visibility = 0
    total_audit = 0

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
                    # context_files can be [{"name": "x.docx", ...}] or ["x.docx"]
                    first = cf[0]
                    if isinstance(first, dict):
                        context_source_origin = first.get("name")
                    else:
                        context_source_origin = str(first)
                    if context_source_origin:
                        context_source_origin_type = "file"
            except (json.JSONDecodeError, TypeError):
                pass

        # ── 1. Get or create Default Domain ──────────────────────────────────
        existing_domain = bind.execute(
            sa.text(
                "SELECT id FROM work_contexts "
                "WHERE project_id = :pid AND level = 'domain' "
                "LIMIT 1"
            ),
            {"pid": project_id},
        ).fetchone()

        if existing_domain:
            domain_id = existing_domain[0]
        else:
            domain_id = str(uuid.uuid4())
            promoted_at = context_built_at or created_at or promoted_at_default
            bind.execute(
                sa.text(
                    "INSERT INTO work_contexts "
                    "(id, project_id, parent_id, level, name, description, "
                    " status, created_at, updated_at, promoted_at) "
                    "VALUES (:id, :pid, NULL, 'domain', 'Default Domain', NULL, "
                    "        'promoted', :now, NULL, :pat)"
                ),
                {
                    "id": domain_id,
                    "pid": project_id,
                    "now": _now_iso(),
                    "pat": promoted_at,
                },
            )
            total_domains += 1

        # ── 2. Backfill Requirements (work_context_id) ──────────────────────
        result = bind.execute(
            sa.text(
                "UPDATE requirements "
                "SET work_context_id = :did, lifecycle_status = 'promoted' "
                "WHERE project_id = :pid AND work_context_id IS NULL"
            ),
            {"did": domain_id, "pid": project_id},
        )
        total_requirements += result.rowcount

        # ── 3. Backfill AuditSnapshots ────────────────────────────────────────
        result = bind.execute(
            sa.text(
                "UPDATE audit_snapshots "
                "SET work_context_id = :did, lifecycle_status = 'promoted' "
                "WHERE project_id = :pid AND work_context_id IS NULL"
            ),
            {"did": domain_id, "pid": project_id},
        )
        total_snapshots += result.rowcount

        # ── 4. Backfill ArtifactVisibility for graph nodes/edges/glossary ────
        now_str = _now_iso()

        # 4a. Graph nodes
        if mind_map_raw:
            try:
                mind_map = json.loads(mind_map_raw) if isinstance(mind_map_raw, str) else mind_map_raw
                nodes = mind_map.get("nodes", [])
                edges = mind_map.get("edges", [])
            except (json.JSONDecodeError, AttributeError):
                nodes, edges = [], []

            for node in nodes:
                item_id = node.get("id")
                if not item_id:
                    continue
                n = _insert_visibility_item(
                    bind, project_id, "graph_node", item_id, domain_id,
                    context_source_origin, context_source_origin_type, now_str,
                )
                total_visibility += n
                n = _insert_audit_log(
                    bind, project_id, "graph_node", item_id, domain_id, now_str
                )
                total_audit += n

            for edge in edges:
                src = edge.get("source")
                tgt = edge.get("target")
                if not src or not tgt:
                    continue
                item_id = f"{src}→{tgt}"
                n = _insert_visibility_item(
                    bind, project_id, "graph_edge", item_id, domain_id,
                    context_source_origin, context_source_origin_type, now_str,
                )
                total_visibility += n
                n = _insert_audit_log(
                    bind, project_id, "graph_edge", item_id, domain_id, now_str
                )
                total_audit += n

        # 4b. Glossary terms
        if glossary_raw:
            try:
                glossary = json.loads(glossary_raw) if isinstance(glossary_raw, str) else glossary_raw
            except (json.JSONDecodeError, AttributeError):
                glossary = []

            for term_obj in glossary:
                term = term_obj.get("term")
                if not term:
                    continue
                # Normalised item_id matches context_lifecycle.py convention
                item_id = term.lower().replace(" ", "_")
                n = _insert_visibility_item(
                    bind, project_id, "glossary_term", item_id, domain_id,
                    context_source_origin, context_source_origin_type, now_str,
                )
                total_visibility += n
                n = _insert_audit_log(
                    bind, project_id, "glossary_term", item_id, domain_id, now_str
                )
                total_audit += n

        # ── 5. Backfill ArtifactVisibility for Requirements ──────────────────
        req_rows = bind.execute(
            sa.text(
                "SELECT id, source_references FROM requirements "
                "WHERE project_id = :pid"
            ),
            {"pid": project_id},
        ).fetchall()

        for req_row in req_rows:
            req_id = req_row[0]
            source_refs_raw = req_row[1]
            req_origin, req_origin_type = _derive_source_origin_from_refs(source_refs_raw)
            n = _insert_visibility_item(
                bind, project_id, "requirement", req_id, domain_id,
                req_origin, req_origin_type, now_str,
            )
            total_visibility += n
            n = _insert_audit_log(
                bind, project_id, "requirement", req_id, domain_id, now_str
            )
            total_audit += n

    logger.info(
        "006 backfill complete — domains=%d requirements=%d snapshots=%d "
        "visibility_rows=%d audit_rows=%d",
        total_domains, total_requirements, total_snapshots,
        total_visibility, total_audit,
    )


def _insert_visibility_item(
    bind, project_id: str, artifact_type: str, item_id: str,
    domain_id: str, source_origin: str | None, source_origin_type: str | None,
    now_str: str,
) -> int:
    """INSERT into artifact_visibility if not exists; returns 1 if inserted, 0 if skipped."""
    existing = bind.execute(
        sa.text(
            "SELECT id FROM artifact_visibility "
            "WHERE project_id = :pid AND artifact_type = :at "
            "  AND artifact_item_id = :iid AND visible_in_context_id = :vid"
        ),
        {"pid": project_id, "at": artifact_type, "iid": item_id, "vid": domain_id},
    ).fetchone()
    if existing:
        return 0

    bind.execute(
        sa.text(
            "INSERT INTO artifact_visibility "
            "(id, project_id, artifact_type, artifact_item_id, "
            " source_context_id, visible_in_context_id, lifecycle_status, "
            " source_origin, source_origin_type, sibling_of, created_at, updated_at) "
            "VALUES (:id, :pid, :at, :iid, :scid, :vid, 'promoted', "
            "        :so, :sot, NULL, :now, NULL)"
        ),
        {
            "id": str(uuid.uuid4()),
            "pid": project_id,
            "at": artifact_type,
            "iid": item_id,
            "scid": domain_id,
            "vid": domain_id,
            "so": source_origin,
            "sot": source_origin_type,
            "now": now_str,
        },
    )
    return 1


def _insert_audit_log(
    bind, project_id: str, artifact_type: str, item_id: str,
    domain_id: str, now_str: str,
) -> int:
    """Insert backfill audit log entry; idempotent (skipped if already exists)."""
    existing = bind.execute(
        sa.text(
            "SELECT id FROM artifact_audit_log "
            "WHERE project_id = :pid AND artifact_type = :at "
            "  AND artifact_item_id = :iid AND event_type = 'created' "
            "  AND actor = 'system'"
        ),
        {"pid": project_id, "at": artifact_type, "iid": item_id},
    ).fetchone()
    if existing:
        return 0

    bind.execute(
        sa.text(
            "INSERT INTO artifact_audit_log "
            "(id, project_id, artifact_type, artifact_item_id, event_type, "
            " work_context_id, old_value, new_value, actor, actor_id, note, created_at) "
            "VALUES (:id, :pid, :at, :iid, 'created', :did, "
            "        NULL, :nv, 'system', NULL, 'backfill migration', :now)"
        ),
        {
            "id": str(uuid.uuid4()),
            "pid": project_id,
            "at": artifact_type,
            "iid": item_id,
            "did": domain_id,
            "nv": json.dumps({"lifecycle_status": "promoted", "via": "backfill"}),
            "now": now_str,
        },
    )
    return 1


def downgrade() -> None:
    """
    Remove all backfill-created rows.

    Removes:
      - All ArtifactAuditLog rows with note='backfill migration' and actor='system'
      - All ArtifactVisibility rows created by the backfill (source_context_id
        pointing to a domain-level context + lifecycle_status="promoted")
      - Clears work_context_id / lifecycle_status on Requirements and AuditSnapshots
        that were set by this migration
      - Does NOT delete WorkContext rows (they may have been extended by the user)

    NOTE: This downgrade only targets backfill-specific rows identified by
    note='backfill migration'. Manually-created visibility data is untouched.
    """
    bind = op.get_bind()

    # Remove backfill audit log entries
    bind.execute(
        sa.text(
            "DELETE FROM artifact_audit_log "
            "WHERE actor = 'system' AND note = 'backfill migration'"
        )
    )

    # Clear visibility rows that were set during backfill
    # (identify by: source_context_id matches a domain-level context + lifecycle_status="promoted")
    # Conservative: only remove rows where source_context_id is a domain
    bind.execute(
        sa.text(
            "DELETE FROM artifact_visibility "
            "WHERE source_context_id IN ("
            "  SELECT id FROM work_contexts WHERE level = 'domain'"
            ") AND lifecycle_status = 'promoted'"
        )
    )

    # Reset requirements that were backfilled (work_context_id points to a domain)
    bind.execute(
        sa.text(
            "UPDATE requirements SET work_context_id = NULL "
            "WHERE work_context_id IN ("
            "  SELECT id FROM work_contexts WHERE level = 'domain'"
            ")"
        )
    )

    # Reset audit_snapshots that were backfilled
    bind.execute(
        sa.text(
            "UPDATE audit_snapshots SET work_context_id = NULL "
            "WHERE work_context_id IN ("
            "  SELECT id FROM work_contexts WHERE level = 'domain'"
            ")"
        )
    )
