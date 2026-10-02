"""Create the M3-A course knowledge model foundation."""

import sqlalchemy as sa
from alembic import op

revision = "0003_m3a_knowledge_model"
down_revision = "0002_m2_course_material_ai"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_nodes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("normalized_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "importance",
            sa.Enum(
                "low",
                "medium",
                "high",
                name="knowledge_importance",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column(
            "difficulty",
            sa.Enum(
                "basic",
                "intermediate",
                "advanced",
                name="knowledge_difficulty",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("course_id", "id", name="uq_knowledge_nodes_course_id_id"),
    )
    op.create_index("ix_knowledge_nodes_course_id", "knowledge_nodes", ["course_id"], unique=False)
    op.create_index(
        "ix_knowledge_nodes_course_normalized_name",
        "knowledge_nodes",
        ["course_id", "normalized_name"],
        unique=False,
    )

    op.create_table(
        "knowledge_edges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("source_node_id", sa.Integer(), nullable=False),
        sa.Column("target_node_id", sa.Integer(), nullable=False),
        sa.Column(
            "relation_type",
            sa.Enum(
                "contains",
                "prerequisite",
                name="knowledge_relation_type",
                native_enum=False,
                create_constraint=True,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source_node_id <> target_node_id", name="ck_knowledge_edges_no_self_edge"),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["course_id", "source_node_id"],
            ["knowledge_nodes.course_id", "knowledge_nodes.id"],
            ondelete="CASCADE",
            name="fk_knowledge_edges_source_in_course",
        ),
        sa.ForeignKeyConstraint(
            ["course_id", "target_node_id"],
            ["knowledge_nodes.course_id", "knowledge_nodes.id"],
            ondelete="CASCADE",
            name="fk_knowledge_edges_target_in_course",
        ),
        sa.UniqueConstraint(
            "course_id",
            "source_node_id",
            "target_node_id",
            "relation_type",
            name="uq_knowledge_edges_course_source_target_relation",
        ),
    )
    op.create_index("ix_knowledge_edges_course_id", "knowledge_edges", ["course_id"], unique=False)
    op.create_index("ix_knowledge_edges_source_node_id", "knowledge_edges", ["source_node_id"], unique=False)
    op.create_index("ix_knowledge_edges_target_node_id", "knowledge_edges", ["target_node_id"], unique=False)

    op.create_table(
        "knowledge_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("knowledge_node_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("source_reference", sa.String(length=255), nullable=False),
        sa.Column("excerpt", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["knowledge_node_id"], ["knowledge_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "knowledge_node_id",
            "material_id",
            "source_reference",
            name="uq_knowledge_sources_node_material_reference",
        ),
    )
    op.create_index(
        "ix_knowledge_sources_knowledge_node_id", "knowledge_sources", ["knowledge_node_id"], unique=False
    )
    op.create_index("ix_knowledge_sources_material_id", "knowledge_sources", ["material_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_knowledge_sources_material_id", table_name="knowledge_sources")
    op.drop_index("ix_knowledge_sources_knowledge_node_id", table_name="knowledge_sources")
    op.drop_table("knowledge_sources")
    op.drop_index("ix_knowledge_edges_target_node_id", table_name="knowledge_edges")
    op.drop_index("ix_knowledge_edges_source_node_id", table_name="knowledge_edges")
    op.drop_index("ix_knowledge_edges_course_id", table_name="knowledge_edges")
    op.drop_table("knowledge_edges")
    op.drop_index("ix_knowledge_nodes_course_normalized_name", table_name="knowledge_nodes")
    op.drop_index("ix_knowledge_nodes_course_id", table_name="knowledge_nodes")
    op.drop_table("knowledge_nodes")
