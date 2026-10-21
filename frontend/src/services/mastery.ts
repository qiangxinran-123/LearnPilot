import { httpClient } from '@/services/http';
import type {
  CourseMasteryResponse,
  KnowledgeEvidenceExplanation,
  KnowledgeNodeMastery,
} from '@/types/mastery';

export function fetchCourseMastery(courseId: number): Promise<CourseMasteryResponse> {
  return httpClient.get<CourseMasteryResponse>(`/courses/${courseId}/mastery`);
}

export function fetchNodeMastery(courseId: number, nodeId: number): Promise<KnowledgeNodeMastery> {
  return httpClient.get<KnowledgeNodeMastery>(`/courses/${courseId}/knowledge/${nodeId}/mastery`);
}

export function fetchNodeEvidence(
  courseId: number,
  nodeId: number,
  { offset = 0, limit = 20 }: { offset?: number; limit?: number } = {},
): Promise<KnowledgeEvidenceExplanation> {
  return httpClient.get<KnowledgeEvidenceExplanation>(
    `/courses/${courseId}/knowledge/${nodeId}/evidence`,
    { params: { offset, limit } },
  );
}
