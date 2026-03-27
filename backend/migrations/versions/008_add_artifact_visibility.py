"""Add artifact_visibility table and source_origin columns on requirements.

Revision ID: 008
Revises: 007
Create Date: 2026-03-26

New tables:
  artifact_visibility — visibility manifest for all artifact items.
    One row per (item × context where visible). Supports multi-context
    visibility for the reference-based promotion model (Decision D10).

Altered tables:
  requirements — add source_origin (VARCHAR), source_origin_type (VARCHAR)
    to track which uploaded file/URL each requirement was extracted from.
"""

from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. artifact_visibility ─────────────────────────────────────────────────
    op.create_table(
        "artifact_visibility",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("artifact_type", sa.String(), nullable=False),
        sa.Column("artifact_item_id", sa.String(), nullable=False),
        sa.Column("source_context_id", sa.String(), nullable=True),
        sa.Column("visible_in_context_id", sa.String(), nullable=True),
        sa.Column(
            "lifecycle_status",
            sa.String(),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("sibling_of", sa.String(), nullable=True),
        sa.Column("source_origin", sa.String(), nullable=True),
        sa.Column("source_origin_type", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_context_id"], ["work_contexts.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["visible_in_context_id"], ["work_contexts.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "artifact_type",
            "artifact_item_id",
            "visible_in_context_id",
            name="uq_artifact_visibility_item_ctx",
        ),
    )
    # Primary query path: "show me everything visible in context X"
    op.create_index(
        "ix_artifact_vis_project_visible_type",
        "artifact_visibility",
        ["project_id", "visible_in_context_id", "artifact_type"],
    )
    # "What was created in this context?"
    op.create_index(
        "ix_artifact_vis_project_source_type",
        "artifact_visibility",
        ["project_id", "source_context_id", "artifact_type"],
    )
    # Item history across all contexts
    op.create_index(
        "ix_artifact_vis_project_type_item",
        "artifact_visibility",
        ["project_id", "artifact_type", "artifact_item_id"],
    )
    # "Find everything from this source file/URL"
    op.create_index(
        "ix_artifact_vis_project_origin",
        "artifact_visibility",
        ["project_id", "source_origin"],
    )

    # ── 2. requirements: add source_origin columns ─────────────────────────────
    with op.batch_alter_table("requirements", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("source_origin", sa.String(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("source_origin_type", sa.String(), nullable=True)
        )


def downgrade() -> None:
    # ── Remove source_origin columns from requirements ─────────────────────────
    with op.batch_alter_table("requirements", schema=None) as batch_op:
        batch_op.drop_column("source_origin_type")
        batch_op.drop_column("source_origin")

    # ── Drop artifact_visibility ───────────────────────────────────────────────
    op.drop_index("ix_artifact_vis_project_origin", table_name="artifact_visibility")
    op.drop_index("ix_artifact_vis_project_type_item", table_name="artifact_visibility")
    op.drop_index("ix_artifact_vis_project_source_type", table_name="artifact_visibility")
    op.drop_index("ix_artifact_vis_project_visible_type", table_name="artifact_visibility")
    op.drop_table("artifact_visibility")
