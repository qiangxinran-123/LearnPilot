from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class MasteryHistory(Base):
    __tablename__ = "mastery_history"
    __table_args__ = (
        ForeignKeyConstraint(
            ["course_id", "knowledge_node_id"],
            ["knowledge_nodes.course_id", "knowledge_nodes.id"],
            ondelete="CASCADE",
            name="fk_mastery_history_course_node",
        ),
        UniqueConstraint(
            "user_id",
            "course_id",
            "knowledge_node_id",
            "algorithm_version",
            "evidence_fingerprint",
            name="uq_mastery_history_version",
        ),
        CheckConstraint(
            "mastery_score IS NULL OR (mastery_score >= 0 AND mastery_score <= 100)", name="ck_mastery_history_score"
        ),
        Index("ix_mastery_history_course_user_time", "course_id", "user_id", "recorded_at", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    knowledge_node_id: Mapped[int] = mapped_column(nullable=False)
    mastery_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    mastery_status: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence_level: Mapped[str] = mapped_column(String(32), nullable=False)
    evidence_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    graph_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
