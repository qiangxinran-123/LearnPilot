import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import LearningSessionView from '@/views/LearningSessionView.vue';
import TutorPanel from '@/components/learning/TutorPanel.vue';
import {
  cancelLearningSession,
  completeLearningSession,
  fetchLearningSession,
  fetchLearningSessionContent,
  fetchTutorMessages,
  nextPracticeQuestion,
  sendTutorMessage,
  updateLearningSessionTask,
} from '@/services/learningSessions';
import { ApiError } from '@/services/http';
import type { AdaptivePractice, LearningContent, LearningSession } from '@/types/learningSession';

const routing = vi.hoisted(() => ({
  push: vi.fn(),
  route: { params: { sessionId: '91' } as Record<string, string> },
}));

vi.mock('vue-router', async () => {
  const actual = await vi.importActual('vue-router');
  return {
    ...actual,
    useRouter: () => ({ push: routing.push }),
    useRoute: () => routing.route,
  };
});
vi.mock('@/services/learningSessions', () => ({
  cancelLearningSession: vi.fn(),
  completeLearningSession: vi.fn(),
  fetchLearningSession: vi.fn(),
  fetchLearningSessionContent: vi.fn(),
  fetchTutorMessages: vi.fn(),
  nextPracticeQuestion: vi.fn(),
  answerPracticeQuestion: vi.fn(),
  sendTutorMessage: vi.fn(),
  updateLearningSessionTask: vi.fn(),
}));

const baseSession: LearningSession = {
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
  tasks: [
    {
      task_id: 101,
      phase: 'concept_learning',
      order_index: 0,
      status: 'not_started',
      source_learning_task_id: 41,
      progress: {},
      started_at: null,
      completed_at: null,
      created_at: '2026-10-25T08:00:00Z',
      updated_at: '2026-10-25T08:00:00Z',
    },
    {
      task_id: 102,
      phase: 'guided_example',
      order_index: 1,
      status: 'not_started',
      source_learning_task_id: 42,
      progress: {},
      started_at: null,
      completed_at: null,
      created_at: '2026-10-25T08:00:00Z',
      updated_at: '2026-10-25T08:00:00Z',
    },
    {
      task_id: 103,
      phase: 'adaptive_practice',
      order_index: 2,
      status: 'not_started',
      source_learning_task_id: null,
      progress: {},
      started_at: null,
      completed_at: null,
      created_at: '2026-10-25T08:00:00Z',
      updated_at: '2026-10-25T08:00:00Z',
    },
  ],
  started_at: null,
  completed_at: null,
  cancelled_at: null,
  created_at: '2026-10-25T08:00:00Z',
  updated_at: '2026-10-25T08:00:00Z',
  reused: false,
};

const baseContent: LearningContent = {
  session_id: 91,
  course_id: 7,
  knowledge_node_id: 11,
  knowledge_node_name: '集合映射',
  knowledge_node_description: '理解映射的定义与性质。',
  phase: 'concept_learning',
  status: 'ready',
  grounded: true,
  segments: [
    {
      material_id: 51,
      material_title: '离散数学讲义',
      material_type: 'pdf',
      segment_index: 1,
      fragment_index: 0,
      text: '映射把定义域中的每个元素对应到陪域中的唯一元素。',
      source_reference: 'PDF 第 2 页',
      relevance: 'direct',
      content_hash: 'a'.repeat(64),
      text_truncated: false,
    },
    {
      material_id: 52,
      material_title: '函数补充笔记',
      material_type: 'txt',
      segment_index: 0,
      fragment_index: 0,
      text: '单射要求不同输入具有不同输出。',
      source_reference: 'TXT segment 1',
      relevance: 'supplemental',
      content_hash: 'b'.repeat(64),
      text_truncated: false,
    },
    {
      material_id: 53,
      material_title: '映射示例文档',
      material_type: 'docx',
      segment_index: 2,
      fragment_index: 0,
      text: '文档中的映射例题使用段落来源。',
      source_reference: 'DOCX 段落 3',
      relevance: 'supplemental',
      content_hash: 'c'.repeat(64),
      text_truncated: false,
    },
    {
      material_id: 54,
      material_title: '映射复习提纲',
      material_type: 'md',
      segment_index: 0,
      fragment_index: 0,
      text: 'Markdown 提纲列出映射的定义。',
      source_reference: 'MD 第1节',
      relevance: 'supplemental',
      content_hash: 'd'.repeat(64),
      text_truncated: false,
    },
  ],
  limits: {
    max_segments: 6,
    max_segment_chars: 800,
    max_total_chars: 6600,
    max_segments_per_material: 2,
  },
};

const basePractice: AdaptivePractice = {
  session_id: 91,
  knowledge_node_id: 11,
  assessment_id: 71,
  status: 'in_progress',
  current_difficulty: 'medium',
  current_question: {
    assessment_question_id: 301,
    question_id: 41,
    question_number: 1,
    question_type: 'single_choice',
    stem: '映射必须满足什么条件？',
    options: [
      { key: 'A', text: '每个输入对应唯一输出' },
      { key: 'B', text: '一个输入对应多个输出' },
    ],
    difficulty: 'medium',
  },
  answered_count: 0,
  max_questions: 5,
  attempts: [],
  summary: null,
  reused: false,
};

describe('M7-1 learning session workspace', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    routing.route.params = { sessionId: '91' };
    vi.mocked(fetchLearningSession).mockResolvedValue(structuredClone(baseSession));
    vi.mocked(fetchLearningSessionContent).mockResolvedValue(structuredClone(baseContent));
    vi.mocked(fetchTutorMessages).mockResolvedValue({ session_id: 91, messages: [] });
    vi.mocked(nextPracticeQuestion).mockResolvedValue(structuredClone(basePractice));
  });

  it('loads server state and renders the frozen three phases without fabricated outcomes', async () => {
    const wrapper = mount(LearningSessionView);
    expect(wrapper.text()).not.toContain('集合映射');
    await flushPromises();
    expect(fetchLearningSession).toHaveBeenCalledWith(91);
    expect(fetchLearningSessionContent).toHaveBeenCalledWith(91, 'concept_learning');
    expect(wrapper.text()).toContain('离散数学');
    expect(wrapper.text()).toContain('集合映射');
    expect(wrapper.text()).toContain('概念理解');
    expect(wrapper.text()).toContain('示例讲解');
    expect(wrapper.text()).toContain('针对练习');
    expect(wrapper.text()).toContain('完成前两个学习阶段后');
    expect(wrapper.text()).toContain('根据连续作答表现调整难度');
    expect(wrapper.text()).toContain('AI Tutor');
    expect(sendTutorMessage).not.toHaveBeenCalled();
  });

  it('shows multiple real source references and opens the selected material', async () => {
    const wrapper = mount(LearningSessionView);
    await flushPromises();
    expect(wrapper.text()).toContain('课程原始资料');
    expect(wrapper.text()).toContain('离散数学讲义');
    expect(wrapper.text()).toContain('PDF 第 2 页');
    expect(wrapper.text()).toContain('函数补充笔记');
    expect(wrapper.text()).toContain('TXT segment 1');
    expect(wrapper.text()).toContain('DOCX 段落 3');
    expect(wrapper.text()).toContain('MD 第1节');
    expect(wrapper.text()).toContain('知识点来源');
    expect(wrapper.text()).toContain('课程内补充');
    await wrapper.find('.source-excerpt__link').trigger('click');
    expect(routing.push).toHaveBeenCalledWith({
      name: 'material-detail',
      params: { courseId: 7, materialId: 51 },
    });
  });

  it('renders an honest empty state without generated filler', async () => {
    vi.mocked(fetchLearningSessionContent).mockResolvedValue({
      ...structuredClone(baseContent),
      status: 'empty',
      grounded: false,
      segments: [],
    });
    const wrapper = mount(LearningSessionView);
    await flushPromises();
    expect(wrapper.text()).toContain('暂未找到相关课程内容');
    expect(wrapper.text()).toContain('不会用生成内容填充此区域');
    expect(wrapper.find('.source-excerpt').exists()).toBe(false);
  });

  it('shows a content error and retries only the content request', async () => {
    vi.mocked(fetchLearningSessionContent)
      .mockRejectedValueOnce(new ApiError('资料读取失败', { code: 'CONTENT_ERROR', status: 500 }))
      .mockResolvedValueOnce(structuredClone(baseContent));
    const wrapper = mount(LearningSessionView);
    await flushPromises();
    expect(wrapper.text()).toContain('学习内容加载失败');
    expect(wrapper.text()).toContain('资料读取失败');
    const retry = wrapper.findAll('button').find((button) => button.text().includes('重新加载'));
    await retry?.trigger('click');
    await flushPromises();
    expect(fetchLearningSession).toHaveBeenCalledTimes(1);
    expect(fetchLearningSessionContent).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain('离散数学讲义');
  });

  it('collapses bounded long excerpts instead of expanding the page unconditionally', async () => {
    const longContent = structuredClone(baseContent);
    longContent.segments = [{ ...longContent.segments[0]!, text: '缓存映射内容'.repeat(100) }];
    vi.mocked(fetchLearningSessionContent).mockResolvedValue(longContent);
    const wrapper = mount(LearningSessionView);
    await flushPromises();
    expect(wrapper.find('details').exists()).toBe(true);
    expect(wrapper.find('summary').text().endsWith('…')).toBe(true);
  });

  it('persists a supported task transition using the server response', async () => {
    const updated = structuredClone(baseSession);
    updated.status = 'in_progress';
    updated.tasks[0]!.status = 'in_progress';
    updated.started_at = '2026-10-25T08:05:00Z';
    vi.mocked(updateLearningSessionTask).mockResolvedValue(updated);
    const wrapper = mount(LearningSessionView);
    await flushPromises();
    const start = wrapper.findAll('button').find((button) => button.text().includes('开始本阶段'));
    await start?.trigger('click');
    await flushPromises();
    expect(updateLearningSessionTask).toHaveBeenCalledWith(91, 'concept_learning', 'in_progress');
    expect(wrapper.text()).toContain('学习中');
  });

  it('opens a safe Tutor hint from the active practice question', async () => {
    const ready = structuredClone(baseSession);
    ready.status = 'in_progress';
    ready.tasks[0]!.status = 'completed';
    ready.tasks[1]!.status = 'completed';
    vi.mocked(fetchLearningSession).mockResolvedValue(ready);
    const wrapper = mount(LearningSessionView);
    await flushPromises();
    await wrapper.findAll('button').find((item) => item.text().includes('开始针对练习'))!.trigger('click');
    await flushPromises();
    await wrapper.findAll('button').find((item) => item.text().includes('我不理解这道题'))!.trigger('click');
    const tutorDraft = wrapper.find('.tutor-panel textarea');
    expect((tutorDraft.element as HTMLTextAreaElement).value).toContain('不要透露正确答案');
  });

  it('shows a recoverable error for a missing session', async () => {
    vi.mocked(fetchLearningSession).mockRejectedValue(
      new ApiError('Learning session not found.', { code: 'SESSION_NOT_FOUND', status: 404 }),
    );
    const wrapper = mount(LearningSessionView);
    await flushPromises();
    expect(wrapper.text()).toContain('无法打开学习会话');
    expect(wrapper.text()).toContain('Learning session not found.');
  });

  it('cancels on the server before returning to Learn', async () => {
    const cancelled = structuredClone(baseSession);
    cancelled.status = 'cancelled';
    cancelled.cancelled_at = '2026-10-25T08:10:00Z';
    vi.mocked(cancelLearningSession).mockResolvedValue(cancelled);
    const wrapper = mount(LearningSessionView);
    await flushPromises();
    const button = wrapper.findAll('button').find((item) => item.text().includes('取消本次会话'));
    await button?.trigger('click');
    await flushPromises();
    expect(cancelLearningSession).toHaveBeenCalledWith(91);
    expect(routing.push).toHaveBeenCalledWith({ name: 'learn', query: { courseId: '7' } });
  });

  it('rejects an invalid route parameter without making a request', async () => {
    routing.route.params = { sessionId: 'bad' };
    const wrapper = mount(LearningSessionView);
    await flushPromises();
    expect(fetchLearningSession).not.toHaveBeenCalled();
    expect(wrapper.text()).toContain('学习会话地址无效');
  });

  it('settles once while pending and restores a saved summary on reload', async () => {
    const ready = structuredClone(baseSession);
    ready.status = 'in_progress';
    ready.tasks.forEach((task) => { task.status = 'completed'; });
    const completed = structuredClone(ready);
    completed.status = 'completed';
    completed.recommendation_refresh_status = 'succeeded';
    completed.completion_summary = {
      practice_summary: { total_questions: 5, correct_answers: 4, accuracy: 0.8 },
      mastery_changes: [{ knowledge_node_id: 11, before: 50, after: 60, delta: 10,
        confidence: 'medium', calculated_at: '2026-10-25T08:00:00Z' }],
      evidence_ids: [1, 2, 3, 4, 5], recommendation: null,
    };
    vi.mocked(fetchLearningSession).mockResolvedValue(ready);
    let resolve!: (value: LearningSession) => void;
    vi.mocked(completeLearningSession).mockImplementation(() => new Promise((done) => { resolve = done; }));
    const wrapper = mount(LearningSessionView);
    await flushPromises();
    const button = wrapper.findAll('button').find((item) => item.text().includes('完成学习并查看结果'))!;
    await button.trigger('click');
    await button.trigger('click');
    expect(completeLearningSession).toHaveBeenCalledTimes(1);
    resolve(completed);
    await flushPromises();
    expect(wrapper.text()).toContain('提高 10 个百分点');
    vi.mocked(fetchLearningSession).mockResolvedValue(completed);
    const reloaded = mount(LearningSessionView);
    await flushPromises();
    expect(reloaded.text()).toContain('本次学习已完成');
    expect(reloaded.text()).toContain('查看 Tutor 辅导记录');
    expect(reloaded.text()).toContain('该会话已结束，历史辅导记录仍可查看。');
    expect(completeLearningSession).toHaveBeenCalledTimes(1);
  });

  it('refreshes Session status after a successful Tutor exchange', async () => {
    const updated = structuredClone(baseSession);
    updated.status = 'in_progress';
    vi.mocked(fetchLearningSession).mockResolvedValueOnce(structuredClone(baseSession)).mockResolvedValue(updated);
    const wrapper = mount(LearningSessionView);
    await flushPromises();
    wrapper.findComponent(TutorPanel).vm.$emit('changed');
    await flushPromises();
    expect(fetchLearningSession).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain('学习中');
    expect(wrapper.text()).not.toContain('尚未开始');
  });

  it('recovers a committed settlement after a lost response', async () => {
    const ready = structuredClone(baseSession);
    ready.status = 'in_progress';
    ready.tasks.forEach((task) => { task.status = 'completed'; });
    const completed = structuredClone(ready);
    completed.status = 'completed';
    completed.recommendation_refresh_status = 'succeeded';
    completed.completion_summary = {
      practice_summary: { total_questions: 5, correct_answers: 3, accuracy: 0.6 },
      mastery_changes: [{ knowledge_node_id: 11, before: 80, after: 70, delta: -10,
        confidence: 'medium', calculated_at: '2026-10-25T08:00:00Z' }],
      evidence_ids: [1, 2, 3, 4, 5], recommendation: null,
    };
    vi.mocked(fetchLearningSession).mockResolvedValue(ready);
    vi.mocked(completeLearningSession)
      .mockRejectedValueOnce(new ApiError('连接中断，请重试', { code: 'NETWORK_ERROR' }))
      .mockResolvedValueOnce(completed);
    const wrapper = mount(LearningSessionView);
    await flushPromises();
    const button = wrapper.findAll('button').find((item) => item.text().includes('完成学习并查看结果'))!;
    await button.trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('连接中断');
    await button.trigger('click');
    await flushPromises();
    expect(completeLearningSession).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain('下降 10 个百分点');
  });
});
