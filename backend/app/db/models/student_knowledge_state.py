from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
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
from backend.app.models import ConfidenceLevel, MasteryStatus


def _enum_values(enum_type: type) -> list[str]:
    return [member.value for member in enum_type]


class StudentKnowledgeState(Base):
    __tablename__ = "student_knowledge_states"
    __table_args__ = (
        ForeignKeyConstraint(
            ["course_id", "knowledge_node_id"],
            ["knowledge_nodes.course_id", "knowledge_nodes.id"],
            ondelete="CASCADE",
            name="fk_student_knowledge_state_course_node",
        ),
        UniqueConstraint(
            "user_id",
            "course_id",
            "knowledge_node_id",
            name="uq_student_knowledge_state_identity",
        ),
        CheckConstraint(
            "mastery_score IS NULL OR (mastery_score >= 0 AND mastery_score <= 100)",
            name="ck_student_knowledge_state_mastery_score",
        ),
        CheckConstraint("evidence_count >= 0", name="ck_student_knowledge_state_evidence_count"),
        CheckConstraint(
            "independent_evidence_count >= 0 AND independent_evidence_count <= evidence_count",
            name="ck_student_knowledge_state_independent_count",
        ),
        CheckConstraint(
            "assessment_count >= 0 AND assessment_count <= independent_evidence_count",
            name="ck_student_knowledge_state_assessment_count",
        ),
        CheckConstraint("length(algorithm_version) > 0", name="ck_student_knowledge_state_algorithm_version"),
        CheckConstraint("length(evidence_fingerprint) = 64", name="ck_student_knowledge_state_fingerprint"),
        Index("ix_student_knowledge_state_course_user", "course_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    knowledge_node_id: Mapped[int] = mapped_column(nullable=False, index=True)
    knowledge_model_version: Mapped[str | None] = mapped_column(String(120), nullable=True)
    mastery_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    mastery_status: Mapped[MasteryStatus] = mapped_column(
        Enum(
            MasteryStatus,
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=True,
            name="mastery_status",
        ),
        nullable=False,
    )
    confidence_level: Mapped[ConfidenceLevel] = mapped_column(
        Enum(
            ConfidenceLevel,
            values_callable=_enum_values,
            native_enum=False,
            create_constraint=True,
            name="confidence_level",
        ),
        nullable=False,
    )
    confidence_reason_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    evidence_count: Mapped[int] = mapped_column(nullable=False)
    independent_evidence_count: Mapped[int] = mapped_column(nullable=False)
    assessment_count: Mapped[int] = mapped_column(nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
