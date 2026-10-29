import { httpClient } from '@/services/http';
import type { ReviewRiskResponse } from '@/types/reviewRisk';

export function fetchReviewRisk(courseId: number): Promise<ReviewRiskResponse> {
  return httpClient.get<ReviewRiskResponse>(`/courses/${courseId}/progress/review-risk`, { params: { limit: 500 } });
}
