import { httpClient } from '@/services/http';
import type { ProgressKnowledge, ProgressOverview } from '@/types/progress';

export function fetchProgressOverview(courseId: number): Promise<ProgressOverview> {
  return httpClient.get<ProgressOverview>(`/courses/${courseId}/progress/overview`);
}
export function fetchProgressKnowledge(courseId: number): Promise<ProgressKnowledge> {
  return httpClient.get<ProgressKnowledge>(`/courses/${courseId}/progress/knowledge`);
}
