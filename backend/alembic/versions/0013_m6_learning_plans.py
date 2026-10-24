"""Create M6-3 learning plans and ordered tasks."""

import sqlalchemy as sa
from alembic import op

revision = "0013_m6_learning_plans"
down_revision = "0012_m5c_mastery_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("target_node_id", sa.Integer(), nullable=False),
        sa.Column("reason_codes", sa.JSON(), nullable=False),
        sa.Column("priority_score", sa.Numeric(5, 4), nullable=False),
        sa.Column("priority_breakdown", sa.JSON(), nullable=False),
        sa.Column("prerequisite_evidence", sa.JSON(), nullable=False),
        sa.Column("blocked_target_node_ids", sa.JSON(), nullable=False),
        sa.Column("context_fingerprint", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "available",
                "superseded",
                name="learning_plan_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("active_slot", sa.Integer(), nullable=True),
        sa.Column("plan_schema_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("priority_score >= 0 AND priority_score <= 1", name="ck_learning_plans_priority_score"),
        sa.CheckConstraint("length(context_fingerprint) = 64", name="ck_learning_plans_context_fingerprint"),
        sa.CheckConstraint(
            "(status = 'available' AND active_slot = 1) OR "
            "(status = 'superseded' AND active_slot IS NULL)",
            name="ck_learning_plans_status_active_slot",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["course_id", "target_node_id"],
            ["knowledge_nodes.course_id", "knowledge_nodes.id"],
            ondelete="CASCADE",
            name="fk_learning_plans_target_in_course",
        ),
        sa.UniqueConstraint("user_id", "course_id", "active_slot", name="uq_learning_plans_active_slot"),
    )
    op.create_index("ix_learning_plans_user_id", "learning_plans", ["user_id"])
    op.create_index("ix_learning_plans_course_id", "learning_plans", ["course_id"])
    op.create_index("ix_learning_plans_target_node_id", "learning_plans", ["target_node_id"])
    op.create_index("ix_learning_plans_context_fingerprint", "learning_plans", ["context_fingerprint"])

    op.create_table(
        "learning_tasks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_node_id", sa.Integer(), nullable=False),
        sa.Column(
            "task_type",
            sa.Enum(
                "concept_review",
                "example_walkthrough",
                "targeted_practice",
                name="learning_task_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("order_index >= 0 AND order_index <= 2", name="ck_learning_tasks_order_index"),
        sa.CheckConstraint(
            "estimated_minutes IS NULL OR estimated_minutes > 0",
            name="ck_learning_tasks_estimated_minutes",
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["learning_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["knowledge_node_id"], ["knowledge_nodes.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("plan_id", "order_index", name="uq_learning_tasks_plan_order"),
    )
    op.create_index("ix_learning_tasks_plan_id", "learning_tasks", ["plan_id"])
    op.create_index("ix_learning_tasks_knowledge_node_id", "learning_tasks", ["knowledge_node_id"])


def downgrade() -> None:
    op.drop_index("ix_learning_tasks_knowledge_node_id", table_name="learning_tasks")
    op.drop_index("ix_learning_tasks_plan_id", table_name="learning_tasks")
    op.drop_table("learning_tasks")
    op.drop_index("ix_learning_plans_context_fingerprint", table_name="learning_plans")
    op.drop_index("ix_learning_plans_target_node_id", table_name="learning_plans")
    op.drop_index("ix_learning_plans_course_id", table_name="learning_plans")
    op.drop_index("ix_learning_plans_user_id", table_name="learning_plans")
    op.drop_table("learning_plans")
