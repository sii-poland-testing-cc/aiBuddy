"""Initial schema — all tables as of schema v5.

Revision ID: 001
Revises:
Create Date: 2026-03-23

Tables created:
  projects
  project_files          (source_type, last_used_in_audit_id already included)
  audit_snapshots
  requirements
  requirement_tc_mappings
  coverage_scores
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column("mind_map", sa.Text(), nullable=True),
        sa.Column("glossary", sa.Text(), nullable=True),
        sa.Column("context_stats", sa.Text(), nullable=True),
        sa.Column("context_built_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("context_files", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "project_files",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("file_path", sa.String(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("indexed", sa.Boolean(), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column("last_used_in_audit_id", sa.String(), nullable=True),
        sa.Column("source_type", sa.Text(), nullable=False, server_default="file"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_files_project_id", "project_files", ["project_id"])

    op.create_table(
        "audit_snapshots",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("files_used", sa.Text(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("requirements_uncovered", sa.Text(), nullable=True),
        sa.Column("recommendations", sa.Text(), nullable=True),
        sa.Column("diff", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "requirements",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("parent_id", sa.String(), nullable=True),
        sa.Column("level", sa.String(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("source_references", sa.Text(), nullable=True),
        sa.Column("taxonomy", sa.Text(), nullable=True),
        sa.Column("completeness_score", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("human_reviewed", sa.Boolean(), nullable=True),
        sa.Column("needs_review", sa.Boolean(), nullable=True),
        sa.Column("review_reason", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["parent_id"], ["requirements.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_requirements_project_id", "requirements", ["project_id"])
    op.create_index("ix_requirements_parent_id", "requirements", ["parent_id"])

    op.create_table(
        "requirement_tc_mappings",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("requirement_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("tc_source_file", sa.String(), nullable=False),
        sa.Column("tc_identifier", sa.String(), nullable=False),
        sa.Column("mapping_confidence", sa.Float(), nullable=False),
        sa.Column("mapping_method", sa.String(), nullable=False),
        sa.Column("coverage_aspects", sa.Text(), nullable=True),
        sa.Column("human_verified", sa.Boolean(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"], ["requirements.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_requirement_tc_mappings_requirement_id",
        "requirement_tc_mappings",
        ["requirement_id"],
    )
    op.create_index(
        "ix_requirement_tc_mappings_project_id",
        "requirement_tc_mappings",
        ["project_id"],
    )

    op.create_table(
        "coverage_scores",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("requirement_id", sa.String(), nullable=False),
        sa.Column("snapshot_id", sa.String(), nullable=True),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("total_score", sa.Float(), nullable=False),
        sa.Column("base_coverage", sa.Float(), nullable=False),
        sa.Column("depth_coverage", sa.Float(), nullable=False),
        sa.Column("quality_weight", sa.Float(), nullable=False),
        sa.Column("confidence_penalty", sa.Float(), nullable=False),
        sa.Column("crossref_bonus", sa.Float(), nullable=False),
        sa.Column("matched_tc_count", sa.Integer(), nullable=True),
        sa.Column("coverage_aspects_present", sa.Text(), nullable=True),
        sa.Column("coverage_aspects_missing", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["requirement_id"], ["requirements.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["audit_snapshots.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_coverage_scores_requirement_id", "coverage_scores", ["requirement_id"]
    )
    op.create_index(
        "ix_coverage_scores_snapshot_id", "coverage_scores", ["snapshot_id"]
    )
    op.create_index(
        "ix_coverage_scores_project_id", "coverage_scores", ["project_id"]
    )


def downgrade() -> None:
    op.drop_table("coverage_scores")
    op.drop_table("requirement_tc_mappings")
    op.drop_table("requirements")
    op.drop_table("audit_snapshots")
    op.drop_table("project_files")
    op.drop_table("projects")
