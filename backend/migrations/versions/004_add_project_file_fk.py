"""Add FK constraint from project_files.last_used_in_audit_id to audit_snapshots.id.

Revision ID: 004
Revises: 003
Create Date: 2026-03-25

Why: last_used_in_audit_id was a bare String with no FK. This means deleting a snapshot
leaves dangling references in project_files. ON DELETE SET NULL restores the file to
"never audited" state when its snapshot is pruned — correct semantic.
"""

from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("project_files", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_project_files_last_audit",
            "audit_snapshots",
            ["last_used_in_audit_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("project_files", schema=None) as batch_op:
        batch_op.drop_constraint("fk_project_files_last_audit", type_="foreignkey")
