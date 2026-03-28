"""Add users table and organizations.owner_id FK.

Revision ID: 006
Revises: 005
Create Date: 2026-03-28

Why: Phase 2 authentication requires a users table for email/password credentials.
     The organizations.owner_id column already exists (nullable String, no FK constraint)
     from Phase 1 (migration 005). This migration creates the users table first, then
     adds the FK constraint from organizations.owner_id → users.id.

Order matters (SQLite FK safety):
  1. Create users table
  2. Create index on users.email
  3. Add FK from organizations.owner_id → users.id (users must exist first)
"""

from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Step 1: Create users table first (BEFORE any FK references to it)
    op.create_table(
        "users",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("hashed_password", sa.String(), nullable=False),
        sa.Column("is_superadmin", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )

    # Step 2: Index on email for fast lookups
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # Step 3: Add FK from organizations.owner_id → users.id
    # organizations.owner_id already exists as a nullable String column (Phase 1).
    # Here we add the FK constraint via batch_alter (required for SQLite).
    with op.batch_alter_table("organizations") as batch_op:
        batch_op.create_foreign_key(
            "fk_organizations_owner_id",
            "users",
            ["owner_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade() -> None:
    # Step 1: Drop FK from organizations first (reverse order)
    with op.batch_alter_table("organizations") as batch_op:
        batch_op.drop_constraint("fk_organizations_owner_id", type_="foreignkey")

    # Step 2: Drop index
    op.drop_index("ix_users_email", table_name="users")

    # Step 3: Drop users table
    op.drop_table("users")
