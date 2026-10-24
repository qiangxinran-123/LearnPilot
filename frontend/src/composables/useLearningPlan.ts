import { computed, onBeforeUnmount, ref } from 'vue';

import { fetchKnowledgeModel } from '@/services/knowledge';
import { normalizeApiError } from '@/services/http';
import { fetchLearningPlan, generateLearningPlan } from '@/services/learningPlans';
import type { KnowledgeNode } from '@/types/knowledge';
import type {
  LearningPlanResponse,
  LearningPlanViewState,
  RecommendationAvailabilityStatus,
} from '@/types/learningPlan';

const BUSINESS_UNAVAILABLE_CODES = new Set(['KNOWLEDGE_MODEL_NOT_FOUND']);

export function useLearningPlan() {
  const state = ref<LearningPlanViewState>('idle');
  const response = ref<LearningPlanResponse | null>(null);
  const nodes = ref<ReadonlyMap<number, KnowledgeNode>>(new Map());
  const activeCourseId = ref<number | null>(null);
  const errorMessage = ref('');
  const regenerationError = ref('');
  const businessCode = ref<string | null>(null);
  const isGenerating = ref(false);
  let request = 0;
  let disposed = false;

  const plan = computed(() => response.value?.plan ?? null);
  const recommendationStatus = computed<RecommendationAvailabilityStatus | null>(
    () => response.value?.recommendation_status ?? null,
  );
  const planLevel = computed(() => response.value?.plan_level ?? null);
  const targetNode = computed(() => {
    const targetId = plan.value?.target_node_id;
    return targetId ? (nodes.value.get(targetId) ?? null) : null;
  });
  const estimatedMinutes = computed(
    () => plan.value?.tasks.reduce((total, task) => total + (task.estimated_minutes ?? 0), 0) ?? 0,
  );

  function reset(courseId: number | null): void {
    activeCourseId.value = courseId;
    isGenerating.value = false;
    response.value = null;
    nodes.value = new Map();
    errorMessage.value = '';
    regenerationError.value = '';
    businessCode.value = null;
  }

  async function acceptResponse(
    result: LearningPlanResponse,
    courseId: number,
    currentRequest: number,
  ): Promise<void> {
    if (result.plan && result.plan.course_id !== courseId) {
      throw new Error('Learning plan course mismatch');
    }
    if (result.availability === 'available' && result.plan) {
      const model = await fetchKnowledgeModel(courseId);
      if (disposed || currentRequest !== request || courseId !== activeCourseId.value) return;
      if (model.course_id !== courseId) throw new Error('Knowledge model course mismatch');
      const nodeMap = new Map(model.nodes.map((node) => [node.id, node]));
      if (!nodeMap.has(result.plan.target_node_id)) {
        throw new Error('Recommended knowledge node is unavailable');
      }
      nodes.value = nodeMap;
      response.value = result;
      state.value = 'available';
      return;
    }
    response.value = result;
    state.value = result.availability === 'stale' ? 'stale' : 'unavailable';
  }

  async function load(courseId: number | null): Promise<void> {
    const currentRequest = ++request;
    reset(courseId);
    if (!courseId) {
      state.value = 'idle';
      return;
    }
    state.value = 'loading';
    try {
      const result = await fetchLearningPlan(courseId);
      if (disposed || currentRequest !== request || courseId !== activeCourseId.value) return;
      await acceptResponse(result, courseId, currentRequest);
    } catch (error: unknown) {
      if (disposed || currentRequest !== request || courseId !== activeCourseId.value) return;
      const normalized = normalizeApiError(error);
      if (normalized.code && BUSINESS_UNAVAILABLE_CODES.has(normalized.code)) {
        businessCode.value = normalized.code;
        state.value = 'unavailable';
        return;
      }
      errorMessage.value = normalized.message;
      state.value = 'error';
    }
  }

  async function regenerate(): Promise<void> {
    const courseId = activeCourseId.value;
    if (!courseId || isGenerating.value) return;
    const currentRequest = ++request;
    isGenerating.value = true;
    regenerationError.value = '';
    try {
      const result = await generateLearningPlan(courseId);
      if (disposed || currentRequest !== request || courseId !== activeCourseId.value) return;
      await acceptResponse(result, courseId, currentRequest);
    } catch (error: unknown) {
      if (disposed || currentRequest !== request || courseId !== activeCourseId.value) return;
      regenerationError.value = normalizeApiError(error).message;
      if (state.value !== 'stale') {
        errorMessage.value = regenerationError.value;
        state.value = 'error';
      }
    } finally {
      if (!disposed && currentRequest === request) isGenerating.value = false;
    }
  }

  onBeforeUnmount(() => {
    disposed = true;
    request += 1;
  });

  return {
    state,
    response,
    plan,
    targetNode,
    nodes,
    activeCourseId,
    recommendationStatus,
    planLevel,
    estimatedMinutes,
    errorMessage,
    regenerationError,
    businessCode,
    isGenerating,
    load,
    regenerate,
  };
}
