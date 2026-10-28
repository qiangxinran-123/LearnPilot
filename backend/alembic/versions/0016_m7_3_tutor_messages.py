"""Create M7-3 session-scoped Tutor messages.

Revision ID: 0016_m7_3_tutor_messages
Revises: 0015_m7_1_sessions
"""

import sqlalchemy as sa
from alembic import op

revision = "0016_m7_3_tutor_messages"
down_revision = "0015_m7_1_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tutor_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("task_state_id", sa.Integer(), nullable=True),
        sa.Column("exchange_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column(
            "role",
            sa.Enum(
                "user",
                "assistant",
                name="tutor_message_role",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "teaching_strategy",
            sa.Enum(
                "hint",
                "guided_question",
                "example",
                "step_by_step_explanation",
                "full_explanation",
                name="teaching_strategy",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("grounded", sa.Boolean(), nullable=False),
        sa.Column("insufficient_evidence", sa.Boolean(), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=True),
        sa.Column("model", sa.String(length=160), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["learning_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_state_id"], ["learning_session_task_states.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("session_id", "exchange_id", "role", name="uq_tutor_messages_exchange_role"),
        sa.UniqueConstraint("session_id", "idempotency_key", name="uq_tutor_messages_idempotency"),
    )
    op.create_index("ix_tutor_messages_session_id", "tutor_messages", ["session_id"])
    op.create_index("ix_tutor_messages_task_state_id", "tutor_messages", ["task_state_id"])
    op.create_index("ix_tutor_messages_exchange_id", "tutor_messages", ["exchange_id"])


def downgrade() -> None:
    op.drop_index("ix_tutor_messages_exchange_id", table_name="tutor_messages")
    op.drop_index("ix_tutor_messages_task_state_id", table_name="tutor_messages")
    op.drop_index("ix_tutor_messages_session_id", table_name="tutor_messages")
    op.drop_table("tutor_messages")
