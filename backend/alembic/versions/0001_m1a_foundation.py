"""Create M1-A relational ownership and material foundation."""

import sqlalchemy as sa
from alembic import op

revision = "0001_m1a_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=False)
    op.create_table(
        "courses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=True),
        sa.Column("learning_goal", sa.Text(), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("legacy_key", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("legacy_key", name="uq_courses_legacy_key"),
    )
    op.create_index("ix_courses_owner_id", "courses", ["owner_id"], unique=False)
    op.create_table(
        "materials",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("course_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("material_type", sa.String(length=50), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=True),
        sa.Column("storage_key", sa.String(length=512), nullable=True),
        sa.Column("storage_status", sa.String(length=32), nullable=False),
        sa.Column("media_type", sa.String(length=127), nullable=True),
        sa.Column("extension", sa.String(length=16), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("text_extracted", sa.Boolean(), nullable=False),
        sa.Column("text_preview", sa.Text(), nullable=False),
        sa.Column("text_length", sa.Integer(), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=True),
        sa.Column("extraction_status", sa.String(length=32), nullable=False),
        sa.Column("extraction_error_code", sa.String(length=64), nullable=True),
        sa.Column("extraction_error_message", sa.String(length=255), nullable=True),
        sa.Column("ai_summary", sa.Text(), nullable=True),
        sa.Column("summary_generated", sa.Boolean(), nullable=True),
        sa.Column("summary_method", sa.String(length=32), nullable=True),
        sa.Column("summary_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cards", sa.JSON(), nullable=True),
        sa.Column("cards_generated", sa.Boolean(), nullable=True),
        sa.Column("cards_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cards_method", sa.String(length=32), nullable=True),
        sa.Column("legacy_key", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("storage_key", name="uq_materials_storage_key"),
        sa.UniqueConstraint("legacy_key", name="uq_materials_legacy_key"),
    )
    op.create_index("ix_materials_course_id", "materials", ["course_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_materials_course_id", table_name="materials")
    op.drop_table("materials")
    op.drop_index("ix_courses_owner_id", table_name="courses")
    op.drop_table("courses")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
