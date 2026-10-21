"""Add the optional current-node mapping for M5-B evidence."""

import sqlalchemy as sa
from alembic import op

revision = "0011_m5b_evidence_mapping"
down_revision = "0010_m5a_learning_evidence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("learning_evidence") as batch_op:
        batch_op.add_column(sa.Column("current_knowledge_node_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_learning_evidence_current_knowledge_node",
            "knowledge_nodes",
            ["current_knowledge_node_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index(
            "ix_learning_evidence_current_knowledge_node_id",
            ["current_knowledge_node_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("learning_evidence") as batch_op:
        batch_op.drop_index("ix_learning_evidence_current_knowledge_node_id")
        batch_op.drop_constraint("fk_learning_evidence_current_knowledge_node", type_="foreignkey")
        batch_op.drop_column("current_knowledge_node_id")
