"""Add requirement_gaps column to projects table.

Revision ID: 003
Revises: 002
Create Date: 2026-03-25

Why: Previously requirement_gaps was stuffed into Project.context_stats under a
"requirement_gaps" key. That created two-source-of-truth problems: M1 rebuild
overwrites context_stats blindly, wiping gaps that Faza 2 had written. A
dedicated column avoids the collision.
"""

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.add_column(sa.Column("requirement_gaps", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_column("requirement_gaps")
