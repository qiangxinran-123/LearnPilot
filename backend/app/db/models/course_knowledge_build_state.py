from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class CourseKnowledgeBuildState(Base):
    """One durable build claim and last successful material snapshot per course."""

    __tablename__ = "course_knowledge_build_states"
    __table_args__ = (CheckConstraint("job_id >= 0", name="ck_course_knowledge_build_job_id"),)

    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), primary_key=True)
    job_id: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="idle", nullable=False)
    stage: Mapped[str | None] = mapped_column(String(24), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(255), nullable=True)
    requested_material_snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    success_material_snapshot_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_added_node_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_reused_node_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checkpoint_json: Mapped[str | None] = mapped_column(Text().with_variant(LONGTEXT(), "mysql"), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
