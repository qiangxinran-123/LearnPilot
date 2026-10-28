from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Response, status

from backend.app.ai import AIServiceError
from backend.app.core.errors import ApiError
from backend.app.models import LearningSessionTaskPhase
from backend.app.schemas.learning_content import LearningContentRead
from backend.app.schemas.learning_session import (
    ActiveLearningSessionResponse,
    LearningSessionCreate,
    LearningSessionRead,
    LearningSessionTaskUpdate,
)
from backend.app.schemas.practice import PracticeAnswerCreate, PracticeRead
from backend.app.schemas.tutor import (
    TutorExchangeRead,
    TutorMessageCreate,
    TutorMessageListRead,
)
from backend.app.services.adaptive_practice_service import (
    AdaptivePracticeError,
    AdaptivePracticeService,
    get_adaptive_practice_service,
)
from backend.app.services.learning_content_service import (
    LearningContentError,
    LearningContentService,
    get_learning_content_service,
)
from backend.app.services.learning_session_service import (
    LearningSessionError,
    LearningSessionService,
    get_learning_session_service,
)
from backend.app.services.learning_settlement_service import (
    LearningSettlementService,
    get_learning_settlement_service,
)
from backend.app.services.tutor_service import TutorError, TutorService, get_tutor_service

router = APIRouter(prefix="/api/learning/sessions", tags=["learning-sessions"])


def _practice_api_error(error: AdaptivePracticeError) -> ApiError:
    if error.code in {"SESSION_NOT_FOUND", "SESSION_TASK_NOT_FOUND", "PRACTICE_QUESTION_NOT_FOUND"}:
        http_status = 404
    elif error.code in {
        "ANSWER_REQUIRED",
        "SCORING_ANSWER_INVALID",
        "SCORING_INPUT_INVALID",
        "SCORING_POLICY_UNSUPPORTED",
        "QUESTION_SNAPSHOT_INVALID",
    }:
        http_status = 422
    else:
        http_status = 409
    return ApiError(http_status, error.code, error.message)


def _content_api_error(error: LearningContentError) -> ApiError:
    if error.code in {"USER_NOT_FOUND", "SESSION_NOT_FOUND"}:
        http_status = 404
    elif error.code in {"CONTENT_PHASE_NOT_AVAILABLE", "SESSION_SCOPE_INVALID"}:
        http_status = 409
    else:
        http_status = 422
    return ApiError(http_status, error.code, error.message)


def _tutor_api_error(error: TutorError) -> ApiError:
    if error.code == "SESSION_NOT_FOUND":
        http_status = 404
    elif error.code in {
        "SESSION_NOT_TUTORABLE",
        "SESSION_TASK_NOT_FOUND",
        "TUTOR_MESSAGE_CONFLICT",
        "TUTOR_MESSAGE_INCOMPLETE",
    }:
        http_status = 409
    else:
        http_status = 422
    return ApiError(http_status, error.code, error.message)


def _tutor_ai_error(error: AIServiceError) -> ApiError:
    if error.code == "AI_RATE_LIMITED":
        http_status = 429
    elif error.code == "AI_TIMEOUT":
        http_status = 504
    elif error.code in {"AI_PROVIDER_ERROR", "AI_AUTHENTICATION_FAILED", "AI_NOT_CONFIGURED"}:
        http_status = 503
    else:
        http_status = 502
    return ApiError(http_status, error.code, error.message)


def _api_error(error: LearningSessionError) -> ApiError:
    if error.code in {
        "USER_NOT_FOUND",
        "COURSE_NOT_FOUND",
        "KNOWLEDGE_NODE_NOT_FOUND",
        "SESSION_NOT_FOUND",
        "SESSION_TASK_NOT_FOUND",
    }:
        http_status = 404
    elif error.code in {
        "KNOWLEDGE_NODE_INACTIVE",
        "LEARNING_PLAN_NOT_AVAILABLE",
        "LEARNING_SESSION_CONFLICT",
        "SESSION_NOT_WRITABLE",
        "SESSION_NOT_CANCELLABLE",
        "TASK_PHASE_NOT_AVAILABLE",
        "TASK_ORDER_VIOLATION",
        "INVALID_TASK_TRANSITION",
        "SESSION_NOT_READY",
        "PRACTICE_NOT_READY",
        "PRACTICE_SCOPE_MISMATCH",
    }:
        http_status = 409
    else:
        http_status = 422
    return ApiError(http_status, error.code, error.message)


@router.post("", response_model=LearningSessionRead, status_code=status.HTTP_201_CREATED)
def create_learning_session(
    payload: LearningSessionCreate,
    response: Response,
    service: LearningSessionService = Depends(get_learning_session_service),
) -> LearningSessionRead:
    try:
        result = service.create_for_configured_user(payload)
    except LearningSessionError as error:
        raise _api_error(error) from error
    if result.reused:
        response.status_code = status.HTTP_200_OK
    return result


@router.get("/active", response_model=ActiveLearningSessionResponse)
def get_active_learning_session(
    course_id: int = Query(gt=0),
    service: LearningSessionService = Depends(get_learning_session_service),
) -> ActiveLearningSessionResponse:
    try:
        return service.get_active_for_configured_user(course_id)
    except LearningSessionError as error:
        raise _api_error(error) from error


@router.get("/{session_id}", response_model=LearningSessionRead)
def get_learning_session(
    session_id: int,
    service: LearningSessionService = Depends(get_learning_session_service),
) -> LearningSessionRead:
    try:
        return service.get_for_configured_user(session_id)
    except LearningSessionError as error:
        raise _api_error(error) from error


@router.get("/{session_id}/content", response_model=LearningContentRead)
def get_learning_session_content(
    session_id: int,
    phase: LearningSessionTaskPhase = Query(default=LearningSessionTaskPhase.CONCEPT_LEARNING),
    q: str | None = Query(default=None, max_length=500),
    service: LearningContentService = Depends(get_learning_content_service),
) -> LearningContentRead:
    try:
        return service.get_for_configured_user(session_id=session_id, phase=phase, query=q)
    except LearningContentError as error:
        raise _content_api_error(error) from error


@router.post("/{session_id}/practice/next", response_model=PracticeRead)
def next_practice_question(
    session_id: int,
    service: AdaptivePracticeService = Depends(get_adaptive_practice_service),
) -> PracticeRead:
    try:
        return service.start_or_next_for_configured_user(session_id)
    except AdaptivePracticeError as error:
        raise _practice_api_error(error) from error


@router.put(
    "/{session_id}/practice/responses/{assessment_question_id}",
    response_model=PracticeRead,
)
def answer_practice_question(
    session_id: int,
    assessment_question_id: int,
    payload: PracticeAnswerCreate,
    service: AdaptivePracticeService = Depends(get_adaptive_practice_service),
) -> PracticeRead:
    try:
        return service.answer_for_configured_user(
            session_id=session_id,
            assessment_question_id=assessment_question_id,
            payload=payload,
        )
    except AdaptivePracticeError as error:
        raise _practice_api_error(error) from error


@router.get("/{session_id}/tutor/messages", response_model=TutorMessageListRead)
def get_tutor_messages(
    session_id: int,
    service: TutorService = Depends(get_tutor_service),
) -> TutorMessageListRead:
    try:
        return service.list_messages_for_configured_user(session_id)
    except TutorError as error:
        raise _tutor_api_error(error) from error


@router.post("/{session_id}/tutor/messages", response_model=TutorExchangeRead)
def create_tutor_message(
    session_id: int,
    payload: TutorMessageCreate,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=128),
    service: TutorService = Depends(get_tutor_service),
) -> TutorExchangeRead:
    try:
        return service.send_message_for_configured_user(
            session_id=session_id,
            payload=payload,
            idempotency_key=idempotency_key,
        )
    except TutorError as error:
        raise _tutor_api_error(error) from error
    except AIServiceError as error:
        raise _tutor_ai_error(error) from error


@router.patch("/{session_id}/tasks/{phase}", response_model=LearningSessionRead)
def update_learning_session_task(
    session_id: int,
    phase: LearningSessionTaskPhase,
    payload: LearningSessionTaskUpdate,
    service: LearningSessionService = Depends(get_learning_session_service),
) -> LearningSessionRead:
    try:
        return service.update_task_for_configured_user(session_id=session_id, phase=phase, payload=payload)
    except LearningSessionError as error:
        raise _api_error(error) from error


@router.post("/{session_id}/cancel", response_model=LearningSessionRead)
def cancel_learning_session(
    session_id: int,
    service: LearningSessionService = Depends(get_learning_session_service),
) -> LearningSessionRead:
    try:
        return service.cancel_for_configured_user(session_id)
    except LearningSessionError as error:
        raise _api_error(error) from error


@router.post("/{session_id}/complete", response_model=LearningSessionRead)
def complete_learning_session(
    session_id: int,
    service: LearningSettlementService = Depends(get_learning_settlement_service),
) -> LearningSessionRead:
    try:
        return service.complete_for_configured_user(session_id)
    except LearningSessionError as error:
        raise _api_error(error) from error


__all__ = ["router"]
