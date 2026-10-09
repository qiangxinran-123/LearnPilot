"""Create the M3-B AI knowledge candidate staging schema."""

import sqlalchemy as sa
from alembic import op

revision = "0004_m3b_knowledge_extraction"
down_revision = "0003_m3a_knowledge_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_extraction_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("material_content_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "success",
                "failed",
                name="knowledge_extraction_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("prompt_version", sa.String(length=80), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=255), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("candidate_count >= 0", name="ck_knowledge_extraction_runs_candidate_count"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "id",
            "course_id",
            "material_id",
            name="uq_knowledge_extraction_runs_id_course_material",
        ),
    )
    op.create_index("ix_knowledge_extraction_runs_course_id", "knowledge_extraction_runs", ["course_id"])
    op.create_index("ix_knowledge_extraction_runs_material_id", "knowledge_extraction_runs", ["material_id"])
    op.create_index(
        "ix_knowledge_extraction_runs_idempotency",
        "knowledge_extraction_runs",
        ["material_id", "material_content_hash", "prompt_version", "model"],
    )
    op.create_index(
        "ix_knowledge_extraction_runs_material_current",
        "knowledge_extraction_runs",
        ["material_id", "is_current"],
    )

    op.create_table(
        "knowledge_candidates",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("extraction_run_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=False),
        sa.Column(
            "importance",
            sa.Enum(
                "low",
                "medium",
                "high",
                name="knowledge_candidate_importance",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "difficulty",
            sa.Enum(
                "basic",
                "intermediate",
                "advanced",
                name="knowledge_candidate_difficulty",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["extraction_run_id", "course_id", "material_id"],
            [
                "knowledge_extraction_runs.id",
                "knowledge_extraction_runs.course_id",
                "knowledge_extraction_runs.material_id",
            ],
            ondelete="CASCADE",
            name="fk_knowledge_candidates_run_context",
        ),
        sa.UniqueConstraint(
            "extraction_run_id",
            "normalized_name",
            name="uq_knowledge_candidates_run_normalized_name",
        ),
        sa.UniqueConstraint("id", "material_id", name="uq_knowledge_candidates_id_material"),
    )
    op.create_index("ix_knowledge_candidates_extraction_run_id", "knowledge_candidates", ["extraction_run_id"])
    op.create_index("ix_knowledge_candidates_material_id", "knowledge_candidates", ["material_id"])
    op.create_index(
        "ix_knowledge_candidates_course_material",
        "knowledge_candidates",
        ["course_id", "material_id"],
    )

    op.create_table(
        "knowledge_candidate_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("source_reference", sa.String(length=255), nullable=False),
        sa.Column("excerpt", sa.String(length=1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["candidate_id", "material_id"],
            ["knowledge_candidates.id", "knowledge_candidates.material_id"],
            ondelete="CASCADE",
            name="fk_knowledge_candidate_sources_candidate_material",
        ),
        sa.UniqueConstraint(
            "candidate_id",
            "material_id",
            "source_reference",
            name="uq_knowledge_candidate_sources_candidate_material_reference",
        ),
    )
    op.create_index(
        "ix_knowledge_candidate_sources_candidate_id",
        "knowledge_candidate_sources",
        ["candidate_id"],
    )
    op.create_index(
        "ix_knowledge_candidate_sources_material_id",
        "knowledge_candidate_sources",
        ["material_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_candidate_sources_material_id", table_name="knowledge_candidate_sources")
    op.drop_index("ix_knowledge_candidate_sources_candidate_id", table_name="knowledge_candidate_sources")
    op.drop_table("knowledge_candidate_sources")
    op.drop_index("ix_knowledge_candidates_course_material", table_name="knowledge_candidates")
    op.drop_index("ix_knowledge_candidates_material_id", table_name="knowledge_candidates")
    op.drop_index("ix_knowledge_candidates_extraction_run_id", table_name="knowledge_candidates")
    op.drop_table("knowledge_candidates")
    op.drop_index("ix_knowledge_extraction_runs_material_current", table_name="knowledge_extraction_runs")
    op.drop_index("ix_knowledge_extraction_runs_idempotency", table_name="knowledge_extraction_runs")
    op.drop_index("ix_knowledge_extraction_runs_material_id", table_name="knowledge_extraction_runs")
    op.drop_index("ix_knowledge_extraction_runs_course_id", table_name="knowledge_extraction_runs")
    op.drop_table("knowledge_extraction_runs")
