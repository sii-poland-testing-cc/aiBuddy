"""Add settings column to projects table.

Revision ID: 002
Revises: 001
Create Date: 2026-03-24
"""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.add_column(sa.Column("settings", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_column("settings")
