import { computed, onBeforeUnmount, reactive, ref, watch, type Ref } from 'vue';

import {
  buildKnowledgeModel,
  fetchKnowledgeModel,
  fetchKnowledgeNodeDetail,
  fetchKnowledgeRelationships,
} from '@/services/knowledge';
import { normalizeApiError } from '@/services/http';
import type {
  KnowledgeEdge,
  KnowledgeEdgeEvidence,
  KnowledgeModelResponse,
  KnowledgeNodeDetailResponse,
} from '@/types/knowledge';

export type KnowledgeModelLoadState = 'loading' | 'ready' | 'error';

export function useKnowledgeModel(courseId: Ref<number>) {
  const state = ref<KnowledgeModelLoadState>('loading');
  const model = ref<KnowledgeModelResponse | null>(null);
  const errorMessage = ref('');
  const buildErrorMessage = ref('');
  const isBuilding = ref(false);
  const selectedNodeDetail = ref<KnowledgeNodeDetailResponse | null>(null);
  const isNodeDetailOpen = ref(false);
  const isNodeDetailLoading = ref(false);
  const selectedEdge = ref<KnowledgeEdge | null>(null);
  const isEdgeDetailOpen = ref(false);
  const evidenceByEdgeId = ref(new Map<number, KnowledgeEdgeEvidence[]>());
  const visibility = reactive({ contains: true, prerequisite: true });
  let activeLoadRequest = 0;
  let activeDetailRequest = 0;
  let disposed = false;

  const nodeCount = computed(() => model.value?.nodes.length ?? 0);
  const containsCount = computed(
    () => model.value?.edges.filter((edge) => edge.relation_type === 'contains').length ?? 0,
  );
  const prerequisiteCount = computed(
    () => model.value?.edges.filter((edge) => edge.relation_type === 'prerequisite').length ?? 0,
  );

  function resetSelection(): void {
    selectedNodeDetail.value = null;
    selectedEdge.value = null;
    isNodeDetailOpen.value = false;
    isEdgeDetailOpen.value = false;
  }

  async function load({ preserveModel = false }: { preserveModel?: boolean } = {}): Promise<boolean> {
    const request = ++activeLoadRequest;
    if (!preserveModel || model.value === null) {
      state.value = 'loading';
    }
    errorMessage.value = '';

    try {
      const knowledgeModel = await fetchKnowledgeModel(courseId.value);
      if (disposed || request !== activeLoadRequest) {
        return false;
      }

      model.value = knowledgeModel;
      state.value = 'ready';
      evidenceByEdgeId.value = new Map();

      try {
        const relationships = await fetchKnowledgeRelationships(courseId.value);
        if (disposed || request !== activeLoadRequest) {
          return false;
        }
        const evidence = new Map<number, KnowledgeEdgeEvidence[]>();
        for (const edge of [...relationships.contains_edges, ...relationships.prerequisite_edges]) {
          evidence.set(edge.id, edge.evidence);
        }
        evidenceByEdgeId.value = evidence;
      } catch (error: unknown) {
        const apiError = normalizeApiError(error);
        // Relations may not have been generated yet. The canonical model remains
        // authoritative and is still useful for a valid node-only graph.
        if (apiError.code !== 'KNOWLEDGE_RELATIONSHIP_NOT_READY') {
          evidenceByEdgeId.value = new Map();
        }
      }
      return true;
    } catch (error: unknown) {
      if (disposed || request !== activeLoadRequest) {
        return false;
      }
      errorMessage.value = normalizeApiError(error).message;
      if (model.value === null) {
        state.value = 'error';
      }
      return false;
    }
  }

  async function selectNode(nodeId: number): Promise<void> {
    const request = ++activeDetailRequest;
    isNodeDetailOpen.value = true;
    isEdgeDetailOpen.value = false;
    isNodeDetailLoading.value = true;
    selectedNodeDetail.value = null;
    try {
      const detail = await fetchKnowledgeNodeDetail(courseId.value, nodeId);
      if (!disposed && request === activeDetailRequest) {
        selectedNodeDetail.value = detail;
      }
    } catch (error: unknown) {
      if (!disposed && request === activeDetailRequest) {
        isNodeDetailOpen.value = false;
        errorMessage.value = normalizeApiError(error).message;
      }
    } finally {
      if (!disposed && request === activeDetailRequest) {
        isNodeDetailLoading.value = false;
      }
    }
  }

  function selectEdge(edgeId: number): void {
    const edge = model.value?.edges.find((candidate) => candidate.id === edgeId) ?? null;
    if (!edge) {
      return;
    }
    selectedEdge.value = edge;
    isEdgeDetailOpen.value = true;
    isNodeDetailOpen.value = false;
  }

  function edgeEvidence(edgeId: number): KnowledgeEdgeEvidence[] {
    return evidenceByEdgeId.value.get(edgeId) ?? [];
  }

  async function build(): Promise<boolean> {
    if (isBuilding.value) {
      return false;
    }
    isBuilding.value = true;
    buildErrorMessage.value = '';
    try {
      await buildKnowledgeModel(courseId.value);
      const reloaded = await load({ preserveModel: true });
      if (reloaded) {
        return true;
      }
      buildErrorMessage.value =
        errorMessage.value || '知识结构已建立，但刷新最新结果失败。请稍后重新加载。';
      return false;
    } catch (error: unknown) {
      buildErrorMessage.value = normalizeApiError(error).message;
      return false;
    } finally {
      isBuilding.value = false;
    }
  }

  watch(
    courseId,
    () => {
      activeLoadRequest += 1;
      activeDetailRequest += 1;
      model.value = null;
      evidenceByEdgeId.value = new Map();
      buildErrorMessage.value = '';
      resetSelection();
      void load();
    },
    { immediate: true },
  );

  onBeforeUnmount(() => {
    disposed = true;
    activeLoadRequest += 1;
    activeDetailRequest += 1;
  });

  return {
    state,
    model,
    errorMessage,
    buildErrorMessage,
    isBuilding,
    selectedNodeDetail,
    isNodeDetailOpen,
    isNodeDetailLoading,
    selectedEdge,
    isEdgeDetailOpen,
    visibility,
    nodeCount,
    containsCount,
    prerequisiteCount,
    load,
    build,
    selectNode,
    selectEdge,
    edgeEvidence,
    resetSelection,
  };
}
