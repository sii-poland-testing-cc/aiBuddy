"""Add work_context and lifecycle tables (Phase 1 — schema only, no logic).

Revision ID: 005
Revises: 004
Create Date: 2026-03-26

New tables:
  work_contexts          — Domain / Epic / Story hierarchy per project
  artifact_audit_log     — append-only event log for every artifact state change
  promotion_conflicts    — queue of conflicts awaiting human resolution
  artifact_lifecycle     — manifest for JSON-stored artifact items (graph/glossary)

Altered tables:
  requirements           — add work_context_id FK, lifecycle_status (default "promoted")
  audit_snapshots        — add work_context_id FK, lifecycle_status (default "promoted")

All existing rows in requirements and audit_snapshots get lifecycle_status="promoted"
via server_default so data is backwards-compatible with Domain-level queries.
"""

from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. work_contexts ──────────────────────────────────────────────────────
    op.create_table(
        "work_contexts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("parent_id", sa.String(), nullable=True),
        sa.Column("level", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["work_contexts.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_work_contexts_project_id", "work_contexts", ["project_id"])
    op.create_index("ix_work_contexts_parent_id", "work_contexts", ["parent_id"])

    # ── 2. artifact_audit_log ─────────────────────────────────────────────────
    op.create_table(
        "artifact_audit_log",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("artifact_type", sa.String(), nullable=False),
        sa.Column("artifact_item_id", sa.String(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("work_context_id", sa.String(), nullable=True),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("actor", sa.String(), nullable=False, server_default="system"),
        sa.Column("actor_id", sa.String(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["work_context_id"], ["work_contexts.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_audit_log_project_type_item",
        "artifact_audit_log",
        ["project_id", "artifact_type", "artifact_item_id"],
    )
    op.create_index(
        "ix_audit_log_project_event_time",
        "artifact_audit_log",
        ["project_id", "event_type", "created_at"],
    )

    # ── 3. promotion_conflicts ────────────────────────────────────────────────
    op.create_table(
        "promotion_conflicts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("artifact_type", sa.String(), nullable=False),
        sa.Column("artifact_item_id", sa.String(), nullable=False),
        sa.Column("source_context_id", sa.String(), nullable=True),
        sa.Column("target_context_id", sa.String(), nullable=True),
        sa.Column("incoming_value", sa.Text(), nullable=False),
        sa.Column("existing_value", sa.Text(), nullable=False),
        sa.Column("conflict_reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by", sa.String(), nullable=True),
        sa.Column("resolution_value", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_context_id"], ["work_contexts.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["target_context_id"], ["work_contexts.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_promotion_conflicts_project_status",
        "promotion_conflicts",
        ["project_id", "status"],
    )
    op.create_index(
        "ix_promotion_conflicts_project_type_item",
        "promotion_conflicts",
        ["project_id", "artifact_type", "artifact_item_id"],
    )

    # ── 4. artifact_lifecycle ─────────────────────────────────────────────────
    op.create_table(
        "artifact_lifecycle",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("artifact_type", sa.String(), nullable=False),
        sa.Column("artifact_item_id", sa.String(), nullable=False),
        sa.Column("work_context_id", sa.String(), nullable=True),
        sa.Column(
            "lifecycle_status",
            sa.String(),
            nullable=False,
            server_default="promoted",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["work_context_id"], ["work_contexts.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "artifact_type",
            "artifact_item_id",
            name="uq_artifact_lifecycle_item",
        ),
    )
    op.create_index(
        "ix_artifact_lifecycle_project_id", "artifact_lifecycle", ["project_id"]
    )

    # ── 5. Alter requirements: add work_context_id + lifecycle_status ─────────
    with op.batch_alter_table("requirements", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("work_context_id", sa.String(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "lifecycle_status",
                sa.String(),
                nullable=False,
                server_default="promoted",
            )
        )
        batch_op.create_foreign_key(
            "fk_requirements_work_context",
            "work_contexts",
            ["work_context_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_requirements_work_context_id", ["work_context_id"]
        )

    # ── 6. Alter audit_snapshots: add work_context_id + lifecycle_status ──────
    with op.batch_alter_table("audit_snapshots", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("work_context_id", sa.String(), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "lifecycle_status",
                sa.String(),
                nullable=False,
                server_default="promoted",
            )
        )
        batch_op.create_foreign_key(
            "fk_audit_snapshots_work_context",
            "work_contexts",
            ["work_context_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_audit_snapshots_work_context_id", ["work_context_id"]
        )


def downgrade() -> None:
    # ── Reverse order: remove FK columns from altered tables first ────────────
    with op.batch_alter_table("audit_snapshots", schema=None) as batch_op:
        batch_op.drop_index("ix_audit_snapshots_work_context_id")
        batch_op.drop_constraint("fk_audit_snapshots_work_context", type_="foreignkey")
        batch_op.drop_column("lifecycle_status")
        batch_op.drop_column("work_context_id")

    with op.batch_alter_table("requirements", schema=None) as batch_op:
        batch_op.drop_index("ix_requirements_work_context_id")
        batch_op.drop_constraint("fk_requirements_work_context", type_="foreignkey")
        batch_op.drop_column("lifecycle_status")
        batch_op.drop_column("work_context_id")

    # ── Drop new tables in reverse FK dependency order ────────────────────────
    op.drop_index("ix_artifact_lifecycle_project_id", table_name="artifact_lifecycle")
    op.drop_table("artifact_lifecycle")

    op.drop_index("ix_promotion_conflicts_project_type_item", table_name="promotion_conflicts")
    op.drop_index("ix_promotion_conflicts_project_status", table_name="promotion_conflicts")
    op.drop_table("promotion_conflicts")

    op.drop_index("ix_audit_log_project_event_time", table_name="artifact_audit_log")
    op.drop_index("ix_audit_log_project_type_item", table_name="artifact_audit_log")
    op.drop_table("artifact_audit_log")

    op.drop_index("ix_work_contexts_parent_id", table_name="work_contexts")
    op.drop_index("ix_work_contexts_project_id", table_name="work_contexts")
    op.drop_table("work_contexts")
