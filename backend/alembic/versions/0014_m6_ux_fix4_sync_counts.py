"""Persist the latest incremental knowledge synchronization node counts."""

import sqlalchemy as sa
from alembic import op

revision = "0014_m6_ux_fix4_sync_counts"
down_revision = "0013_m6_learning_plans"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "course_knowledge_build_states",
        sa.Column("last_added_node_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "course_knowledge_build_states",
        sa.Column("last_reused_node_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("course_knowledge_build_states", "last_reused_node_count")
    op.drop_column("course_knowledge_build_states", "last_added_node_count")
