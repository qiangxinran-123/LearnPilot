import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import PracticePanel from '@/components/learning/PracticePanel.vue';
import { answerPracticeQuestion, nextPracticeQuestion } from '@/services/learningSessions';
import { ApiError } from '@/services/http';
import type { AdaptivePractice, PracticeAttempt, PracticeQuestion } from '@/types/learningSession';

vi.mock('@/services/learningSessions', () => ({
  answerPracticeQuestion: vi.fn(),
  nextPracticeQuestion: vi.fn(),
}));

const question: PracticeQuestion = {
  assessment_question_id: 301,
  question_id: 41,
  question_number: 1,
  question_type: 'single_choice',
  stem: '直接映射缓存中，主存块映射到哪里？',
  options: [
    { key: 'A', text: '唯一确定的缓存行' },
    { key: 'B', text: '任意缓存行' },
  ],
  difficulty: 'medium',
};

const basePractice: AdaptivePractice = {
  session_id: 91,
  knowledge_node_id: 11,
  assessment_id: 71,
  status: 'in_progress',
  current_difficulty: 'medium',
  current_question: question,
  answered_count: 0,
  max_questions: 5,
  attempts: [],
  summary: null,
  reused: false,
};

function attempt(isCorrect = false): PracticeAttempt {
  return {
    ...question,
    attempt_id: 501,
    selected_options: [isCorrect ? 'A' : 'B'],
    correct_answer: ['A'],
    explanation: '直接映射使用块号取模得到唯一缓存行。',
    is_correct: isCorrect,
    points_awarded: isCorrect ? '1.00' : '0.00',
    source_refs: [
      {
        material_id: 9,
        material_title: 'Cache Lecture',
        source_reference: 'PDF 第 2 页',
        excerpt: null,
      },
    ],
    submitted_at: '2026-10-26T08:00:00Z',
  };
}

function mountPanel(props: Partial<InstanceType<typeof PracticePanel>['$props']> = {}) {
  return mount(PracticePanel, {
    props: {
      sessionId: 91,
      practiceAssessmentId: null,
      enabled: true,
      readOnly: false,
      ...props,
    },
  });
}

describe('M7-4 adaptive practice panel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(nextPracticeQuestion).mockResolvedValue(structuredClone(basePractice));
  });

  it('starts from the server and renders a redacted single-choice question', async () => {
    const wrapper = mountPanel();
    await wrapper.get('button').trigger('click');
    await flushPromises();
    expect(nextPracticeQuestion).toHaveBeenCalledWith(91);
    expect(wrapper.text()).toContain('直接映射缓存中');
    expect(wrapper.text()).toContain('中等');
    expect(wrapper.text()).not.toContain('正确答案');
  });

  it('validates selection, submits once and renders deterministic feedback', async () => {
    vi.mocked(answerPracticeQuestion).mockResolvedValue({
      ...structuredClone(basePractice),
      current_question: null,
      answered_count: 1,
      attempts: [attempt(false)],
    });
    const wrapper = mountPanel();
    await wrapper.get('button').trigger('click');
    await flushPromises();
    const submit = wrapper.findAll('button').find((item) => item.text().includes('提交答案'))!;
    await submit.trigger('click');
    expect(wrapper.text()).toContain('请先选择一个有效答案');
    expect(answerPracticeQuestion).not.toHaveBeenCalled();
    await wrapper.findAll('input[type="radio"]')[1]!.setValue(true);
    await submit.trigger('click');
    await flushPromises();
    expect(answerPracticeQuestion).toHaveBeenCalledWith(91, 301, ['B']);
    expect(wrapper.text()).toContain('需要再理解一下');
    expect(wrapper.text()).toContain('正确答案：A');
    expect(wrapper.text()).toContain('PDF 第 2 页');
  });

  it('supports multiple-choice submission', async () => {
    const multiple = structuredClone(basePractice);
    multiple.current_question = {
      ...question,
      question_type: 'multiple_choice',
      options: [
        { key: 'A', text: '时间局部性' },
        { key: 'B', text: '空间局部性' },
      ],
    };
    vi.mocked(nextPracticeQuestion).mockResolvedValue(multiple);
    vi.mocked(answerPracticeQuestion).mockResolvedValue({
      ...multiple,
      current_question: null,
      answered_count: 1,
      attempts: [{ ...attempt(true), question_type: 'multiple_choice', selected_options: ['A', 'B'] }],
    });
    const wrapper = mountPanel();
    await wrapper.get('button').trigger('click');
    await flushPromises();
    const checks = wrapper.findAll('input[type="checkbox"]');
    await checks[0]!.setValue(true);
    await checks[1]!.setValue(true);
    await wrapper.findAll('button').find((item) => item.text().includes('提交答案'))!.trigger('click');
    await flushPromises();
    expect(answerPracticeQuestion).toHaveBeenCalledWith(91, 301, ['A', 'B']);
  });

  it('retries the same answer after an interrupted response', async () => {
    vi.mocked(answerPracticeQuestion)
      .mockRejectedValueOnce(new ApiError('连接中断，请重试', { code: 'NETWORK_ERROR' }))
      .mockResolvedValueOnce({
        ...structuredClone(basePractice), current_question: null, answered_count: 1, attempts: [attempt(false)],
      });
    const wrapper = mountPanel();
    await wrapper.get('button').trigger('click');
    await flushPromises();
    await wrapper.findAll('input[type="radio"]')[1]!.setValue(true);
    await wrapper.findAll('button').find((button) => button.text().includes('提交答案'))!.trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('连接中断');
    await wrapper.findAll('button').find((button) => button.text() === '重试')!.trigger('click');
    await flushPromises();
    expect(vi.mocked(answerPracticeQuestion).mock.calls).toEqual([[91, 301, ['B']], [91, 301, ['B']]]);
    expect(wrapper.text()).toContain('需要再理解一下');
  });

  it('restores an existing practice and renders its completed summary', async () => {
    vi.mocked(nextPracticeQuestion).mockResolvedValue({
      ...structuredClone(basePractice),
      status: 'completed',
      current_question: null,
      answered_count: 5,
      attempts: [attempt(true)],
      summary: { answered_count: 5, correct_count: 4, accuracy: '0.80' },
    });
    const wrapper = mountPanel({ practiceAssessmentId: 71 });
    await flushPromises();
    expect(nextPracticeQuestion).toHaveBeenCalledWith(91);
    expect(wrapper.text()).toContain('本次练习已完成');
    expect(wrapper.text()).toContain('正确率 80%');
    expect(wrapper.text()).toContain('将在后续结算流程中更新');
  });

  it('shows explicit empty and recoverable API error states', async () => {
    vi.mocked(nextPracticeQuestion)
      .mockRejectedValueOnce(new ApiError('练习服务暂不可用', { code: 'NETWORK_ERROR' }))
      .mockResolvedValueOnce({
        ...structuredClone(basePractice),
        status: 'question_bank_empty',
        current_question: null,
      });
    const wrapper = mountPanel();
    await wrapper.get('button').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('练习服务暂不可用');
    await wrapper.findAll('button').find((item) => item.text() === '重试')!.trigger('click');
    await flushPromises();
    expect(nextPracticeQuestion).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).toContain('暂无可用练习题');
  });

  it('emits safe Tutor modes before and after an incorrect answer', async () => {
    vi.mocked(answerPracticeQuestion).mockResolvedValue({
      ...structuredClone(basePractice),
      current_question: null,
      answered_count: 1,
      attempts: [attempt(false)],
    });
    const wrapper = mountPanel();
    await wrapper.get('button').trigger('click');
    await flushPromises();
    await wrapper.findAll('button').find((item) => item.text().includes('我不理解'))!.trigger('click');
    expect(wrapper.emitted('askTutor')?.[0]?.[0]).toMatchObject({ mode: 'hint' });
    await wrapper.findAll('input[type="radio"]')[1]!.setValue(true);
    await wrapper.findAll('button').find((item) => item.text().includes('提交答案'))!.trigger('click');
    await flushPromises();
    await wrapper.findAll('button').find((item) => item.text().includes('解释错题'))!.trigger('click');
    expect(wrapper.emitted('askTutor')?.[1]?.[0]).toMatchObject({
      mode: 'step_by_step_explanation',
    });
  });
});
