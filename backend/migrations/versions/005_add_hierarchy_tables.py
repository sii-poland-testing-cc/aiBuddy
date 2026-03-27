"""Add hierarchy tables: organizations, workspaces; add FKs to projects.

Revision ID: 005
Revises: 004
Create Date: 2026-03-27

Seeds all existing project rows into a default organization.
"""

from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None

DEFAULT_ORG_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    # Step 1: create organizations table (HIER-01)
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Step 2: insert default organization (D-03)
    op.execute(
        f"INSERT INTO organizations (id, name, owner_id, created_at) "
        f"VALUES ('{DEFAULT_ORG_ID}', 'Default Organization', NULL, datetime('now'))"
    )

    # Step 3: create workspaces table (HIER-02)
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("organization_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["organization_id"], ["organizations.id"],
            name="fk_workspaces_organization_id", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workspaces_organization_id", "workspaces", ["organization_id"])
    op.create_index(
        "uq_workspaces_org_name", "workspaces",
        ["organization_id", "name"], unique=True,
    )

    # Step 4: add columns to projects (HIER-03, nullable first for SQLite)
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.add_column(sa.Column("organization_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("workspace_id", sa.String(), nullable=True))

    # Step 5: seed existing project rows into default org (D-03)
    op.execute(
        f"UPDATE projects SET organization_id = '{DEFAULT_ORG_ID}' "
        f"WHERE organization_id IS NULL"
    )

    # Step 6: add FK constraints + index (D-05, D-08)
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_projects_organization_id",
            "organizations", ["organization_id"], ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            "fk_projects_workspace_id",
            "workspaces", ["workspace_id"], ["id"],
            ondelete="SET NULL",
        )
    op.create_index("ix_projects_organization_id", "projects", ["organization_id"])


def downgrade() -> None:
    # Reverse order
    op.drop_index("ix_projects_organization_id", table_name="projects")
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_constraint("fk_projects_workspace_id", type_="foreignkey")
        batch_op.drop_constraint("fk_projects_organization_id", type_="foreignkey")
        batch_op.drop_column("workspace_id")
        batch_op.drop_column("organization_id")
    op.drop_index("uq_workspaces_org_name", table_name="workspaces")
    op.drop_index("ix_workspaces_organization_id", table_name="workspaces")
    op.drop_table("workspaces")
    op.drop_table("organizations")
