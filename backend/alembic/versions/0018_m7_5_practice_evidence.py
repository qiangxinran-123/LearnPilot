"""Allow practice as a traceable learning evidence source."""

import sqlalchemy as sa
from alembic import op

revision = "0018_m7_5_practice_evidence"
down_revision = "0017_m7_4_practice"
branch_labels = None
depends_on = None

OLD_TYPE = sa.Enum("diagnostic", name="learning_evidence_source_type", native_enum=False, create_constraint=True)
NEW_TYPE = sa.Enum(
    "diagnostic", "practice", name="learning_evidence_source_type", native_enum=False, create_constraint=True
)


def upgrade() -> None:
    with op.batch_alter_table("learning_evidence") as batch:
        batch.alter_column("source_type", existing_type=OLD_TYPE, type_=NEW_TYPE, existing_nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("learning_evidence") as batch:
        batch.alter_column("source_type", existing_type=NEW_TYPE, type_=OLD_TYPE, existing_nullable=False)
