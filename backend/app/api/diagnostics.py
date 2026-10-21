from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.core.errors import ApiError
from backend.app.schemas.assessment_scoring import AssessmentReadinessSchema
from backend.app.schemas.diagnostic_api import (
    DiagnosticAssessmentCreateSchema,
    DiagnosticAssessmentDetailSchema,
    DiagnosticAssessmentListSchema,
    DiagnosticResponseSaveSchema,
    DiagnosticResultSchema,
    SavedResponseSchema,
)
from backend.app.services.assessment_assembly_service import AssessmentAssemblyError
from backend.app.services.diagnostic_domain_service import DiagnosticDomainError
from backend.app.services.diagnostic_experience_service import (
    DiagnosticExperienceService,
    get_diagnostic_experience_service,
)
from backend.app.services.diagnostic_report_service import DiagnosticReportError

router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])


def _api_error(error: AssessmentAssemblyError | DiagnosticDomainError | DiagnosticReportError) -> ApiError:
    if error.code in {"COURSE_NOT_FOUND", "ASSESSMENT_NOT_FOUND"}:
        status = 404
    elif error.code in {"ANSWER_INVALID", "QUESTION_SNAPSHOT_INVALID", "SCORING_POLICY_UNSUPPORTED"}:
        status = 422
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
