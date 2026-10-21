"""Create the M5-C current student knowledge state."""

import sqlalchemy as sa
from alembic import op

revision = "0012_m5c_mastery_state"
down_revision = "0011_m5b_evidence_mapping"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "student_knowledge_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_node_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_model_version", sa.String(length=120), nullable=True),
        sa.Column("mastery_score", sa.Numeric(5, 2), nullable=True),
        sa.Column(
            "mastery_status",
            sa.Enum(
                "not_assessed",
                "good_performance",
                "needs_reinforcement",
                "possibly_weak",
                "needs_attention",
                name="mastery_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "confidence_level",
            sa.Enum(
                "insufficient",
                "low",
                "medium",
                "high",
                name="confidence_level",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("confidence_reason_codes", sa.JSON(), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("independent_evidence_count", sa.Integer(), nullable=False),
        sa.Column("assessment_count", sa.Integer(), nullable=False),
        sa.Column("algorithm_version", sa.String(length=64), nullable=False),
        sa.Column("evidence_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "mastery_score IS NULL OR (mastery_score >= 0 AND mastery_score <= 100)",
            name="ck_student_knowledge_state_mastery_score",
        ),
        sa.CheckConstraint("evidence_count >= 0", name="ck_student_knowledge_state_evidence_count"),
        sa.CheckConstraint(
            "independent_evidence_count >= 0 AND independent_evidence_count <= evidence_count",
            name="ck_student_knowledge_state_independent_count",
        ),
        sa.CheckConstraint(
            "assessment_count >= 0 AND assessment_count <= independent_evidence_count",
            name="ck_student_knowledge_state_assessment_count",
        ),
        sa.CheckConstraint("length(algorithm_version) > 0", name="ck_student_knowledge_state_algorithm_version"),
        sa.CheckConstraint("length(evidence_fingerprint) = 64", name="ck_student_knowledge_state_fingerprint"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["course_id", "knowledge_node_id"],
            ["knowledge_nodes.course_id", "knowledge_nodes.id"],
            ondelete="CASCADE",
            name="fk_student_knowledge_state_course_node",
        ),
        sa.UniqueConstraint(
            "user_id",
            "course_id",
            "knowledge_node_id",
            name="uq_student_knowledge_state_identity",
        ),
    )
    op.create_index("ix_student_knowledge_states_user_id", "student_knowledge_states", ["user_id"])
    op.create_index("ix_student_knowledge_states_knowledge_node_id", "student_knowledge_states", ["knowledge_node_id"])
    op.create_index(
        "ix_student_knowledge_state_course_user",
        "student_knowledge_states",
        ["course_id", "user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_student_knowledge_state_course_user", table_name="student_knowledge_states")
    op.drop_index("ix_student_knowledge_states_knowledge_node_id", table_name="student_knowledge_states")
    op.drop_index("ix_student_knowledge_states_user_id", table_name="student_knowledge_states")
    op.drop_table("student_knowledge_states")
