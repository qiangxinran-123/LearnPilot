import { defineComponent } from 'vue';
import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { unavailablePresentation } from '@/components/learning/planPresentation';
import { useLearningPlan } from '@/composables/useLearningPlan';
import { ApiError } from '@/services/http';
import { fetchKnowledgeModel } from '@/services/knowledge';
import { fetchLearningPlan, generateLearningPlan } from '@/services/learningPlans';
import type { KnowledgeModelResponse } from '@/types/knowledge';
import type { LearningPlanResponse } from '@/types/learningPlan';

vi.mock('@/services/knowledge', () => ({ fetchKnowledgeModel: vi.fn() }));
vi.mock('@/services/learningPlans', () => ({
  fetchLearningPlan: vi.fn(),
  generateLearningPlan: vi.fn(),
}));

const model: KnowledgeModelResponse = {
  course_id: 7,
  nodes: [
    {
      id: 11,
      course_id: 7,
      name: '集合映射',
      normalized_name: '集合映射',
      description: '理解映射的定义与性质。',
      importance: 'high',
      difficulty: 'intermediate',
      created_at: '2026-10-22T08:00:00Z',
      updated_at: '2026-10-22T08:00:00Z',
    },
  ],
  edges: [],
};

function planResponse(
  availability: LearningPlanResponse['availability'] = 'available',
): LearningPlanResponse {
  return {
    availability,
    recommendation_status: 'available',
    plan_level: 'personalized',
    reused: false,
    plan: {
      plan_id: 31,
      user_id: 2,
      course_id: 7,
      target_node_id: 11,
      reason_codes: ['knowledge_gap', 'neutral_review_risk'],
      priority_score: '0.6250',
      priority_breakdown: {
        knowledge_gap: '0.8000',
        dependency_importance: '0.5000',
        course_importance: '0.5000',
        review_risk: '0.5000',
        total_priority: '0.6250',
      },
      prerequisite_evidence: [],
      blocked_target_node_ids: [],
      status: 'available',
      tasks: [
        {
          task_id: 41,
          knowledge_node_id: 11,
          task_type: 'concept_review',
          title: '回顾集合映射',
          description: '梳理核心定义。',
          order_index: 0,
          estimated_minutes: 15,
        },
      ],
      created_at: '2026-10-22T08:00:00Z',
      updated_at: '2026-10-22T08:00:00Z',
    },
  };
}

function deferred<T>(): {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason?: unknown) => void;
} {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

const Harness = defineComponent({
  setup() {
    return { learningPlan: useLearningPlan() };
  },
  template: `
    <div>
      <span data-testid="state">{{ learningPlan.state.value }}</span>
      <span data-testid="target">{{ learningPlan.targetNode.value?.name }}</span>
      <span data-testid="regeneration-error">{{ learningPlan.regenerationError.value }}</span>
      <button data-testid="load" @click="learningPlan.load(7)">load</button>
      <button data-testid="load-other" @click="learningPlan.load(8)">load other</button>
      <button data-testid="regenerate" :disabled="learningPlan.isGenerating.value" @click="learningPlan.regenerate">regenerate</button>
    </div>
  `,
});

describe('useLearningPlan request lifecycle', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchKnowledgeModel).mockResolvedValue(model);
  });

  it('loads an available plan and never generates it automatically', async () => {
    vi.mocked(fetchLearningPlan).mockResolvedValue(planResponse());
    const wrapper = mount(Harness);
    await wrapper.get('[data-testid="load"]').trigger('click');
    await flushPromises();
    expect(wrapper.get('[data-testid="state"]').text()).toBe('available');
    expect(wrapper.get('[data-testid="target"]').text()).toBe('集合映射');
    expect(generateLearningPlan).not.toHaveBeenCalled();
  });

  it('treats stale as a business state and only POSTs once after an explicit click', async () => {
    const pending = deferred<LearningPlanResponse>();
    vi.mocked(fetchLearningPlan).mockResolvedValue(planResponse('stale'));
    vi.mocked(generateLearningPlan).mockReturnValue(pending.promise);
    const wrapper = mount(Harness);
    await wrapper.get('[data-testid="load"]').trigger('click');
    await flushPromises();
    expect(wrapper.get('[data-testid="state"]').text()).toBe('stale');
    expect(generateLearningPlan).not.toHaveBeenCalled();

    const regenerate = wrapper.get('[data-testid="regenerate"]');
    await regenerate.trigger('click');
    await regenerate.trigger('click');
    expect(generateLearningPlan).toHaveBeenCalledTimes(1);
    pending.resolve(planResponse());
    await flushPromises();
    expect(wrapper.get('[data-testid="state"]').text()).toBe('available');
  });

  it('keeps the stale view and retry capability when regeneration fails', async () => {
    vi.mocked(fetchLearningPlan).mockResolvedValue(planResponse('stale'));
    vi.mocked(generateLearningPlan).mockRejectedValue(new ApiError('暂时无法生成'));
    const wrapper = mount(Harness);
    await wrapper.get('[data-testid="load"]').trigger('click');
    await flushPromises();
    await wrapper.get('[data-testid="regenerate"]').trigger('click');
    await flushPromises();
    expect(wrapper.get('[data-testid="state"]').text()).toBe('stale');
    expect(wrapper.get('[data-testid="regeneration-error"]').text()).toBe('暂时无法生成');
    expect(wrapper.get('[data-testid="regenerate"]').attributes('disabled')).toBeUndefined();
  });

  it('does not let an old course response overwrite a newer course request', async () => {
    const oldRequest = deferred<LearningPlanResponse>();
    vi.mocked(fetchLearningPlan).mockImplementation((courseId) => {
      if (courseId === 7) return oldRequest.promise;
      return Promise.resolve({
        availability: 'not_available',
        recommendation_status: 'all_mastered',
        plan_level: null,
        plan: null,
        reused: false,
      });
    });
    const wrapper = mount(Harness);
    await wrapper.get('[data-testid="load"]').trigger('click');
    await wrapper.get('[data-testid="load-other"]').trigger('click');
    await flushPromises();
    expect(wrapper.get('[data-testid="state"]').text()).toBe('unavailable');
    oldRequest.resolve(planResponse());
    await flushPromises();
    expect(wrapper.get('[data-testid="state"]').text()).toBe('unavailable');
    expect(fetchKnowledgeModel).not.toHaveBeenCalled();
  });

  it('separates knowledge-model absence from technical request failures', async () => {
    vi.mocked(fetchLearningPlan).mockRejectedValueOnce(
      new ApiError('The course has no active knowledge model.', {
        code: 'KNOWLEDGE_MODEL_NOT_FOUND',
        status: 422,
      }),
    );
    const wrapper = mount(Harness);
    await wrapper.get('[data-testid="load"]').trigger('click');
    await flushPromises();
    expect(wrapper.get('[data-testid="state"]').text()).toBe('unavailable');
    expect(unavailablePresentation(null, 7, 'KNOWLEDGE_MODEL_NOT_FOUND').title).toContain(
      '知识结构',
    );

    vi.mocked(fetchLearningPlan).mockRejectedValueOnce(new ApiError('网络异常'));
    await wrapper.get('[data-testid="load"]').trigger('click');
    await flushPromises();
    expect(wrapper.get('[data-testid="state"]').text()).toBe('error');
  });
});
