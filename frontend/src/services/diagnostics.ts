import { httpClient } from '@/services/http';
import type {
  Assessment,
  AssessmentDiscardResponse,
  AssessmentListResponse,
  CourseQuestionPreparationResponse,
  DiagnosticQuestionGenerationResponse,
  DiagnosticReadiness,
  DiagnosticResult,
  QuestionBankListResponse,
  QuestionBankReadiness,
  QuestionReviewResponse,
  QuestionValidationStatus,
  SavedResponse,
} from '@/types/diagnostic';

export function fetchDiagnosticReadiness(courseId: number): Promise<DiagnosticReadiness> {
  return httpClient.get<DiagnosticReadiness>(`/diagnostics/courses/${courseId}/readiness`);
}

export function fetchQuestionBankReadiness(courseId: number): Promise<QuestionBankReadiness> {
  return httpClient.get<QuestionBankReadiness>(`/diagnostics/courses/${courseId}/question-bank`);
}

export function fetchDiagnosticQuestions(
  courseId: number,
  status?: QuestionValidationStatus,
): Promise<QuestionBankListResponse> {
  return httpClient.get<QuestionBankListResponse>(`/diagnostics/courses/${courseId}/questions`, {
    params: status ? { status } : undefined,
  });
}

export function generateDiagnosticQuestion(
  courseId: number,
  knowledgeNodeId: number,
): Promise<DiagnosticQuestionGenerationResponse> {
  return httpClient.post<DiagnosticQuestionGenerationResponse>(
    `/diagnostics/courses/${courseId}/questions/generate`,
    { knowledge_node_id: knowledgeNodeId, count: 1 },
  );
}

export function prepareCourseDiagnosticQuestions(
  courseId: number,
): Promise<CourseQuestionPreparationResponse> {
  return httpClient.post<CourseQuestionPreparationResponse>(
    `/diagnostics/courses/${courseId}/questions/prepare`,
  );
}

export function approveDiagnosticQuestion(
  courseId: number,
  questionId: number,
): Promise<QuestionReviewResponse> {
  return httpClient.post<QuestionReviewResponse>(
    `/diagnostics/courses/${courseId}/questions/${questionId}/approve`,
  );
}

export function rejectDiagnosticQuestion(
  courseId: number,
  questionId: number,
): Promise<QuestionReviewResponse> {
  return httpClient.post<QuestionReviewResponse>(
    `/diagnostics/courses/${courseId}/questions/${questionId}/reject`,
  );
}

export function createOrResumeAssessment(courseId: number): Promise<Assessment> {
  return httpClient.post<Assessment>('/diagnostics/assessments', { course_id: courseId });
}

export function fetchAssessments(): Promise<AssessmentListResponse> {
  return httpClient.get<AssessmentListResponse>('/diagnostics/assessments');
}

export function fetchAssessment(assessmentId: number): Promise<Assessment> {
  return httpClient.get<Assessment>(`/diagnostics/assessments/${assessmentId}`);
}

export function startAssessment(assessmentId: number): Promise<Assessment> {
  return httpClient.post<Assessment>(`/diagnostics/assessments/${assessmentId}/start`);
}

export function saveAssessmentResponse(
  assessmentId: number,
  assessmentQuestionId: number,
  selectedOptions: string[],
): Promise<SavedResponse> {
  return httpClient.put<SavedResponse>(
    `/diagnostics/assessments/${assessmentId}/responses/${assessmentQuestionId}`,
    { schema_version: 'objective_answer_v1', selected_options: selectedOptions },
  );
}

export function discardAssessment(assessmentId: number): Promise<AssessmentDiscardResponse> {
  return httpClient.post<AssessmentDiscardResponse>(
    `/diagnostics/assessments/${assessmentId}/discard`,
  );
}

export function submitAssessment(assessmentId: number): Promise<DiagnosticResult> {
  return httpClient.post<DiagnosticResult>(`/diagnostics/assessments/${assessmentId}/submit`);
}

export function fetchAssessmentResult(assessmentId: number): Promise<DiagnosticResult> {
  return httpClient.get<DiagnosticResult>(`/diagnostics/assessments/${assessmentId}/result`);
}
