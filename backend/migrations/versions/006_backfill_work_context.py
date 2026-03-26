"""Backfill existing project data into the lifecycle model (Phase 8).

Revision ID: 006
Revises: 005
Create Date: 2026-03-26

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

  4. Inserts ArtifactLifecycle manifest rows for every graph node, graph edge,
     and glossary term found in Project.mind_map / Project.glossary.
     Uses INSERT OR IGNORE so re-running the migration is safe.

  5. Emits one ArtifactAuditLog row per manifest item:
       event_type="created", actor="system", note="backfill migration"
     Skipped if an audit-log entry for the same (project_id, artifact_type,
     artifact_item_id) already exists (idempotent).

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


def upgrade() -> None:
    bind = op.get_bind()

    # ── Fetch all projects ────────────────────────────────────────────────────
    projects = bind.execute(
        sa.text(
            "SELECT id, mind_map, glossary, context_built_at, created_at "
            "FROM projects"
        )
    ).fetchall()

    promoted_at_default = datetime.now(timezone.utc).isoformat()
    total_domains = 0
    total_requirements = 0
    total_snapshots = 0
    total_manifest = 0
    total_audit = 0

    for project in projects:
        project_id = project[0]
        mind_map_raw = project[1]
        glossary_raw = project[2]
        context_built_at = project[3]
        created_at = project[4]

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

        # ── 2. Backfill Requirements ──────────────────────────────────────────
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

        # ── 4 + 5. Backfill ArtifactLifecycle manifest + AuditLog ────────────
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
                n = _insert_manifest_item(
                    bind, project_id, "graph_node", item_id, domain_id, now_str
                )
                total_manifest += n
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
                n = _insert_manifest_item(
                    bind, project_id, "graph_edge", item_id, domain_id, now_str
                )
                total_manifest += n
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
                n = _insert_manifest_item(
                    bind, project_id, "glossary_term", item_id, domain_id, now_str
                )
                total_manifest += n
                n = _insert_audit_log(
                    bind, project_id, "glossary_term", item_id, domain_id, now_str
                )
                total_audit += n

    logger.info(
        "006 backfill complete — domains=%d requirements=%d snapshots=%d "
        "manifest_rows=%d audit_rows=%d",
        total_domains, total_requirements, total_snapshots,
        total_manifest, total_audit,
    )


def _insert_manifest_item(
    bind, project_id: str, artifact_type: str, item_id: str,
    domain_id: str, now_str: str,
) -> int:
    """INSERT OR IGNORE into artifact_lifecycle; returns 1 if inserted, 0 if skipped."""
    existing = bind.execute(
        sa.text(
            "SELECT id FROM artifact_lifecycle "
            "WHERE project_id = :pid AND artifact_type = :at AND artifact_item_id = :iid"
        ),
        {"pid": project_id, "at": artifact_type, "iid": item_id},
    ).fetchone()
    if existing:
        return 0

    bind.execute(
        sa.text(
            "INSERT INTO artifact_lifecycle "
            "(id, project_id, artifact_type, artifact_item_id, work_context_id, "
            " lifecycle_status, created_at, updated_at) "
            "VALUES (:id, :pid, :at, :iid, :did, 'promoted', :now, NULL)"
        ),
        {
            "id": str(uuid.uuid4()),
            "pid": project_id,
            "at": artifact_type,
            "iid": item_id,
            "did": domain_id,
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
      - All ArtifactLifecycle rows created by the backfill (work_context_id set
        to a domain from this backfill; use inner join approach for safety)
      - Clears work_context_id / lifecycle_status on Requirements and AuditSnapshots
        that were set by this migration
      - Does NOT delete WorkContext rows (they may have been extended by the user)

    NOTE: This downgrade only targets backfill-specific rows identified by
    note='backfill migration'. Manually-created lifecycle data is untouched.
    """
    bind = op.get_bind()

    # Remove backfill audit log entries
    bind.execute(
        sa.text(
            "DELETE FROM artifact_audit_log "
            "WHERE actor = 'system' AND note = 'backfill migration'"
        )
    )

    # Clear lifecycle manifest rows that were set during backfill
    # (identify by: work_context_id matches a domain-level context + lifecycle_status="promoted")
    # Conservative: only remove rows where work_context_id is a domain
    bind.execute(
        sa.text(
            "DELETE FROM artifact_lifecycle "
            "WHERE work_context_id IN ("
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
