import { httpClient } from '@/services/http';
import type { LearningHistory, ProgressTrend, TrendRange } from '@/types/progressHistory';

export function fetchProgressTrend(courseId: number, range: TrendRange): Promise<ProgressTrend> {
  return httpClient.get<ProgressTrend>(`/courses/${courseId}/progress/trend`, { params: { range } });
}
export function fetchLearningHistory(courseId: number, cursor?: string): Promise<LearningHistory> {
  return httpClient.get<LearningHistory>(`/courses/${courseId}/progress/history`, { params: { cursor } });
}
