"""Create M2 parsed-content and AI artifact persistence.

M1 persisted only a bounded extracted-text copy and unstructured mock artifacts.
Backfill recoverable data with explicit legacy provenance; never treat a preview
as the complete document or label a legacy mock as a real model response.
"""

import hashlib
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.mysql import LONGTEXT

revision = "0002_m2_course_material_ai"
down_revision = "0001_m1a_foundation"
branch_labels = None
depends_on = None

LEGACY_MODEL_PROVIDER = "legacy-mock"
LEGACY_MODEL_NAME = "campusai-m1"
LEGACY_PROMPT_VERSION = "legacy_m1_mock"


def _optional_text(value: object, max_length: int | None = None) -> str | None:
    if not isinstance(value, str):
        return None
    result = value.strip()
    if not result:
        return None
    return result[:max_length] if max_length is not None else result


def _backfill_legacy_materials() -> None:
    connection = op.get_bind()
    metadata = sa.MetaData()
    materials = sa.Table("materials", metadata, autoload_with=connection)
    contents = sa.Table("material_contents", metadata, autoload_with=connection)
    summaries = sa.Table("material_summaries", metadata, autoload_with=connection)
    cards = sa.Table("study_cards", metadata, autoload_with=connection)
    now = datetime.now(timezone.utc)

    for row in connection.execute(sa.select(materials)).mappings().all():
        material_id = row["id"]
        raw_text = row["extracted_text"]
        text = raw_text if isinstance(raw_text, str) and raw_text.strip() else None
        if text is not None:
            saved_length = row["text_length"] or len(text)
            partial = saved_length > len(text)
            connection.execute(
                sa.insert(contents).values(
                    material_id=material_id,
                    plain_text=text,
                    segments=[{"text": text, "source_reference": "旧版提取文本"}],
                    content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    parser_name="m1-legacy-partial" if partial else "m1-legacy",
                    parser_version="m1-backfill-v1",
                    page_count=0,
                    created_at=row["created_at"] or now,
                    updated_at=now,
                )
            )
            connection.execute(
                sa.update(materials)
                .where(materials.c.id == material_id)
                .values(
                    extraction_status="LEGACY_CONTENT_PARTIAL" if partial else "SUCCESS",
                    text_extracted=not partial,
                    extraction_error_code="LEGACY_TEXT_TRUNCATED" if partial else None,
                    extraction_error_message=(
                        "Only the M1 saved text excerpt is available; re-upload the original file." if partial else None
                    ),
                )
            )
        elif row["text_extracted"]:
            connection.execute(
                sa.update(materials)
                .where(materials.c.id == material_id)
                .values(
                    extraction_status="LEGACY_CONTENT_UNAVAILABLE",
                    text_extracted=False,
                    extraction_error_code="LEGACY_CONTENT_UNAVAILABLE",
                    extraction_error_message=("M1 did not save extracted text; re-upload the original file."),
                )
            )

        legacy_summary = _optional_text(row["ai_summary"])
        if legacy_summary is not None:
            generated_at = row["summary_updated_at"] or row["updated_at"] or now
            connection.execute(
                sa.insert(summaries).values(
                    material_id=material_id,
                    overview=legacy_summary,
                    key_concepts=[],
                    important_points=[],
                    common_mistakes=[],
                    review_suggestions=[],
                    model_provider=LEGACY_MODEL_PROVIDER,
                    model_name=LEGACY_MODEL_NAME,
                    prompt_version=LEGACY_PROMPT_VERSION,
                    created_at=generated_at,
                    updated_at=generated_at,
                )
            )

        legacy_cards = row["cards"]
        if isinstance(legacy_cards, list):
            generated_at = row["cards_generated_at"] or row["updated_at"] or now
            order_index = 0
            for legacy_card in legacy_cards:
                if not isinstance(legacy_card, dict):
                    continue
                question = _optional_text(legacy_card.get("question"))
                answer = _optional_text(legacy_card.get("answer"))
                if question is None or answer is None:
                    continue
                order_index += 1
                connection.execute(
                    sa.insert(cards).values(
                        material_id=material_id,
                        question=question,
                        answer=answer,
                        knowledge_hint=_optional_text(legacy_card.get("knowledge_hint"), 500),
                        source_reference=_optional_text(legacy_card.get("source_reference"), 255),
                        order_index=order_index,
                        model_provider=LEGACY_MODEL_PROVIDER,
                        model_name=LEGACY_MODEL_NAME,
                        prompt_version=LEGACY_PROMPT_VERSION,
                        created_at=generated_at,
                        updated_at=generated_at,
                    )
                )


def upgrade() -> None:
    op.create_table(
        "material_contents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("plain_text", sa.Text().with_variant(LONGTEXT(), "mysql"), nullable=False),
        sa.Column("segments", sa.JSON(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("parser_name", sa.String(length=80), nullable=False),
        sa.Column("parser_version", sa.String(length=32), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("material_id", name="uq_material_contents_material_id"),
    )
    op.create_index("ix_material_contents_material_id", "material_contents", ["material_id"], unique=False)
    op.create_index("ix_material_contents_content_hash", "material_contents", ["content_hash"], unique=False)

    op.create_table(
        "material_summaries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("overview", sa.Text(), nullable=False),
        sa.Column("key_concepts", sa.JSON(), nullable=False),
        sa.Column("important_points", sa.JSON(), nullable=False),
        sa.Column("common_mistakes", sa.JSON(), nullable=False),
        sa.Column("review_suggestions", sa.JSON(), nullable=False),
        sa.Column("model_provider", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=160), nullable=False),
        sa.Column("prompt_version", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("material_id", name="uq_material_summaries_material_id"),
    )
    op.create_index("ix_material_summaries_material_id", "material_summaries", ["material_id"], unique=False)

    op.create_table(
        "study_cards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("knowledge_hint", sa.String(length=500), nullable=True),
        sa.Column("source_reference", sa.String(length=255), nullable=True),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("model_provider", sa.String(length=80), nullable=False),
        sa.Column("model_name", sa.String(length=160), nullable=False),
        sa.Column("prompt_version", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["material_id"], ["materials.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("material_id", "order_index", name="uq_study_cards_material_order"),
    )
    op.create_index("ix_study_cards_material_id", "study_cards", ["material_id"], unique=False)
    _backfill_legacy_materials()


def downgrade() -> None:
    op.drop_index("ix_study_cards_material_id", table_name="study_cards")
    op.drop_table("study_cards")
    op.drop_index("ix_material_summaries_material_id", table_name="material_summaries")
    op.drop_table("material_summaries")
    op.drop_index("ix_material_contents_content_hash", table_name="material_contents")
    op.drop_index("ix_material_contents_material_id", table_name="material_contents")
    op.drop_table("material_contents")
