from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.models import EvidenceSourceType, QuestionDifficulty


def _enum_values(enum_type: type) -> list[str]:
    return [member.value for member in enum_type]


class LearningEvidence(Base):
    __tablename__ = "learning_evidence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["source_assessment_id", "source_question_snapshot_id"],
            ["assessment_questions.assessment_id", "assessment_questions.id"],
            ondelete="RESTRICT",
            name="fk_learning_evidence_assessment_question",
        ),
        UniqueConstraint(
            "source_type",
            "source_question_snapshot_id",
            "historical_knowledge_node_ref",
            "evidence_schema_version",
            name="uq_learning_evidence_source_node_version",
        ),
        CheckConstraint(
            "normalized_score >= 0 AND normalized_score <= 1",
            name="ck_learning_evidence_normalized_score",
        ),
        CheckConstraint(
            "attribution_weight > 0 AND attribution_weight <= 1",
            name="ck_learning_evidence_attribution_weight",
        ),
        CheckConstraint(
            "historical_knowledge_node_ref > 0",
            name="ck_learning_evidence_historical_node_ref",
        ),
        CheckConstraint(
            "length(source_scoring_version) > 0",
            name="ck_learning_evidence_source_scoring_version",
        ),
        CheckConstraint(
            "length(evidence_schema_version) > 0",
            name="ck_learning_evidence_schema_version",
        ),
        Index("ix_learning_evidence_course_user", "course_id", "user_id"),
        Index("ix_learning_evidence_source_assessment", "source_assessment_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="RESTRICT"), nullable=False, index=True)
    source_type: Mapped[EvidenceSourceType] = mapped_column(
        Enum(
            EvidenceSourceType,
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=True,
            name="learning_evidence_source_type",
        ),
        nullable=False,
    )
    source_assessment_id: Mapped[int] = mapped_column(ForeignKey("assessments.id", ondelete="RESTRICT"), nullable=False)
    source_question_snapshot_id: Mapped[int] = mapped_column(nullable=False)
    source_response_id: Mapped[int] = mapped_column(
        ForeignKey("responses.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    historical_knowledge_node_ref: Mapped[int] = mapped_column(nullable=False)
    current_knowledge_node_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_nodes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    knowledge_model_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    normalized_score: Mapped[Decimal] = mapped_column(Numeric(6, 5), nullable=False)
    difficulty: Mapped[QuestionDifficulty] = mapped_column(
        Enum(
            QuestionDifficulty,
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=True,
            name="learning_evidence_difficulty",
        ),
        nullable=False,
    )
    attribution_weight: Mapped[Decimal] = mapped_column(Numeric(6, 5), nullable=False)
    source_scoring_version: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_schema_version: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
