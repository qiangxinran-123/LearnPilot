"""Allow M4 assessments to represent M7 adaptive practice.

Revision ID: 0017_m7_4_practice
Revises: 0016_m7_3_tutor_messages
"""

import sqlalchemy as sa
from alembic import op

revision = "0017_m7_4_practice"
down_revision = "0016_m7_3_tutor_messages"
branch_labels = None
depends_on = None


OLD_TYPE = sa.Enum(
    "initial_diagnostic",
    name="assessment_type",
    native_enum=False,
    create_constraint=True,
)
NEW_TYPE = sa.Enum(
    "initial_diagnostic",
    "practice",
    name="assessment_type",
    native_enum=False,
    create_constraint=True,
)


def upgrade() -> None:
    with op.batch_alter_table("assessments") as batch:
        batch.alter_column(
            "assessment_type",
            existing_type=OLD_TYPE,
            type_=NEW_TYPE,
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("assessments") as batch:
        batch.alter_column(
            "assessment_type",
            existing_type=NEW_TYPE,
            type_=OLD_TYPE,
            existing_nullable=False,
        )
