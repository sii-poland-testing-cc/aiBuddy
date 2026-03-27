"""Copy-up promotion semantics (Decision D10).

Revision ID: 007
Revises: 006
Create Date: 2026-03-26

Changes:
  artifact_lifecycle — relax unique constraint from (project_id, artifact_type,
      artifact_item_id) to (project_id, artifact_type, artifact_item_id,
      work_context_id) so the same item can exist in multiple contexts
      (source stays, promoted copy is created in target).
      Also adds promoted_to_context_id to record where an item was promoted.

  requirements       — adds promoted_to_context_id so promoted source rows
      can show a "promoted to [parent]" badge in the UI.
"""

from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── 1. artifact_lifecycle: swap unique constraint + add promoted_to_context_id ──
    with op.batch_alter_table("artifact_lifecycle", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("promoted_to_context_id", sa.String(), nullable=True)
        )
        # Drop the old item-level unique (prevented same item in two contexts)
        batch_op.drop_constraint("uq_artifact_lifecycle_item", type_="unique")
        # New constraint: same item allowed in multiple contexts, but not twice
        # in the same context
        batch_op.create_unique_constraint(
            "uq_artifact_lifecycle_item_ctx",
            ["project_id", "artifact_type", "artifact_item_id", "work_context_id"],
        )

    # ── 2. requirements: add promoted_to_context_id ────────────────────────────────
    with op.batch_alter_table("requirements", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("promoted_to_context_id", sa.String(), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("requirements", schema=None) as batch_op:
        batch_op.drop_column("promoted_to_context_id")

    with op.batch_alter_table("artifact_lifecycle", schema=None) as batch_op:
        batch_op.drop_constraint("uq_artifact_lifecycle_item_ctx", type_="unique")
        batch_op.create_unique_constraint(
            "uq_artifact_lifecycle_item",
            ["project_id", "artifact_type", "artifact_item_id"],
        )
        batch_op.drop_column("promoted_to_context_id")
