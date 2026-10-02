from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.ai import AIServiceError
from backend.app.core.errors import ApiError
from backend.app.schemas.course import (
    CardGenerationResponse,
    Material,
    MaterialContentResponse,
    MaterialQARequest,
    MaterialQAResponse,
    MaterialSearchResponse,
    MaterialSummaryResponse,
)
from backend.app.services.course_service import (
    CourseService,
    MaterialNotParsedError,
    ResourceNotFoundError,
    get_course_service,
    serialize_material,
    serialize_study_card,
)
from backend.app.services.material_ai_service import (
    MaterialAIService,
    get_material_ai_service,
    serialize_summary,
)
from backend.app.storage import StorageError

router = APIRouter(prefix="/api/materials", tags=["materials"])


def course_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Course not found")


def material_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Material not found")


def translate_ai_error(error: AIServiceError) -> ApiError:
    transient_codes = {"AI_TIMEOUT", "AI_PROVIDER_ERROR"}
    if error.code == "AI_RATE_LIMITED":
        status_code = 429
    elif error.code in transient_codes:
        status_code = 503
    else:
        status_code = 400
    return ApiError(status_code, error.code, error.message)


@router.get("/search", response_model=MaterialSearchResponse)
def search_course_materials(
    q: str | None = Query(default=None),
    course_id: int | None = Query(default=None),
    service: CourseService = Depends(get_course_service),
) -> dict[str, object]:
    if q is None or not q.strip():
        raise ApiError(400, "EMPTY_SEARCH_QUERY", "Search keyword must not be empty")
    try:
        materials = service.search_materials(q, course_id)
    except ResourceNotFoundError as error:
        raise course_not_found() from error
    return {
        "query": q,
        "course_id": course_id,
        "count": len(materials),
        "materials": [serialize_material(material) for material in materials],
    }


@router.get("/{material_id}", response_model=Material, response_model_exclude_none=True)
def get_material(material_id: int, service: CourseService = Depends(get_course_service)) -> dict[str, object]:
    try:
        return serialize_material(service.get_material(material_id))
    except ResourceNotFoundError as error:
        raise material_not_found() from error


@router.delete("/{material_id}")
def delete_material(material_id: int, service: CourseService = Depends(get_course_service)) -> dict[str, object]:
    try:
        service.delete_material(material_id)
    except ResourceNotFoundError as error:
        raise material_not_found() from error
    except StorageError as error:
        raise ApiError(500, "STORAGE_FAILURE", str(error)) from error
    return {"id": material_id, "deleted": True}


@router.get("/{material_id}/content", response_model=MaterialContentResponse)
def get_material_content(
    material_id: int,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=12_000, ge=500, le=20_000),
    service: CourseService = Depends(get_course_service),
) -> dict[str, object]:
    try:
        content = service.get_content(material_id)
    except ResourceNotFoundError as error:
        raise material_not_found() from error
    except MaterialNotParsedError as error:
        raise ApiError(400, "MATERIAL_NOT_PARSED", str(error)) from error
    text = content.plain_text[offset : offset + limit]
    return {
        "material_id": material_id,
        "text": text,
        "offset": offset,
        "limit": limit,
        "total_length": len(content.plain_text),
        "has_more": offset + len(text) < len(content.plain_text),
        "page_count": content.page_count,
        "parser_name": content.parser_name,
        "parser_version": content.parser_version,
    }


@router.get("/{material_id}/summary", response_model=MaterialSummaryResponse)
def get_material_summary(
    material_id: int, service: MaterialAIService = Depends(get_material_ai_service)
) -> dict[str, object]:
    try:
        return serialize_summary(service.get_summary(material_id), material_id)
    except ResourceNotFoundError as error:
        raise material_not_found() from error


@router.post("/{material_id}/summary", response_model=MaterialSummaryResponse)
def generate_material_summary(
    material_id: int, service: MaterialAIService = Depends(get_material_ai_service)
) -> dict[str, object]:
    try:
        return serialize_summary(service.generate_summary(material_id), material_id)
    except ResourceNotFoundError as error:
        raise material_not_found() from error
    except MaterialNotParsedError as error:
        raise ApiError(400, "MATERIAL_NOT_PARSED", str(error)) from error
    except AIServiceError as error:
        raise translate_ai_error(error) from error


@router.get("/{material_id}/cards", response_model=CardGenerationResponse)
def get_material_cards(
    material_id: int, service: MaterialAIService = Depends(get_material_ai_service)
) -> dict[str, object]:
    try:
        cards = service.get_cards(material_id)
    except ResourceNotFoundError as error:
        raise material_not_found() from error
    return {
        "material_id": material_id,
        "count": len(cards),
        "cards": [serialize_study_card(card) for card in cards],
        "cards_generated": bool(cards),
        "cards_generated_at": cards[0].updated_at if cards else None,
        "cards_method": cards[0].model_provider if cards else None,
    }


@router.post("/{material_id}/cards", response_model=CardGenerationResponse)
def generate_material_cards(
    material_id: int, service: MaterialAIService = Depends(get_material_ai_service)
) -> dict[str, object]:
    try:
        cards = service.generate_cards(material_id)
    except ResourceNotFoundError as error:
        raise material_not_found() from error
    except MaterialNotParsedError as error:
        raise ApiError(400, "MATERIAL_NOT_PARSED", str(error)) from error
    except AIServiceError as error:
        raise translate_ai_error(error) from error
    return {
        "material_id": material_id,
        "count": len(cards),
        "cards": [serialize_study_card(card) for card in cards],
        "cards_generated": True,
        "cards_generated_at": cards[0].updated_at if cards else None,
        "cards_method": cards[0].model_provider if cards else None,
    }


@router.post("/{material_id}/qa", response_model=MaterialQAResponse)
def material_qa(
    material_id: int,
    payload: MaterialQARequest,
    service: MaterialAIService = Depends(get_material_ai_service),
) -> MaterialQAResponse:
    try:
        return service.answer_question(material_id, payload.question)
    except ResourceNotFoundError as error:
        raise material_not_found() from error
    except MaterialNotParsedError as error:
        raise ApiError(400, "MATERIAL_NOT_PARSED", str(error)) from error
    except AIServiceError as error:
        raise translate_ai_error(error) from error
