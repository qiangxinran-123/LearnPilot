from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from backend.app.models import LearningSessionTaskPhase


class LearningContentStatus(StrEnum):
    READY = "ready"
    EMPTY = "empty"


class LearningContentRelevance(StrEnum):
    DIRECT = "direct"
    SUPPLEMENTAL = "supplemental"


class LearningContentSegmentRead(BaseModel):
    material_id: int = Field(gt=0)
    material_title: str = Field(min_length=1, max_length=255)
    material_type: str = Field(min_length=1, max_length=50)
    segment_index: int = Field(ge=0)
    fragment_index: int = Field(ge=0)
    text: str = Field(min_length=1)
    source_reference: str = Field(min_length=1, max_length=255)
    relevance: LearningContentRelevance
    content_hash: str = Field(min_length=64, max_length=64)
    text_truncated: bool


class LearningContentLimits(BaseModel):
    max_segments: int = Field(gt=0)
    max_segment_chars: int = Field(gt=0)
    max_total_chars: int = Field(gt=0)
    max_segments_per_material: int = Field(gt=0)


class LearningContentRead(BaseModel):
    session_id: int = Field(gt=0)
    course_id: int = Field(gt=0)
    knowledge_node_id: int = Field(gt=0)
    knowledge_node_name: str = Field(min_length=1, max_length=255)
    knowledge_node_description: str
    phase: LearningSessionTaskPhase
    status: LearningContentStatus
    grounded: bool
    segments: list[LearningContentSegmentRead]
    limits: LearningContentLimits


__all__ = [
    "LearningContentLimits",
    "LearningContentRead",
    "LearningContentRelevance",
    "LearningContentSegmentRead",
    "LearningContentStatus",
]
