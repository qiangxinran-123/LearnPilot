"""Add the immutable diagnostic report policy reference."""

from alembic import op
import sqlalchemy as sa

revision = "0009_m4e_diagnostic_report_policy"
down_revision = "0008_m4a_diagnostic_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assessments", sa.Column("report_policy_version", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("assessments", "report_policy_version")
