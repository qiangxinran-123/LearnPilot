"""Create M7-1 learning sessions and persisted task state."""

import sqlalchemy as sa
from alembic import op

revision = "0015_m7_1_sessions"
down_revision = "0014_m6_ux_fix4_sync_counts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "learning_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("target_knowledge_node_id", sa.Integer(), nullable=False),
        sa.Column("source_learning_plan_id", sa.Integer(), nullable=True),
        sa.Column("practice_assessment_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "created",
                "in_progress",
                "completed",
                "cancelled",
                name="learning_session_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("active_slot", sa.Integer(), nullable=True),
        sa.Column("session_contract_version", sa.String(length=64), nullable=False),
        sa.Column("completion_summary", sa.JSON(), nullable=True),
        sa.Column(
            "recommendation_refresh_status",
            sa.Enum(
                "not_requested",
                "pending",
                "succeeded",
                "failed",
                name="recommendation_refresh_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(status IN ('created', 'in_progress') AND active_slot = 1) OR "
            "(status IN ('completed', 'cancelled') AND active_slot IS NULL)",
            name="ck_learning_sessions_status_active_slot",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["course_id", "target_knowledge_node_id"],
            ["knowledge_nodes.course_id", "knowledge_nodes.id"],
            ondelete="RESTRICT",
            name="fk_learning_sessions_target_in_course",
        ),
        sa.ForeignKeyConstraint(
            ["source_learning_plan_id"], ["learning_plans.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["practice_assessment_id"], ["assessments.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("practice_assessment_id", name="uq_learning_sessions_practice_assessment"),
        sa.UniqueConstraint(
            "user_id",
            "course_id",
            "target_knowledge_node_id",
            "active_slot",
            name="uq_learning_sessions_active_target",
        ),
    )
    op.create_index("ix_learning_sessions_user_id", "learning_sessions", ["user_id"])
    op.create_index("ix_learning_sessions_course_id", "learning_sessions", ["course_id"])
    op.create_index(
        "ix_learning_sessions_target_knowledge_node_id",
        "learning_sessions",
        ["target_knowledge_node_id"],
    )
    op.create_index(
        "ix_learning_sessions_source_learning_plan_id",
        "learning_sessions",
        ["source_learning_plan_id"],
    )

    op.create_table(
        "learning_session_task_states",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("source_learning_task_id", sa.Integer(), nullable=True),
        sa.Column(
            "phase",
            sa.Enum(
                "concept_learning",
                "guided_example",
                "adaptive_practice",
                name="learning_session_task_phase",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "not_started",
                "in_progress",
                "completed",
                name="learning_session_task_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("progress", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "order_index >= 0 AND order_index <= 2", name="ck_learning_session_tasks_order"
        ),
        sa.ForeignKeyConstraint(["session_id"], ["learning_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["source_learning_task_id"], ["learning_tasks.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("session_id", "phase", name="uq_learning_session_tasks_phase"),
        sa.UniqueConstraint(
            "session_id", "order_index", name="uq_learning_session_tasks_order"
        ),
    )
    op.create_index(
        "ix_learning_session_task_states_session_id",
        "learning_session_task_states",
        ["session_id"],
    )
    op.create_index(
        "ix_learning_session_task_states_source_learning_task_id",
        "learning_session_task_states",
        ["source_learning_task_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_learning_session_task_states_source_learning_task_id",
        table_name="learning_session_task_states",
    )
    op.drop_index(
        "ix_learning_session_task_states_session_id",
        table_name="learning_session_task_states",
    )
    op.drop_table("learning_session_task_states")
    op.drop_index("ix_learning_sessions_source_learning_plan_id", table_name="learning_sessions")
    op.drop_index(
        "ix_learning_sessions_target_knowledge_node_id", table_name="learning_sessions"
    )
    op.drop_index("ix_learning_sessions_course_id", table_name="learning_sessions")
    op.drop_index("ix_learning_sessions_user_id", table_name="learning_sessions")
    op.drop_table("learning_sessions")
