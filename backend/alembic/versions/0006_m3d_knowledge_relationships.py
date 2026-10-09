"""Create the M3-D knowledge relationship and evidence schema."""

import sqlalchemy as sa
from alembic import op

revision = "0006_m3d_relationships"
down_revision = "0005_m3c_canonicalization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_relationship_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_snapshot_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "success",
                "failed",
                name="knowledge_relationship_status",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("prompt_version", sa.String(length=80), nullable=False),
        sa.Column("node_count", sa.Integer(), nullable=False),
        sa.Column("contains_edge_count", sa.Integer(), nullable=False),
        sa.Column("prerequisite_edge_count", sa.Integer(), nullable=False),
        sa.Column("rejected_edge_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=255), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("node_count >= 0", name="ck_knowledge_relationship_runs_node_count"),
        sa.CheckConstraint(
            "contains_edge_count >= 0",
            name="ck_knowledge_relationship_runs_contains_count",
        ),
        sa.CheckConstraint(
            "prerequisite_edge_count >= 0",
            name="ck_knowledge_relationship_runs_prerequisite_count",
        ),
        sa.CheckConstraint(
            "rejected_edge_count >= 0",
            name="ck_knowledge_relationship_runs_rejected_count",
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("id", "course_id", name="uq_knowledge_relationship_runs_id_course"),
    )
    op.create_index(
        "ix_knowledge_relationship_runs_course_id",
        "knowledge_relationship_runs",
        ["course_id"],
    )
    op.create_index(
        "ix_knowledge_relationship_runs_idempotency",
        "knowledge_relationship_runs",
        ["course_id", "knowledge_snapshot_hash", "prompt_version", "model"],
    )
    op.create_index(
        "ix_knowledge_relationship_runs_course_current",
        "knowledge_relationship_runs",
        ["course_id", "is_current"],
    )

    with op.batch_alter_table("knowledge_edges") as batch_op:
        batch_op.add_column(sa.Column("relationship_run_id", sa.Integer(), nullable=True))
        batch_op.create_unique_constraint(
            "uq_knowledge_edges_id_course",
            ["id", "course_id"],
        )
        batch_op.create_foreign_key(
            "fk_knowledge_edges_relationship_run_course",
            "knowledge_relationship_runs",
            ["course_id", "relationship_run_id"],
            ["course_id", "id"],
            ondelete="CASCADE",
        )
        batch_op.create_index(
            "ix_knowledge_edges_relationship_run_id",
            ["relationship_run_id"],
            unique=False,
        )

    op.create_table(
        "knowledge_edge_evidences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("knowledge_edge_id", sa.Integer(), nullable=False),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=True),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("excerpt", sa.String(length=1000), nullable=True),
        sa.Column(
            "evidence_type",
            sa.Enum(
                "material",
                "model_inference",
                "structural",
                name="knowledge_edge_evidence_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["knowledge_edge_id", "course_id"],
            ["knowledge_edges.id", "knowledge_edges.course_id"],
            ondelete="CASCADE",
            name="fk_knowledge_edge_evidences_edge_course",
        ),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_knowledge_edge_evidences_edge_id",
        "knowledge_edge_evidences",
        ["knowledge_edge_id"],
    )
    op.create_index(
        "ix_knowledge_edge_evidences_course_id",
        "knowledge_edge_evidences",
        ["course_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_knowledge_edge_evidences_course_id", table_name="knowledge_edge_evidences")
    op.drop_index("ix_knowledge_edge_evidences_edge_id", table_name="knowledge_edge_evidences")
    op.drop_table("knowledge_edge_evidences")

    with op.batch_alter_table("knowledge_edges") as batch_op:
        batch_op.drop_index("ix_knowledge_edges_relationship_run_id")
        batch_op.drop_constraint("fk_knowledge_edges_relationship_run_course", type_="foreignkey")
        batch_op.drop_constraint("uq_knowledge_edges_id_course", type_="unique")
        batch_op.drop_column("relationship_run_id")

    op.drop_index(
        "ix_knowledge_relationship_runs_course_current",
        table_name="knowledge_relationship_runs",
    )
    op.drop_index(
        "ix_knowledge_relationship_runs_idempotency",
        table_name="knowledge_relationship_runs",
    )
    op.drop_index(
        "ix_knowledge_relationship_runs_course_id",
        table_name="knowledge_relationship_runs",
    )
    op.drop_table("knowledge_relationship_runs")
