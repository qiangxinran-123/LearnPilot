import { createPinia } from 'pinia';
import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import DashboardView from '@/views/DashboardView.vue';
import LearnView from '@/views/LearnView.vue';
import { fetchCourses } from '@/services/courses';
import { fetchKnowledgeModel } from '@/services/knowledge';
import { fetchLearningPlan, generateLearningPlan } from '@/services/learningPlans';
import { createLearningSession, fetchActiveLearningSession } from '@/services/learningSessions';
import { ApiError } from '@/services/http';
import type { LearningPlanResponse } from '@/types/learningPlan';

const routing = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
  route: { query: {} as Record<string, string> },
}));

vi.mock('vue-router', async () => {
  const actual = await vi.importActual('vue-router');
  return {
    ...actual,
    useRouter: () => ({ push: routing.push, replace: routing.replace }),
    useRoute: () => routing.route,
  };
});
vi.mock('@/services/courses', () => ({ fetchCourses: vi.fn() }));
vi.mock('@/services/knowledge', () => ({ fetchKnowledgeModel: vi.fn() }));
vi.mock('@/services/learningPlans', () => ({
  fetchLearningPlan: vi.fn(),
  generateLearningPlan: vi.fn(),
}));
vi.mock('@/services/learningSessions', () => ({
  createLearningSession: vi.fn(),
  fetchActiveLearningSession: vi.fn(),
}));

const courses = [
  { id: 7, name: '离散数学', description: '集合与图论' },
  { id: 8, name: '计算机组成', description: '处理器与存储系统' },
];
const available: LearningPlanResponse = {
  availability: 'available',
  recommendation_status: 'available',
  plan_level: 'personalized',
  reused: false,
  plan: {
    plan_id: 31,
    user_id: 2,
    course_id: 7,
    target_node_id: 11,
    reason_codes: ['knowledge_gap', 'prerequisite_for_other_nodes'],
    priority_score: '0.6250',
    priority_breakdown: {
      knowledge_gap: '0.8000',
      dependency_importance: '0.5000',
      course_importance: '0.5000',
      review_risk: '0.5000',
      total_priority: '0.6250',
    },
    prerequisite_evidence: [{ source_node_id: 10, target_node_id: 11, status: 'satisfied' }],
    blocked_target_node_ids: [12],
    status: 'available',
    tasks: [
      {
        task_id: 1,
        knowledge_node_id: 11,
        task_type: 'concept_review',
        title: '回顾集合映射',
        description: '梳理定义与关键条件。',
        order_index: 0,
        estimated_minutes: 15,
      },
      {
        task_id: 2,
        knowledge_node_id: 11,
        task_type: 'targeted_practice',
        title: '练习集合映射',
        description: '使用已有练习进行巩固。',
        order_index: 1,
        estimated_minutes: 20,
      },
    ],
    created_at: '2026-10-22T08:00:00Z',
    updated_at: '2026-10-22T08:00:00Z',
  },
};
const model = {
  course_id: 7,
  nodes: [
    {
      id: 10,
      course_id: 7,
      name: '集合基础',
      normalized_name: '集合基础',
      description: '',
      importance: 'medium' as const,
      difficulty: 'basic' as const,
      created_at: '2026-10-22T08:00:00Z',
      updated_at: '2026-10-22T08:00:00Z',
    },
    {
      id: 11,
      course_id: 7,
      name: '集合映射',
      normalized_name: '集合映射',
      description: '理解映射的定义与性质。',
      importance: 'high' as const,
      difficulty: 'intermediate' as const,
      created_at: '2026-10-22T08:00:00Z',
      updated_at: '2026-10-22T08:00:00Z',
    },
  ],
  edges: [],
};

function mountOptions() {
  return {
    global: {
      plugins: [createPinia()],
      stubs: { RouterLink: { template: '<a><slot /></a>' } },
    },
  };
}

describe('M6-4 recommendation views', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    routing.route.query = {};
    vi.mocked(fetchCourses).mockResolvedValue({ count: courses.length, courses });
    vi.mocked(fetchLearningPlan).mockResolvedValue(available);
    vi.mocked(fetchActiveLearningSession).mockResolvedValue({ session: null });
    vi.mocked(fetchKnowledgeModel).mockResolvedValue(model);
  });

  it('keeps recommendations visible and retries a failed active session lookup', async () => {
    vi.mocked(fetchActiveLearningSession)
      .mockRejectedValueOnce(new ApiError('Internal server error.', { status: 500 }))
      .mockResolvedValueOnce({ session: null });
    const wrapper = mount(LearnView, mountOptions());
    await flushPromises();

    expect(wrapper.text()).toContain('集合映射');
    expect(wrapper.text()).toContain('学习会话加载失败');
    expect(wrapper.text()).not.toContain('Internal server error.');
    const start = wrapper.findAll('button').find((button) => button.text().includes('开始学习'));
    expect(start?.attributes('disabled')).toBeDefined();
    const retry = wrapper.findAll('button').find((button) => button.text().includes('重试'));
    await retry?.trigger('click');
    await flushPromises();
    expect(fetchActiveLearningSession).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).not.toContain('学习会话加载失败');
    expect(start?.attributes('disabled')).toBeUndefined();
  });

  it('creates one session from the recommendation and protects repeated clicks', async () => {
    let resolveCreate!: (value: Awaited<ReturnType<typeof createLearningSession>>) => void;
    vi.mocked(createLearningSession).mockReturnValue(
      new Promise((resolve) => {
        resolveCreate = resolve;
      }),
    );
    const wrapper = mount(LearnView, mountOptions());
    await flushPromises();
    const button = wrapper.findAll('button').find((item) => item.text().includes('开始学习'));
    await button?.trigger('click');
    await button?.trigger('click');
    expect(createLearningSession).toHaveBeenCalledTimes(1);
    resolveCreate({
      session_id: 91,
      user_id: 2,
      course_id: 7,
      course_name: '离散数学',
      target_knowledge_node_id: 11,
      target_knowledge_node_name: '集合映射',
      source_learning_plan_id: 31,
      practice_assessment_id: null,
      status: 'created',
      session_contract_version: 'learning_session_v1',
      completion_summary: null,
      recommendation_refresh_status: 'not_requested',
      tasks: [],
      started_at: null,
      completed_at: null,
      cancelled_at: null,
      created_at: '2026-10-25T08:00:00Z',
      updated_at: '2026-10-25T08:00:00Z',
      reused: false,
    });
    await flushPromises();
    expect(routing.push).toHaveBeenCalledWith({
      name: 'learning-session',
      params: { sessionId: 91 },
    });
  });

  it('shows the same real recommendation target on Dashboard and Learn without POSTing', async () => {
    const dashboard = mount(DashboardView, mountOptions());
    await flushPromises();
    const learn = mount(LearnView, mountOptions());
    await flushPromises();
    expect(dashboard.text()).toContain('集合映射');
    expect(learn.text()).toContain('集合映射');
    expect(learn.text()).toContain('当前学习课程');
    expect(learn.text()).toContain('离散数学');
    expect(learn.text()).toContain('个性化学习计划');
    expect(dashboard.text()).toContain('2 个学习任务');
    expect(learn.text()).toContain('预计 35 分钟');
    expect(generateLearningPlan).not.toHaveBeenCalled();
  });

  it('renders tasks in backend order and exposes no completion or execution controls', async () => {
    const wrapper = mount(LearnView, mountOptions());
    await flushPromises();
    const tasks = wrapper.findAll('.task-card');
    expect(tasks).toHaveLength(2);
    expect(tasks[0]!.text()).toContain('回顾集合映射');
    expect(tasks[1]!.text()).toContain('练习集合映射');
    expect(tasks[0]!.text()).toContain('建议用时 15 分钟');
    expect(wrapper.text()).not.toContain('完成任务');
    expect(wrapper.find('input[type="checkbox"]').exists()).toBe(false);
    expect(generateLearningPlan).not.toHaveBeenCalled();
  });

  it('uses the existing knowledge map route with the exact recommended node id', async () => {
    const wrapper = mount(LearnView, mountOptions());
    await flushPromises();
    const button = wrapper.findAll('button').find((item) => item.text().includes('知识地图'));
    await button?.trigger('click');
    expect(routing.push).toHaveBeenCalledWith({
      name: 'course-detail',
      params: { courseId: 7 },
      query: { tab: 'knowledge-structure', nodeId: '11' },
    });
  });

  it('renders stale without an error state or automatic generation', async () => {
    vi.mocked(fetchLearningPlan).mockResolvedValue({ ...available, availability: 'stale' });
    const wrapper = mount(LearnView, mountOptions());
    await flushPromises();
    expect(wrapper.text()).toContain('学习计划需要更新');
    expect(wrapper.text()).not.toContain('学习计划加载失败');
    expect(generateLearningPlan).not.toHaveBeenCalled();
  });

  it('shows diagnosis guidance only when the backend reports initial diagnosis is needed', async () => {
    vi.mocked(fetchLearningPlan).mockResolvedValue({
      availability: 'not_available',
      recommendation_status: 'needs_initial_diagnostic',
      plan_level: null,
      plan: null,
      reused: false,
    });
    const wrapper = mount(LearnView, mountOptions());
    await flushPromises();
    expect(wrapper.text()).toContain('先完成一次学习诊断');
    expect(wrapper.text()).toContain('前往诊断');
  });

  it.each([
    ['preliminary', '初步学习建议', '当前诊断证据仍然有限'],
    ['foundational', '基础学习路线', '当前尚无充分的个人诊断数据'],
  ] as const)(
    'shows the real %s plan level without claiming precise personalization',
    async (level, title, copy) => {
      vi.mocked(fetchLearningPlan).mockResolvedValue({ ...available, plan_level: level });
      const wrapper = mount(LearnView, mountOptions());
      await flushPromises();
      expect(wrapper.text()).toContain(title);
      expect(wrapper.text()).toContain(copy);
    },
  );

  it('offers explicit generation for an available foundational recommendation', async () => {
    vi.mocked(fetchLearningPlan).mockResolvedValue({
      availability: 'not_available',
      recommendation_status: 'available',
      plan_level: 'foundational',
      plan: null,
      reused: false,
    });
    vi.mocked(generateLearningPlan).mockResolvedValue({ ...available, plan_level: 'foundational' });
    const wrapper = mount(LearnView, mountOptions());
    await flushPromises();
    expect(wrapper.text()).toContain('生成基础学习路线');
    expect(generateLearningPlan).not.toHaveBeenCalled();
    const button = wrapper
      .findAll('button')
      .find((item) => item.text().includes('生成基础学习路线'));
    await button?.trigger('click');
    await flushPromises();
    expect(generateLearningPlan).toHaveBeenCalledTimes(1);
    expect(wrapper.text()).toContain('基础学习路线');
  });

  it('switches the visible course context and loads only the selected course plan', async () => {
    vi.mocked(fetchLearningPlan).mockImplementation((courseId) =>
      courseId === 7
        ? Promise.resolve(available)
        : Promise.resolve({
            availability: 'not_available',
            recommendation_status: 'all_mastered',
            plan_level: null,
            plan: null,
            reused: false,
          }),
    );
    const wrapper = mount(LearnView, mountOptions());
    await flushPromises();
    expect(wrapper.text()).toContain('离散数学');
    expect(wrapper.text()).toContain('集合映射');

    wrapper.findComponent({ name: 'ElSelect' }).vm.$emit('update:modelValue', 8);
    await flushPromises();
    expect(fetchLearningPlan).toHaveBeenCalledWith(8);
    expect(wrapper.text()).toContain('计算机组成');
    expect(wrapper.text()).not.toContain('集合映射');
    expect(wrapper.text()).toContain('当前暂无优先补强内容');
  });
});
