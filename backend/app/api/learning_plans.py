from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.core.errors import ApiError
from backend.app.schemas.learning_plan import LearningPlanResponse
from backend.app.services.learning_plan_service import (
    LearningPlanError,
    LearningPlanService,
    get_learning_plan_service,
)

router = APIRouter(prefix="/api/courses", tags=["learning-plans"])


def _api_error(error: LearningPlanError) -> ApiError:
    if error.code in {"USER_NOT_FOUND", "COURSE_NOT_FOUND", "RECOMMENDED_NODE_NOT_FOUND"}:
        status = 404
    elif error.code == "LEARNING_PLAN_CONFLICT":
        status = 409
    else:
        status = 422
    return ApiError(status, error.code, error.message)


@router.get("/{course_id}/learning-plan", response_model=LearningPlanResponse)
def get_learning_plan(
    course_id: int,
    service: LearningPlanService = Depends(get_learning_plan_service),
) -> LearningPlanResponse:
    try:
        return service.get_current_for_configured_user(course_id)
    except LearningPlanError as error:
        raise _api_error(error) from error


@router.post("/{course_id}/learning-plan/generate", response_model=LearningPlanResponse)
def generate_learning_plan(
    course_id: int,
    service: LearningPlanService = Depends(get_learning_plan_service),
) -> LearningPlanResponse:
    try:
        return service.generate_for_configured_user(course_id)
    except LearningPlanError as error:
        raise _api_error(error) from error


__all__ = ["router"]
