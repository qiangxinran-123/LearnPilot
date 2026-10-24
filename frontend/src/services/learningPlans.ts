import { httpClient } from '@/services/http';
import type { LearningPlanResponse } from '@/types/learningPlan';

export function fetchLearningPlan(courseId: number): Promise<LearningPlanResponse> {
  return httpClient.get<LearningPlanResponse>(`/courses/${courseId}/learning-plan`);
}

export function generateLearningPlan(courseId: number): Promise<LearningPlanResponse> {
  return httpClient.post<LearningPlanResponse>(`/courses/${courseId}/learning-plan/generate`);
}
