from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.app.core.errors import ApiError
from backend.app.schemas.knowledge import KnowledgeModelResponse, KnowledgeNodeDetailResponse
from backend.app.services.course_service import ResourceNotFoundError
from backend.app.services.knowledge_model_service import (
    KnowledgeModelError,
    KnowledgeModelService,
    KnowledgeNodeNotFoundError,
    get_knowledge_model_service,
)

router = APIRouter(prefix="/api/courses", tags=["knowledge-model"])


def course_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Course not found")


@router.get("/{course_id}/knowledge-model", response_model=KnowledgeModelResponse)
def get_course_knowledge_model(
    course_id: int,
    service: KnowledgeModelService = Depends(get_knowledge_model_service),
) -> dict[str, object]:
    try:
        nodes, edges = service.get_knowledge_model(course_id)
    except ResourceNotFoundError as error:
        raise course_not_found() from error
    return {"course_id": course_id, "nodes": nodes, "edges": edges}


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
        node, sources, related_edges = service.get_node_detail(course_id, node_id)
    except ResourceNotFoundError as error:
        raise course_not_found() from error
    except KnowledgeNodeNotFoundError as error:
        raise ApiError(404, error.code, error.message) from error
    except KnowledgeModelError as error:
        raise ApiError(400, error.code, error.message) from error
    return {"node": node, "sources": sources, "related_edges": related_edges}
