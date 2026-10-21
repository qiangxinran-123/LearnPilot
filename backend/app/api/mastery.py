from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from backend.app.core.errors import ApiError
from backend.app.schemas.mastery_api import (
    CourseMasteryReadSchema,
    KnowledgeEvidenceExplanationSchema,
    KnowledgeNodeMasteryReadSchema,
)
from backend.app.services.mastery_read_service import (
    MasteryReadError,
    MasteryReadService,
    get_mastery_read_service,
)

router = APIRouter(prefix="/api/courses", tags=["mastery"])


def _api_error(error: MasteryReadError) -> ApiError:
    status = 404 if error.code in {"COURSE_NOT_FOUND", "KNOWLEDGE_NODE_NOT_FOUND"} else 409
    return ApiError(status, error.code, error.message)


@router.get("/{course_id}/mastery", response_model=CourseMasteryReadSchema)
def get_course_mastery(
    course_id: int,
    service: MasteryReadService = Depends(get_mastery_read_service),
) -> CourseMasteryReadSchema:
    try:
        return service.course_mastery(course_id)
    except MasteryReadError as error:
        raise _api_error(error) from error


@router.get("/{course_id}/knowledge/{node_id}/mastery", response_model=KnowledgeNodeMasteryReadSchema)
def get_node_mastery(
    course_id: int,
    node_id: int,
    service: MasteryReadService = Depends(get_mastery_read_service),
) -> KnowledgeNodeMasteryReadSchema:
    try:
        return service.node_mastery(course_id, node_id)
    except MasteryReadError as error:
        raise _api_error(error) from error


@router.get("/{course_id}/knowledge/{node_id}/evidence", response_model=KnowledgeEvidenceExplanationSchema)
def get_node_evidence(
    course_id: int,
    node_id: int,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    service: MasteryReadService = Depends(get_mastery_read_service),
) -> KnowledgeEvidenceExplanationSchema:
    try:
        return service.node_evidence(course_id, node_id, offset=offset, limit=limit)
    except MasteryReadError as error:
        raise _api_error(error) from error


__all__ = ["router"]
