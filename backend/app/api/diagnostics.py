from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.core.errors import ApiError
from backend.app.models import QuestionValidationStatus
from backend.app.schemas.assessment_scoring import AssessmentReadinessSchema
from backend.app.schemas.diagnostic_api import (
    DiagnosticAssessmentCreateSchema,
    DiagnosticAssessmentDetailSchema,
    DiagnosticAssessmentDiscardSchema,
    DiagnosticAssessmentListSchema,
    DiagnosticResponseSaveSchema,
    DiagnosticResultSchema,
    SavedResponseSchema,
)
from backend.app.schemas.question_generation import (
    CourseQuestionPreparationResponseSchema,
    DiagnosticQuestionGenerateRequestSchema,
    DiagnosticQuestionGenerationResponseSchema,
    QuestionBankListSchema,
    QuestionBankReadinessSchema,
    QuestionReviewResponseSchema,
)
from backend.app.services.assessment_assembly_service import AssessmentAssemblyError
from backend.app.services.diagnostic_domain_service import DiagnosticDomainError
from backend.app.services.diagnostic_experience_service import (
    DiagnosticExperienceService,
    get_diagnostic_experience_service,
)
from backend.app.services.diagnostic_question_bank_service import (
    DiagnosticQuestionBankError,
    DiagnosticQuestionBankService,
    get_diagnostic_question_bank_service,
)
from backend.app.services.diagnostic_question_generation import DiagnosticQuestionGenerationError
from backend.app.services.diagnostic_report_service import DiagnosticReportError

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


def _api_error(
    error: AssessmentAssemblyError
    | DiagnosticDomainError
    | DiagnosticReportError
    | DiagnosticQuestionBankError
    | DiagnosticQuestionGenerationError,
) -> ApiError:
    if error.code in {
        "COURSE_NOT_FOUND",
        "ASSESSMENT_NOT_FOUND",
        "KNOWLEDGE_NODE_NOT_FOUND",
        "QUESTION_NOT_FOUND",
    }:
        status = 404
    elif error.code in {
        "ANSWER_INVALID",
        "QUESTION_SNAPSHOT_INVALID",
        "SCORING_POLICY_UNSUPPORTED",
        "QUESTION_ALIGNMENT_INVALID",
        "QUESTION_QUALITY_INVALID",
        "QUESTION_SOURCE_INVALID",
    }:
        status = 422
    elif error.code in {
        "AI_NOT_CONFIGURED",
        "AI_TIMEOUT",
        "AI_RATE_LIMITED",
    }:
        status = 503
    elif error.code in {"AI_AUTHENTICATION_FAILED", "AI_PROVIDER_ERROR", "QUESTION_GENERATION_FAILED"}:
        status = 502
    else:
        status = 409
    return ApiError(status, error.code, error.message)


@router.get("/courses/{course_id}/readiness", response_model=AssessmentReadinessSchema)
def get_readiness(
    course_id: int, service: DiagnosticExperienceService = Depends(get_diagnostic_experience_service)
) -> AssessmentReadinessSchema:
    try:
        return service.readiness(course_id)
    except (AssessmentAssemblyError, DiagnosticDomainError, DiagnosticReportError) as error:
        raise _api_error(error) from error


@router.get("/courses/{course_id}/question-bank", response_model=QuestionBankReadinessSchema)
def get_question_bank_readiness(
    course_id: int,
    service: DiagnosticQuestionBankService = Depends(get_diagnostic_question_bank_service),
) -> QuestionBankReadinessSchema:
    try:
        return service.readiness(course_id)
    except (AssessmentAssemblyError, DiagnosticQuestionBankError) as error:
        raise _api_error(error) from error


@router.get("/courses/{course_id}/questions", response_model=QuestionBankListSchema)
def list_diagnostic_questions(
    course_id: int,
    status: QuestionValidationStatus | None = None,
    service: DiagnosticQuestionBankService = Depends(get_diagnostic_question_bank_service),
) -> QuestionBankListSchema:
    try:
        return service.list_questions(course_id, status)
    except DiagnosticQuestionBankError as error:
        raise _api_error(error) from error


@router.post(
    "/courses/{course_id}/questions/generate",
    response_model=DiagnosticQuestionGenerationResponseSchema,
    status_code=201,
)
def generate_diagnostic_question(
    course_id: int,
    payload: DiagnosticQuestionGenerateRequestSchema,
    service: DiagnosticQuestionBankService = Depends(get_diagnostic_question_bank_service),
) -> DiagnosticQuestionGenerationResponseSchema:
    try:
        return service.generate_pending(
            course_id=course_id,
            knowledge_node_id=payload.knowledge_node_id,
        )
    except (DiagnosticQuestionBankError, DiagnosticQuestionGenerationError) as error:
        raise _api_error(error) from error


@router.post(
    "/courses/{course_id}/questions/prepare",
    response_model=CourseQuestionPreparationResponseSchema,
)
def prepare_course_diagnostic_questions(
    course_id: int,
    service: DiagnosticQuestionBankService = Depends(get_diagnostic_question_bank_service),
) -> CourseQuestionPreparationResponseSchema:
    try:
        return service.prepare_course(course_id)
    except (AssessmentAssemblyError, DiagnosticQuestionBankError, DiagnosticQuestionGenerationError) as error:
        raise _api_error(error) from error


@router.post(
    "/courses/{course_id}/questions/{question_id}/approve",
    response_model=QuestionReviewResponseSchema,
)
def approve_diagnostic_question(
    course_id: int,
    question_id: int,
    service: DiagnosticQuestionBankService = Depends(get_diagnostic_question_bank_service),
) -> QuestionReviewResponseSchema:
    try:
        return service.approve(course_id, question_id)
    except DiagnosticQuestionBankError as error:
        raise _api_error(error) from error


@router.post(
    "/courses/{course_id}/questions/{question_id}/reject",
    response_model=QuestionReviewResponseSchema,
)
def reject_diagnostic_question(
    course_id: int,
    question_id: int,
    service: DiagnosticQuestionBankService = Depends(get_diagnostic_question_bank_service),
) -> QuestionReviewResponseSchema:
    try:
        return service.reject(course_id, question_id)
    except DiagnosticQuestionBankError as error:
        raise _api_error(error) from error


@router.post("/assessments", response_model=DiagnosticAssessmentDetailSchema, status_code=201)
def create_assessment(
    payload: DiagnosticAssessmentCreateSchema,
    service: DiagnosticExperienceService = Depends(get_diagnostic_experience_service),
) -> DiagnosticAssessmentDetailSchema:
    try:
        return service.create_or_resume(payload.course_id)
    except (AssessmentAssemblyError, DiagnosticDomainError) as error:
        raise _api_error(error) from error


@router.get("/assessments", response_model=DiagnosticAssessmentListSchema)
def list_assessments(
    service: DiagnosticExperienceService = Depends(get_diagnostic_experience_service),
) -> DiagnosticAssessmentListSchema:
    return service.list_assessments()


@router.get("/assessments/{assessment_id}", response_model=DiagnosticAssessmentDetailSchema)
def get_assessment(
    assessment_id: int, service: DiagnosticExperienceService = Depends(get_diagnostic_experience_service)
) -> DiagnosticAssessmentDetailSchema:
    try:
        return service.get_assessment(assessment_id)
    except (AssessmentAssemblyError, DiagnosticDomainError) as error:
        raise _api_error(error) from error


@router.post("/assessments/{assessment_id}/start", response_model=DiagnosticAssessmentDetailSchema)
def start_assessment(
    assessment_id: int, service: DiagnosticExperienceService = Depends(get_diagnostic_experience_service)
) -> DiagnosticAssessmentDetailSchema:
    try:
        return service.start(assessment_id)
    except (AssessmentAssemblyError, DiagnosticDomainError) as error:
        raise _api_error(error) from error


@router.put(
    "/assessments/{assessment_id}/responses/{assessment_question_id}",
    response_model=SavedResponseSchema,
)
def save_response(
    assessment_id: int,
    assessment_question_id: int,
    payload: DiagnosticResponseSaveSchema,
    service: DiagnosticExperienceService = Depends(get_diagnostic_experience_service),
) -> SavedResponseSchema:
    try:
        return service.save_response(assessment_id, assessment_question_id, payload)
    except (AssessmentAssemblyError, DiagnosticDomainError) as error:
        raise _api_error(error) from error


@router.post(
    "/assessments/{assessment_id}/discard",
    response_model=DiagnosticAssessmentDiscardSchema,
)
def discard_assessment(
    assessment_id: int, service: DiagnosticExperienceService = Depends(get_diagnostic_experience_service)
) -> DiagnosticAssessmentDiscardSchema:
    try:
        return service.discard(assessment_id)
    except (AssessmentAssemblyError, DiagnosticDomainError) as error:
        raise _api_error(error) from error


@router.post("/assessments/{assessment_id}/submit", response_model=DiagnosticResultSchema)
def submit_assessment(
    assessment_id: int, service: DiagnosticExperienceService = Depends(get_diagnostic_experience_service)
) -> DiagnosticResultSchema:
    try:
        return service.submit(assessment_id)
    except (AssessmentAssemblyError, DiagnosticDomainError) as error:
        raise _api_error(error) from error


@router.get("/assessments/{assessment_id}/result", response_model=DiagnosticResultSchema)
def get_result(
    assessment_id: int, service: DiagnosticExperienceService = Depends(get_diagnostic_experience_service)
) -> DiagnosticResultSchema:
    try:
        return service.result(assessment_id)
    except (AssessmentAssemblyError, DiagnosticDomainError, DiagnosticReportError) as error:
        raise _api_error(error) from error
