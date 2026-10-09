import { httpClient } from '@/services/http';
import type {
  KnowledgeModelBuildResponse,
  KnowledgeModelResponse,
  KnowledgeNodeDetailResponse,
  KnowledgeRelationshipsResponse,
} from '@/types/knowledge';

const KNOWLEDGE_MODEL_BUILD_TIMEOUT_MS = 180_000;

export function fetchKnowledgeModel(courseId: number): Promise<KnowledgeModelResponse> {
  return httpClient.get<KnowledgeModelResponse>(`/courses/${courseId}/knowledge-model`);
}

export function fetchKnowledgeNodeDetail(
  courseId: number,
  nodeId: number,
): Promise<KnowledgeNodeDetailResponse> {
  return httpClient.get<KnowledgeNodeDetailResponse>(
    `/courses/${courseId}/knowledge-nodes/${nodeId}`,
  );
}
export function fetchKnowledgeRelationships(courseId: number): Promise<KnowledgeRelationshipsResponse> {
  return httpClient.get<KnowledgeRelationshipsResponse>(
    `/courses/${courseId}/knowledge-relationships`);
}

export function buildKnowledgeModel(courseId: number): Promise<KnowledgeModelBuildResponse> {
  return httpClient.post<KnowledgeModelBuildResponse>(
    `/courses/${courseId}/knowledge-model/build`,
    undefined,
    { timeout: KNOWLEDGE_MODEL_BUILD_TIMEOUT_MS },
  );
}
