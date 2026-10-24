from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.app.models import (
    KnowledgeCanonicalizationStatus,
    KnowledgeDifficulty,
    KnowledgeEdgeEvidenceType,
    KnowledgeExtractionStatus,
    KnowledgeImportance,
    KnowledgeRelationshipStatus,
    KnowledgeRelationType,
    KnowledgeResolutionType,
)


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
    material_title: str | None = None
    original_text_excerpt: str | None = None
    original_text_truncated: bool = False
    created_at: datetime


class KnowledgeModelResponse(BaseModel):
    course_id: int
    nodes: list[KnowledgeNodeResponse]
    edges: list[KnowledgeEdgeResponse]


class KnowledgeNodeBrowseResponse(BaseModel):
    course_id: int
    total: int
    offset: int
    limit: int
    nodes: list[KnowledgeNodeResponse]


class KnowledgeModelBuildResponse(BaseModel):
    course_id: int
    material_count: int
    node_count: int
    contains_edge_count: int
    prerequisite_edge_count: int
    added_node_count: int
    reused_node_count: int
    reused: bool


class KnowledgeBuildJobResponse(BaseModel):
    job_id: int
    status: Literal["running", "success"]
    stage: Literal["queued", "extracting", "canonicalizing", "relationships", "complete"] | None
    reused: bool


class KnowledgeBuildStatusResponse(BaseModel):
    course_id: int
    state: Literal[
        "no_materials",
        "not_ready",
        "not_built",
        "running",
        "ready",
        "update_available",
        "failed",
        "update_failed",
    ]
    stage: Literal["queued", "extracting", "canonicalizing", "relationships"] | None
    job_id: int | None
    material_count: int
    ready_material_count: int
    synced_material_count: int
    pending_sync_material_count: int
    pending_parse_material_count: int
    failed_material_count: int
    last_added_node_count: int
    last_reused_node_count: int
    node_count: int
    contains_edge_count: int
    prerequisite_edge_count: int
    needs_update: bool
    can_build: bool
    has_model: bool
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None


class KnowledgeNodeDetailResponse(BaseModel):
    node: KnowledgeNodeResponse
    sources: list[KnowledgeSourceResponse]
    related_edges: list[KnowledgeEdgeResponse]


class KnowledgeExtractionRequest(BaseModel):
    regenerate: bool = False


class KnowledgeExtractionRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    material_id: int
    material_content_hash: str
    status: KnowledgeExtractionStatus
    provider: str
    model: str
    prompt_version: str
    candidate_count: int
    error_code: str | None = None
    error_message: str | None = None
    is_current: bool
    started_at: datetime
    completed_at: datetime | None = None
    created_at: datetime


class KnowledgeCandidateSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    candidate_id: int
    material_id: int
    source_reference: str
    excerpt: str
    created_at: datetime


class KnowledgeCandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    extraction_run_id: int
    course_id: int
    material_id: int
    name: str
    normalized_name: str
    description: str
    importance: KnowledgeImportance
    difficulty: KnowledgeDifficulty
    created_at: datetime
    sources: list[KnowledgeCandidateSourceResponse]


class KnowledgeExtractionResponse(BaseModel):
    run: KnowledgeExtractionRunResponse
    candidates: list[KnowledgeCandidateResponse]
    reused: bool


class KnowledgeCanonicalizationRequest(BaseModel):
    regenerate: bool = False


class KnowledgeCanonicalizationRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    candidate_snapshot_hash: str
    status: KnowledgeCanonicalizationStatus
    provider: str
    model: str
    prompt_version: str
    configuration_version: str
    candidate_count: int
    canonical_node_count: int
    merged_candidate_count: int
    unresolved_count: int
    error_code: str | None = None
    error_message: str | None = None
    is_current: bool
    started_at: datetime
    completed_at: datetime | None = None
    created_at: datetime


class KnowledgeCandidateResolutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    canonicalization_run_id: int
    course_id: int
    candidate_id: int
    knowledge_node_id: int
    resolution_type: KnowledgeResolutionType
    created_at: datetime


class KnowledgeCanonicalizationResponse(BaseModel):
    run: KnowledgeCanonicalizationRunResponse
    nodes: list[KnowledgeNodeResponse]
    resolutions: list[KnowledgeCandidateResolutionResponse]
    reused: bool


class KnowledgeRelationshipRequest(BaseModel):
    regenerate: bool = False


class KnowledgeRelationshipRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    knowledge_snapshot_hash: str
    status: KnowledgeRelationshipStatus
    provider: str
    model: str
    prompt_version: str
    node_count: int
    contains_edge_count: int
    prerequisite_edge_count: int
    rejected_edge_count: int
    error_code: str | None = None
    error_message: str | None = None
    is_current: bool
    started_at: datetime
    completed_at: datetime | None = None
    created_at: datetime


class KnowledgeEdgeEvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    knowledge_edge_id: int
    course_id: int
    material_id: int | None = None
    source_reference: str | None = None
    excerpt: str | None = None
    evidence_type: KnowledgeEdgeEvidenceType
    reason: str
    created_at: datetime


class KnowledgeRelationshipEdgeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    source_node_id: int
    target_node_id: int
    relation_type: KnowledgeRelationType
    created_at: datetime
    updated_at: datetime
    evidence: list[KnowledgeEdgeEvidenceResponse] = Field(default_factory=list)


class KnowledgeRelationshipsResponse(BaseModel):
    run: KnowledgeRelationshipRunResponse
    contains_edges: list[KnowledgeRelationshipEdgeResponse]
    prerequisite_edges: list[KnowledgeRelationshipEdgeResponse]
    reused: bool
