"""Create the M3-C knowledge canonicalization schema."""

import sqlalchemy as sa
from alembic import op

revision = "0005_m3c_canonicalization"
down_revision = "0004_m3b_knowledge_extraction"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "knowledge_nodes",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "knowledge_nodes",
        sa.Column(
            "managed_by_canonicalization",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index("ix_knowledge_nodes_course_active", "knowledge_nodes", ["course_id", "is_active"])
    op.create_index(
        "uq_knowledge_candidates_id_course",
        "knowledge_candidates",
        ["id", "course_id"],
        unique=True,
    )

    op.create_table(
        "knowledge_canonicalization_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("candidate_snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "success",
                "failed",
                name="knowledge_canonicalization_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("prompt_version", sa.String(length=80), nullable=False),
        sa.Column("configuration_version", sa.String(length=80), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("canonical_node_count", sa.Integer(), nullable=False),
        sa.Column("merged_candidate_count", sa.Integer(), nullable=False),
        sa.Column("unresolved_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=255), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("candidate_count >= 0", name="ck_knowledge_canonicalization_candidate_count"),
        sa.CheckConstraint("canonical_node_count >= 0", name="ck_knowledge_canonicalization_node_count"),
        sa.CheckConstraint("merged_candidate_count >= 0", name="ck_knowledge_canonicalization_merged_count"),
        sa.CheckConstraint("unresolved_count >= 0", name="ck_knowledge_canonicalization_unresolved_count"),
        sa.CheckConstraint(
            "canonical_node_count <= candidate_count",
            name="ck_knowledge_canonicalization_nodes_within_candidates",
        ),
        sa.CheckConstraint(
            "merged_candidate_count <= candidate_count",
            name="ck_knowledge_canonicalization_merged_within_candidates",
        ),
        sa.CheckConstraint(
            "unresolved_count <= candidate_count",
            name="ck_knowledge_canonicalization_unresolved_within_candidates",
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("id", "course_id", name="uq_knowledge_canonicalization_runs_id_course"),
    )
    op.create_index(
        "ix_knowledge_canonicalization_runs_course_id",
        "knowledge_canonicalization_runs",
        ["course_id"],
    )
    op.create_index(
        "ix_knowledge_canonicalization_idempotency",
        "knowledge_canonicalization_runs",
        ["course_id", "candidate_snapshot_hash", "prompt_version", "model", "configuration_version"],
    )
    op.create_index(
        "ix_knowledge_canonicalization_course_current",
        "knowledge_canonicalization_runs",
        ["course_id", "is_current"],
    )

    op.create_table(
        "knowledge_candidate_resolutions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("canonicalization_run_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_node_id", sa.Integer(), nullable=False),
        sa.Column(
            "resolution_type",
            sa.Enum(
                "exact",
                "semantic_merge",
                "new_node",
                name="knowledge_resolution_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["canonicalization_run_id", "course_id"],
            ["knowledge_canonicalization_runs.id", "knowledge_canonicalization_runs.course_id"],
            ondelete="CASCADE",
            name="fk_knowledge_candidate_resolutions_run_course",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id", "course_id"],
            ["knowledge_candidates.id", "knowledge_candidates.course_id"],
            ondelete="CASCADE",
            name="fk_knowledge_candidate_resolutions_candidate_course",
        ),
        sa.ForeignKeyConstraint(
            ["course_id", "knowledge_node_id"],
            ["knowledge_nodes.course_id", "knowledge_nodes.id"],
            ondelete="CASCADE",
            name="fk_knowledge_candidate_resolutions_node_course",
        ),
        sa.UniqueConstraint(
            "canonicalization_run_id",
            "candidate_id",
            name="uq_knowledge_candidate_resolutions_run_candidate",
        ),
    )
    op.create_index(
        "ix_knowledge_candidate_resolutions_canonicalization_run_id",
        "knowledge_candidate_resolutions",
        ["canonicalization_run_id"],
    )
    op.create_index(
        "ix_knowledge_candidate_resolutions_candidate_id",
        "knowledge_candidate_resolutions",
        ["candidate_id"],
    )
    op.create_index(
        "ix_knowledge_candidate_resolutions_node_id",
        "knowledge_candidate_resolutions",
        ["knowledge_node_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_knowledge_candidate_resolutions_node_id",
        table_name="knowledge_candidate_resolutions",
    )
    op.drop_index(
        "ix_knowledge_candidate_resolutions_candidate_id",
        table_name="knowledge_candidate_resolutions",
    )
    op.drop_index(
        "ix_knowledge_candidate_resolutions_canonicalization_run_id",
        table_name="knowledge_candidate_resolutions",
    )
    op.drop_table("knowledge_candidate_resolutions")
    op.drop_index(
        "ix_knowledge_canonicalization_course_current",
        table_name="knowledge_canonicalization_runs",
    )
    op.drop_index(
        "ix_knowledge_canonicalization_idempotency",
        table_name="knowledge_canonicalization_runs",
    )
    op.drop_index(
        "ix_knowledge_canonicalization_runs_course_id",
        table_name="knowledge_canonicalization_runs",
    )
    op.drop_table("knowledge_canonicalization_runs")
    op.drop_index("uq_knowledge_candidates_id_course", table_name="knowledge_candidates")
    op.drop_index("ix_knowledge_nodes_course_active", table_name="knowledge_nodes")
    op.drop_column("knowledge_nodes", "managed_by_canonicalization")
    op.drop_column("knowledge_nodes", "is_active")
