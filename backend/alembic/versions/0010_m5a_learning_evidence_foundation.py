"""Create the M5-A learning evidence foundation."""

import sqlalchemy as sa
from alembic import op

revision = "0010_m5a_learning_evidence"
down_revision = "0009_m4e_diagnostic_report_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column(
            "source_type",
            sa.Enum(
                "diagnostic",
                name="learning_evidence_source_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("source_assessment_id", sa.Integer(), nullable=False),
        sa.Column("source_question_snapshot_id", sa.Integer(), nullable=False),
        sa.Column("source_response_id", sa.Integer(), nullable=False),
        sa.Column("historical_knowledge_node_ref", sa.Integer(), nullable=False),
        sa.Column("knowledge_model_version", sa.String(length=120), nullable=True),
        sa.Column("normalized_score", sa.Numeric(6, 5), nullable=False),
        sa.Column(
            "difficulty",
            sa.Enum(
                "easy",
                "medium",
                "hard",
                name="learning_evidence_difficulty",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("attribution_weight", sa.Numeric(6, 5), nullable=False),
        sa.Column("source_scoring_version", sa.String(length=64), nullable=False),
        sa.Column("evidence_schema_version", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "normalized_score >= 0 AND normalized_score <= 1",
            name="ck_learning_evidence_normalized_score",
        ),
        sa.CheckConstraint(
            "attribution_weight > 0 AND attribution_weight <= 1",
            name="ck_learning_evidence_attribution_weight",
        ),
        sa.CheckConstraint(
            "historical_knowledge_node_ref > 0",
            name="ck_learning_evidence_historical_node_ref",
        ),
        sa.CheckConstraint(
            "length(source_scoring_version) > 0",
            name="ck_learning_evidence_source_scoring_version",
        ),
        sa.CheckConstraint(
            "length(evidence_schema_version) > 0",
            name="ck_learning_evidence_schema_version",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_assessment_id"], ["assessments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["source_assessment_id", "source_question_snapshot_id"],
            ["assessment_questions.assessment_id", "assessment_questions.id"],
            ondelete="RESTRICT",
            name="fk_learning_evidence_assessment_question",
        ),
        sa.ForeignKeyConstraint(["source_response_id"], ["responses.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint(
            "source_type",
            "source_question_snapshot_id",
            "historical_knowledge_node_ref",
            "evidence_schema_version",
            name="uq_learning_evidence_source_node_version",
        ),
    )
    op.create_index("ix_learning_evidence_user_id", "learning_evidence", ["user_id"])
    op.create_index("ix_learning_evidence_course_id", "learning_evidence", ["course_id"])
    op.create_index("ix_learning_evidence_source_response_id", "learning_evidence", ["source_response_id"])
    op.create_index(
        "ix_learning_evidence_course_user",
        "learning_evidence",
        ["course_id", "user_id"],
    )
    op.create_index(
        "ix_learning_evidence_source_assessment",
        "learning_evidence",
        ["source_assessment_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_learning_evidence_source_assessment", table_name="learning_evidence")
    op.drop_index("ix_learning_evidence_course_user", table_name="learning_evidence")
    op.drop_index("ix_learning_evidence_source_response_id", table_name="learning_evidence")
    op.drop_index("ix_learning_evidence_course_id", table_name="learning_evidence")
    op.drop_index("ix_learning_evidence_user_id", table_name="learning_evidence")
    op.drop_table("learning_evidence")
