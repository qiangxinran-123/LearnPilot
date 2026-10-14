import { httpClient } from '@/services/http';
import type {
  CanonicalNodePage,
  KnowledgeBuildJobResponse,
  KnowledgeBuildStatus,
  KnowledgeModelBuildResponse,
  KnowledgeModelResponse,
  KnowledgeNodeDetailResponse,
  KnowledgeRelationshipsResponse,
} from '@/types/knowledge';

const KNOWLEDGE_MODEL_BUILD_TIMEOUT_MS = 180_000;

export function fetchKnowledgeModel(
  courseId: number,
  { canonicalOnly = false }: { canonicalOnly?: boolean } = {},
): Promise<KnowledgeModelResponse> {
  return httpClient.get<KnowledgeModelResponse>(`/courses/${courseId}/knowledge-model`, {
    params: canonicalOnly ? { canonical_only: true } : undefined,
  });
}

export function fetchKnowledgeNodeDetail(
  courseId: number,
  nodeId: number,
): Promise<KnowledgeNodeDetailResponse> {
  return httpClient.get<KnowledgeNodeDetailResponse>(
    `/courses/${courseId}/knowledge-nodes/${nodeId}`,
  );
}
export function fetchKnowledgeRelationships(
  courseId: number,
): Promise<KnowledgeRelationshipsResponse> {
  return httpClient.get<KnowledgeRelationshipsResponse>(
    `/courses/${courseId}/knowledge-relationships`,
  );
}

export function buildKnowledgeModel(courseId: number): Promise<KnowledgeModelBuildResponse> {
  return httpClient.post<KnowledgeModelBuildResponse>(
    `/courses/${courseId}/knowledge-model/build`,
    undefined,
    { timeout: KNOWLEDGE_MODEL_BUILD_TIMEOUT_MS },
  );
}

export function fetchKnowledgeBuildStatus(courseId: number): Promise<KnowledgeBuildStatus> {
  return httpClient.get<KnowledgeBuildStatus>(`/courses/${courseId}/knowledge-model/build-status`);
}

export function startKnowledgeBuild(courseId: number): Promise<KnowledgeBuildJobResponse> {
  return httpClient.post<KnowledgeBuildJobResponse>(
    `/courses/${courseId}/knowledge-model/build-jobs`,
  );
}

export function fetchCanonicalNodes(
  courseId: number,
  { query = '', offset = 0, limit = 8 }: { query?: string; offset?: number; limit?: number } = {},
): Promise<CanonicalNodePage> {
  return httpClient.get<CanonicalNodePage>(`/courses/${courseId}/knowledge-nodes`, {
    params: { q: query || undefined, offset, limit },
  });
}
