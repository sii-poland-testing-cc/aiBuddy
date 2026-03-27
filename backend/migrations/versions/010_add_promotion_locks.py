"""Add promotion_locks table for pessimistic locking (Phase 8.4).

Revision ID: 010
Revises: 009
Create Date: 2026-03-27

New tables:
  promotion_locks — application-level promotion lock for SQLite.
    One row per (project_id, target_context_id) while a promotion is running.
    INSERT fails on unique constraint if another promotion is already in progress.
    PostgreSQL uses SELECT … FOR UPDATE instead.
"""

from alembic import op
import sqlalchemy as sa


revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("__dummy__", recreate="never"):
        pass  # batch mode for SQLite compat

    op.create_table(
        "promotion_locks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_context_id",
            sa.String(),
            sa.ForeignKey("work_contexts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acquired_by", sa.String(), nullable=False, server_default="system"),
        sa.UniqueConstraint(
            "project_id", "target_context_id",
            name="uq_promotion_lock_project_target",
        ),
    )


def downgrade() -> None:
    op.drop_table("promotion_locks")
