"""Create the M4-A diagnostic domain foundation."""

import sqlalchemy as sa
from alembic import op

revision = "0008_m4a_diagnostic_domain"
down_revision = "0007_m3e_workspace_build_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column(
            "question_type",
            sa.Enum(
                "single_choice",
                "true_false",
                "multiple_choice",
                name="question_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("stem", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("correct_answer", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column(
            "difficulty",
            sa.Enum(
                "easy",
                "medium",
                "hard",
                name="question_difficulty",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "validation_status",
            sa.Enum(
                "pending",
                "validated",
                "rejected",
                name="question_validation_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("source_refs", sa.JSON(), nullable=False),
        sa.Column("generation_metadata", sa.JSON(), nullable=False),
        sa.Column("content_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("content_version >= 1", name="ck_questions_content_version"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("course_id", "id", name="uq_questions_course_id_id"),
    )
    op.create_index("ix_questions_course_id", "questions", ["course_id"])

    op.create_table(
        "question_knowledge_nodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_node_id", sa.Integer(), nullable=False),
        sa.Column(
            "relation_role",
            sa.Enum(
                "primary",
                "secondary",
                name="question_knowledge_relation_role",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["course_id", "question_id"],
            ["questions.course_id", "questions.id"],
            ondelete="CASCADE",
            name="fk_question_knowledge_nodes_question_course",
        ),
        sa.ForeignKeyConstraint(
            ["course_id", "knowledge_node_id"],
            ["knowledge_nodes.course_id", "knowledge_nodes.id"],
            ondelete="CASCADE",
            name="fk_question_knowledge_nodes_node_course",
        ),
        sa.UniqueConstraint(
            "question_id", "knowledge_node_id", name="uq_question_knowledge_nodes_question_node"
        ),
    )
    op.create_index("ix_question_knowledge_nodes_question_id", "question_knowledge_nodes", ["question_id"])
    op.create_index(
        "ix_question_knowledge_nodes_knowledge_node_id", "question_knowledge_nodes", ["knowledge_node_id"]
    )
    op.create_index(
        "ix_question_knowledge_nodes_course_node",
        "question_knowledge_nodes",
        ["course_id", "knowledge_node_id"],
    )

    op.create_table(
        "assessments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column(
            "assessment_type",
            sa.Enum(
                "initial_diagnostic",
                name="assessment_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "ready",
                "in_progress",
                "submitted",
                name="assessment_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("id", "course_id", name="uq_assessments_id_course_id"),
    )
    op.create_index("ix_assessments_course_id", "assessments", ["course_id"])
    op.create_index("ix_assessments_owner_id", "assessments", ["owner_id"])

    op.create_table(
        "assessment_questions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("assessment_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("question_snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("order_index >= 0", name="ck_assessment_questions_order_index"),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="SET NULL"),
        sa.UniqueConstraint(
            "assessment_id", "id", name="uq_assessment_questions_assessment_id_id"
        ),
        sa.UniqueConstraint(
            "assessment_id", "order_index", name="uq_assessment_questions_assessment_order"
        ),
        sa.UniqueConstraint(
            "assessment_id", "question_id", name="uq_assessment_questions_assessment_question"
        ),
    )
    op.create_index("ix_assessment_questions_assessment_id", "assessment_questions", ["assessment_id"])
    op.create_index("ix_assessment_questions_question_id", "assessment_questions", ["question_id"])

    op.create_table(
        "responses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("assessment_id", sa.Integer(), nullable=False),
        sa.Column("assessment_question_id", sa.Integer(), nullable=False),
        sa.Column("answer_payload", sa.JSON(), nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("points_awarded", sa.Numeric(10, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assessment_id"], ["assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["assessment_id", "assessment_question_id"],
            ["assessment_questions.assessment_id", "assessment_questions.id"],
            ondelete="CASCADE",
            name="fk_responses_assessment_question",
        ),
        sa.UniqueConstraint("assessment_question_id", name="uq_responses_assessment_question_id"),
    )
    op.create_index("ix_responses_assessment_id", "responses", ["assessment_id"])


def downgrade() -> None:
    op.drop_index("ix_responses_assessment_id", table_name="responses")
    op.drop_table("responses")
    op.drop_index("ix_assessment_questions_question_id", table_name="assessment_questions")
    op.drop_index("ix_assessment_questions_assessment_id", table_name="assessment_questions")
    op.drop_table("assessment_questions")
    op.drop_index("ix_assessments_owner_id", table_name="assessments")
    op.drop_index("ix_assessments_course_id", table_name="assessments")
    op.drop_table("assessments")
    op.drop_index("ix_question_knowledge_nodes_course_node", table_name="question_knowledge_nodes")
    op.drop_index("ix_question_knowledge_nodes_knowledge_node_id", table_name="question_knowledge_nodes")
    op.drop_index("ix_question_knowledge_nodes_question_id", table_name="question_knowledge_nodes")
    op.drop_table("question_knowledge_nodes")
    op.drop_index("ix_questions_course_id", table_name="questions")
    op.drop_table("questions")
