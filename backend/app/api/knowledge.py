from __future__ import annotations

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from backend.app.core.errors import ApiError
from backend.app.schemas.knowledge import (
    KnowledgeBuildJobResponse,
    KnowledgeBuildStatusResponse,
    KnowledgeCanonicalizationRequest,
    KnowledgeCanonicalizationResponse,
    KnowledgeExtractionRequest,
    KnowledgeExtractionResponse,
    KnowledgeModelBuildResponse,
    KnowledgeModelResponse,
    KnowledgeNodeBrowseResponse,
    KnowledgeNodeDetailResponse,
    KnowledgeRelationshipRequest,
    KnowledgeRelationshipsResponse,
)
from backend.app.services.course_knowledge_build_job_service import (
    CourseKnowledgeBuildJobService,
    get_course_knowledge_build_job_service,
    run_course_knowledge_build_job,
)
from backend.app.services.course_knowledge_build_service import (
    CourseKnowledgeBuildError,
    CourseKnowledgeBuildResult,
    CourseKnowledgeBuildService,
    get_course_knowledge_build_service,
)
from backend.app.services.course_service import ResourceNotFoundError
from backend.app.services.knowledge_canonicalization_service import (
    KnowledgeCanonicalizationError,
    KnowledgeCanonicalizationResult,
    KnowledgeCanonicalizationService,
    get_knowledge_canonicalization_service,
)
from backend.app.services.knowledge_extraction_service import (
    KnowledgeExtractionError,
    KnowledgeExtractionResult,
    KnowledgeExtractionService,
    get_knowledge_extraction_service,
)
from backend.app.services.knowledge_model_service import (
    KnowledgeModelError,
    KnowledgeModelService,
    KnowledgeNodeNotFoundError,
    get_knowledge_model_service,
)
from backend.app.services.knowledge_relationship_service import (
    KnowledgeRelationshipError,
    KnowledgeRelationshipResult,
    KnowledgeRelationshipService,
    get_knowledge_relationship_service,
)

router = APIRouter(prefix="/api/courses", tags=["knowledge-model"])


def course_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Course not found")


def extraction_error(error: KnowledgeExtractionError) -> ApiError:
    status_code = {
        "KNOWLEDGE_EXTRACTION_NOT_READY": 409,
        "KNOWLEDGE_EXTRACTION_INVALID_OUTPUT": 422,
        "KNOWLEDGE_EXTRACTION_INVALID_REFERENCE": 422,
        "KNOWLEDGE_EXTRACTION_FAILED": 502,
    }.get(error.code, 400)
    return ApiError(status_code, error.code, error.message)


def extraction_payload(result: KnowledgeExtractionResult) -> dict[str, object]:
    return {
        "run": result.run,
        "candidates": result.candidates,
        "reused": result.reused,
    }


def canonicalization_error(error: KnowledgeCanonicalizationError) -> ApiError:
    status_code = {
        "KNOWLEDGE_CANONICALIZATION_NOT_READY": 409,
        "KNOWLEDGE_CANONICALIZATION_INVALID_OUTPUT": 422,
        "KNOWLEDGE_CANONICALIZATION_FAILED": 502,
    }.get(error.code, 400)
    return ApiError(status_code, error.code, error.message)


def canonicalization_payload(result: KnowledgeCanonicalizationResult) -> dict[str, object]:
    return {
        "run": result.run,
        "nodes": result.nodes,
        "resolutions": result.resolutions,
        "reused": result.reused,
    }


def relationship_error(error: KnowledgeRelationshipError) -> ApiError:
    status_code = {
        "KNOWLEDGE_RELATIONSHIP_NOT_READY": 409,
        "KNOWLEDGE_RELATIONSHIP_INVALID_OUTPUT": 422,
        "KNOWLEDGE_RELATIONSHIP_FAILED": 502,
    }.get(error.code, 400)
    return ApiError(status_code, error.code, error.message)


def relationship_payload(result: KnowledgeRelationshipResult) -> dict[str, object]:
    def edge_payload(edge: object) -> dict[str, object]:
        edge_id = getattr(edge, "id")
        return {
            "id": edge_id,
            "course_id": getattr(edge, "course_id"),
            "source_node_id": getattr(edge, "source_node_id"),
            "target_node_id": getattr(edge, "target_node_id"),
            "relation_type": getattr(edge, "relation_type"),
            "created_at": getattr(edge, "created_at"),
            "updated_at": getattr(edge, "updated_at"),
            "evidence": result.evidence_by_edge_id.get(edge_id, []),
        }

    edges = [edge_payload(edge) for edge in result.edges]
    return {
        "run": result.run,
        "contains_edges": [edge for edge in edges if edge["relation_type"].value == "contains"],
        "prerequisite_edges": [edge for edge in edges if edge["relation_type"].value == "prerequisite"],
        "reused": result.reused,
    }


def knowledge_model_build_error(error: CourseKnowledgeBuildError) -> ApiError:
    status_code = {
        "KNOWLEDGE_MODEL_BUILD_NOT_READY": 409,
        "KNOWLEDGE_MODEL_BUILD_INVALID_OUTPUT": 422,
        "KNOWLEDGE_MODEL_BUILD_FAILED": 502,
    }.get(error.code, 400)
    return ApiError(status_code, error.code, error.message)


def knowledge_model_build_payload(result: CourseKnowledgeBuildResult) -> dict[str, object]:
    return {
        "course_id": result.course_id,
        "material_count": result.material_count,
        "node_count": result.node_count,
        "contains_edge_count": result.contains_edge_count,
        "prerequisite_edge_count": result.prerequisite_edge_count,
        "reused": result.reused,
    }


@router.get("/{course_id}/knowledge-model", response_model=KnowledgeModelResponse)
def get_course_knowledge_model(
    course_id: int,
    service: KnowledgeModelService = Depends(get_knowledge_model_service),
    canonical_only: bool = False,
) -> dict[str, object]:
    try:
        nodes, edges = service.get_knowledge_model(course_id, canonical_only=canonical_only)
    except ResourceNotFoundError as error:
        raise course_not_found() from error
    return {"course_id": course_id, "nodes": nodes, "edges": edges}


@router.get("/{course_id}/knowledge-nodes", response_model=KnowledgeNodeBrowseResponse)
def browse_course_knowledge_nodes(
    course_id: int,
    q: Annotated[str, Query(max_length=100)] = "",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 8,
    service: KnowledgeModelService = Depends(get_knowledge_model_service),
) -> dict[str, object]:
    try:
        total, nodes = service.browse_canonical_nodes(course_id, query=q, offset=offset, limit=limit)
    except ResourceNotFoundError as error:
        raise course_not_found() from error
    return {"course_id": course_id, "total": total, "offset": offset, "limit": limit, "nodes": nodes}


@router.post(
    "/{course_id}/knowledge-model/build",
    response_model=KnowledgeModelBuildResponse,
)
def build_course_knowledge_model(
    course_id: int,
    service: CourseKnowledgeBuildService = Depends(get_course_knowledge_build_service),
) -> dict[str, object]:
    try:
        result = service.build(course_id)
    except ResourceNotFoundError as error:
        raise course_not_found() from error
    except CourseKnowledgeBuildError as error:
        raise knowledge_model_build_error(error) from error
    return knowledge_model_build_payload(result)


@router.post(
    "/{course_id}/knowledge-model/build-jobs",
    response_model=KnowledgeBuildJobResponse,
    status_code=202,
)
def start_course_knowledge_build_job(
    course_id: int,
    background_tasks: BackgroundTasks,
    service: CourseKnowledgeBuildJobService = Depends(get_course_knowledge_build_job_service),
) -> dict[str, object]:
    try:
        job = service.start(course_id)
    except ResourceNotFoundError as error:
        raise course_not_found() from error
    except CourseKnowledgeBuildError as error:
        raise knowledge_model_build_error(error) from error
    if job.should_schedule:
        background_tasks.add_task(run_course_knowledge_build_job, course_id, job.job_id, service.settings)
    return {"job_id": job.job_id, "status": job.status, "stage": job.stage, "reused": job.reused}


@router.get(
    "/{course_id}/knowledge-model/build-status",
    response_model=KnowledgeBuildStatusResponse,
)
def get_course_knowledge_build_status(
    course_id: int,
    service: CourseKnowledgeBuildJobService = Depends(get_course_knowledge_build_job_service),
) -> dict[str, object]:
    try:
        return asdict(service.get_status(course_id))
    except ResourceNotFoundError as error:
        raise course_not_found() from error


@router.get(
    "/{course_id}/knowledge-nodes/{node_id}",
    response_model=KnowledgeNodeDetailResponse,
)
def get_knowledge_node_detail(
    course_id: int,
    node_id: int,
    service: KnowledgeModelService = Depends(get_knowledge_model_service),
) -> dict[str, object]:
    try:
        node, _sources, related_edges = service.get_node_detail(course_id, node_id)
        sources = service.get_verified_source_previews(course_id, node_id)
    except ResourceNotFoundError as error:
        raise course_not_found() from error
    except KnowledgeNodeNotFoundError as error:
        raise ApiError(404, error.code, error.message) from error
    except KnowledgeModelError as error:
        raise ApiError(400, error.code, error.message) from error
    return {
        "node": node,
        "sources": sources,
        "related_edges": related_edges,
    }


@router.post(
    "/{course_id}/materials/{material_id}/knowledge-extraction",
    response_model=KnowledgeExtractionResponse,
)
def extract_material_knowledge(
    course_id: int,
    material_id: int,
    payload: KnowledgeExtractionRequest | None = None,
    service: KnowledgeExtractionService = Depends(get_knowledge_extraction_service),
) -> dict[str, object]:
    try:
        result = service.extract(
            course_id,
            material_id,
            regenerate=payload.regenerate if payload is not None else False,
        )
    except ResourceNotFoundError as error:
        raise HTTPException(status_code=404, detail=f"{error.resource} not found") from error
    except KnowledgeExtractionError as error:
        raise extraction_error(error) from error
    return extraction_payload(result)


@router.get(
    "/{course_id}/materials/{material_id}/knowledge-extraction",
    response_model=KnowledgeExtractionResponse,
)
def get_material_knowledge_extraction(
    course_id: int,
    material_id: int,
    service: KnowledgeExtractionService = Depends(get_knowledge_extraction_service),
) -> dict[str, object]:
    try:
        result = service.get_extraction(course_id, material_id)
    except ResourceNotFoundError as error:
        raise HTTPException(status_code=404, detail=f"{error.resource} not found") from error
    except KnowledgeExtractionError as error:
        raise extraction_error(error) from error
    return extraction_payload(result)


@router.post(
    "/{course_id}/knowledge-canonicalization",
    response_model=KnowledgeCanonicalizationResponse,
)
def canonicalize_course_knowledge(
    course_id: int,
    payload: KnowledgeCanonicalizationRequest | None = None,
    service: KnowledgeCanonicalizationService = Depends(get_knowledge_canonicalization_service),
) -> dict[str, object]:
    try:
        result = service.canonicalize(
            course_id,
            regenerate=payload.regenerate if payload is not None else False,
        )
    except ResourceNotFoundError as error:
        raise course_not_found() from error
    except KnowledgeCanonicalizationError as error:
        raise canonicalization_error(error) from error
    return canonicalization_payload(result)


@router.get(
    "/{course_id}/knowledge-canonicalization",
    response_model=KnowledgeCanonicalizationResponse,
)
def get_course_knowledge_canonicalization(
    course_id: int,
    service: KnowledgeCanonicalizationService = Depends(get_knowledge_canonicalization_service),
) -> dict[str, object]:
    try:
        result = service.get_canonicalization(course_id)
    except ResourceNotFoundError as error:
        raise course_not_found() from error
    except KnowledgeCanonicalizationError as error:
        raise canonicalization_error(error) from error
    return canonicalization_payload(result)


@router.post(
    "/{course_id}/knowledge-relationships",
    response_model=KnowledgeRelationshipsResponse,
)
def generate_course_knowledge_relationships(
    course_id: int,
    payload: KnowledgeRelationshipRequest | None = None,
    service: KnowledgeRelationshipService = Depends(get_knowledge_relationship_service),
) -> dict[str, object]:
    try:
        result = service.generate_relationships(
            course_id,
            regenerate=payload.regenerate if payload is not None else False,
        )
    except ResourceNotFoundError as error:
        raise course_not_found() from error
    except KnowledgeRelationshipError as error:
        raise relationship_error(error) from error
    return relationship_payload(result)


@router.get(
    "/{course_id}/knowledge-relationships",
    response_model=KnowledgeRelationshipsResponse,
)
def get_course_knowledge_relationships(
    course_id: int,
    service: KnowledgeRelationshipService = Depends(get_knowledge_relationship_service),
) -> dict[str, object]:
    try:
        result = service.get_relationships(course_id)
    except ResourceNotFoundError as error:
        raise course_not_found() from error
    except KnowledgeRelationshipError as error:
        raise relationship_error(error) from error
    return relationship_payload(result)
