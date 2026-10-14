"""Persist course knowledge build claims and successful material snapshots."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import LONGTEXT

revision = "0007_m3e_workspace_build_state"
down_revision = "0006_m3d_relationships"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "course_knowledge_build_states",
        sa.Column("course_id", sa.Integer(), nullable=False, primary_key=True),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("stage", sa.String(length=24), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=255), nullable=True),
        sa.Column("requested_material_snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column("success_material_snapshot_hash", sa.String(length=64), nullable=True),
        sa.Column("checkpoint_json", sa.Text().with_variant(LONGTEXT(), "mysql"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("job_id >= 0", name="ck_course_knowledge_build_job_id"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("course_knowledge_build_states")
