from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.models import KnowledgeDifficulty, KnowledgeImportance, KnowledgeRelationType


class KnowledgeNodeCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)
    importance: KnowledgeImportance = KnowledgeImportance.MEDIUM
    difficulty: KnowledgeDifficulty = KnowledgeDifficulty.INTERMEDIATE

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Knowledge node name must not be blank.")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str) -> str:
        return value.strip()


class KnowledgeNodeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    importance: KnowledgeImportance | None = None
    difficulty: KnowledgeDifficulty | None = None

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("Knowledge node name must not be null.")
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Knowledge node name must not be blank.")
        return normalized

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str:
        return "" if value is None else value.strip()


class KnowledgeEdgeCreate(BaseModel):
    source_node_id: int = Field(gt=0)
    target_node_id: int = Field(gt=0)
    relation_type: KnowledgeRelationType


class KnowledgeSourceCreate(BaseModel):
    material_id: int = Field(gt=0)
    source_reference: str = Field(min_length=1, max_length=255)
    excerpt: str | None = Field(default=None, max_length=1000)

    @field_validator("source_reference")
    @classmethod
    def normalize_source_reference(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Knowledge source reference must not be blank.")
        return normalized

    @field_validator("excerpt")
    @classmethod
    def normalize_excerpt(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class KnowledgeNodeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    name: str
    normalized_name: str
    description: str
    importance: KnowledgeImportance
    difficulty: KnowledgeDifficulty
    created_at: datetime
    updated_at: datetime


class KnowledgeEdgeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    source_node_id: int
    target_node_id: int
    relation_type: KnowledgeRelationType
    created_at: datetime
    updated_at: datetime


class KnowledgeSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    knowledge_node_id: int
    material_id: int
    source_reference: str
    excerpt: str | None = None
    created_at: datetime


class KnowledgeModelResponse(BaseModel):
    course_id: int
    nodes: list[KnowledgeNodeResponse]
    edges: list[KnowledgeEdgeResponse]


class KnowledgeNodeDetailResponse(BaseModel):
    node: KnowledgeNodeResponse
    sources: list[KnowledgeSourceResponse]
    related_edges: list[KnowledgeEdgeResponse]
