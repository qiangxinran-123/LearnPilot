"""Record future evidence-backed M5 states without backfilling."""
import sqlalchemy as sa
from alembic import op

revision = "0019_m8_mastery_history"
down_revision = "0018_m7_5_practice_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mastery_history",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", sa.Integer(), sa.ForeignKey("courses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("knowledge_node_id", sa.Integer(), nullable=False),
        sa.Column("mastery_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("mastery_status", sa.String(32), nullable=False),
        sa.Column("confidence_level", sa.String(32), nullable=False),
        sa.Column("evidence_fingerprint", sa.String(64), nullable=False),
        sa.Column("algorithm_version", sa.String(64), nullable=False),
        sa.Column("graph_fingerprint", sa.String(64), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id", "knowledge_node_id"], ["knowledge_nodes.course_id", "knowledge_nodes.id"],
                                ondelete="CASCADE", name="fk_mastery_history_course_node"),
        sa.UniqueConstraint("user_id", "course_id", "knowledge_node_id", "algorithm_version", "evidence_fingerprint",
                            name="uq_mastery_history_version"),
        sa.CheckConstraint("mastery_score IS NULL OR (mastery_score >= 0 AND mastery_score <= 100)",
                           name="ck_mastery_history_score"),
    )
    op.create_index("ix_mastery_history_course_user_time", "mastery_history", ["course_id", "user_id", "recorded_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_mastery_history_course_user_time", table_name="mastery_history")
    op.drop_table("mastery_history")
