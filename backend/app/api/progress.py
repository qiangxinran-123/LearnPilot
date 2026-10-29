from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.app.core.errors import ApiError
from backend.app.core.settings import Settings, get_settings
from backend.app.db.session import get_db
from backend.app.schemas.progress import ProgressKnowledge, ProgressOverview
from backend.app.schemas.progress_history import LearningHistoryPage
from backend.app.schemas.progress_trend import ProgressTrend
from backend.app.schemas.review_risk import ReviewRiskResponse
from backend.app.services.learning_history_service import LearningHistoryService
from backend.app.services.mastery_read_service import MasteryReadError
from backend.app.services.progress_analytics_service import ProgressAnalyticsService
from backend.app.services.progress_trend_service import ProgressTrendService
from backend.app.services.review_risk_service import ReviewRiskService

router = APIRouter(prefix="/api/courses", tags=["progress"])


def get_progress_service(
    session: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> ProgressAnalyticsService:
    return ProgressAnalyticsService(session, settings)


@router.get("/{course_id}/progress/overview", response_model=ProgressOverview)
def overview(course_id: int, service: ProgressAnalyticsService = Depends(get_progress_service)) -> ProgressOverview:
    try:
        return service.overview(course_id)
    except MasteryReadError as error:
        raise ApiError(404 if error.code == "COURSE_NOT_FOUND" else 409, error.code, error.message) from error


@router.get("/{course_id}/progress/knowledge", response_model=ProgressKnowledge)
def knowledge(course_id: int, service: ProgressAnalyticsService = Depends(get_progress_service)) -> ProgressKnowledge:
    try:
        return service.knowledge(course_id)
    except MasteryReadError as error:
        raise ApiError(404 if error.code == "COURSE_NOT_FOUND" else 409, error.code, error.message) from error


@router.get("/{course_id}/progress/history", response_model=LearningHistoryPage)
def history(
    course_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = None,
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> LearningHistoryPage:
    try:
        return LearningHistoryService(session, settings).history(course_id, limit=limit, cursor=cursor)
    except MasteryReadError as error:
        status = 404 if error.code == "COURSE_NOT_FOUND" else 400
        raise ApiError(status, error.code, error.message) from error


@router.get("/{course_id}/progress/trend", response_model=ProgressTrend)
def trend(
    course_id: int,
    time_range: Literal["7d", "30d", "all"] = Query(default="30d", alias="range"),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ProgressTrend:
    try:
        return ProgressTrendService(session, settings).trend(course_id, time_range)
    except MasteryReadError as error:
        raise ApiError(404 if error.code == "COURSE_NOT_FOUND" else 409, error.code, error.message) from error


@router.get("/{course_id}/progress/review-risk", response_model=ReviewRiskResponse)
def review_risk(
    course_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ReviewRiskResponse:
    try:
        return ReviewRiskService(session, settings).assess(course_id, limit=limit)
    except MasteryReadError as error:
        raise ApiError(404 if error.code == "COURSE_NOT_FOUND" else 409, error.code, error.message) from error
