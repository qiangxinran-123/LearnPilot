import { httpClient } from '@/services/http';
import type {
  Assessment,
  AssessmentListResponse,
  DiagnosticReadiness,
  DiagnosticResult,
  SavedResponse,
} from '@/types/diagnostic';

export function fetchDiagnosticReadiness(courseId: number): Promise<DiagnosticReadiness> {
  return httpClient.get<DiagnosticReadiness>(`/diagnostics/courses/${courseId}/readiness`);
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

export function submitAssessment(assessmentId: number): Promise<DiagnosticResult> {
  return httpClient.post<DiagnosticResult>(`/diagnostics/assessments/${assessmentId}/submit`);
}

export function fetchAssessmentResult(assessmentId: number): Promise<DiagnosticResult> {
  return httpClient.get<DiagnosticResult>(`/diagnostics/assessments/${assessmentId}/result`);
}
