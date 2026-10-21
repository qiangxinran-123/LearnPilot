import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import DiagnosticAssessmentView from '@/views/DiagnosticAssessmentView.vue';
import { fetchAssessment, saveAssessmentResponse } from '@/services/diagnostics';

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { assessmentId: '12' } }),
  useRouter: () => ({ push: vi.fn() }),
}));
vi.mock('@/services/diagnostics', () => ({
  fetchAssessment: vi.fn(),
  fetchAssessmentResult: vi.fn(),
  saveAssessmentResponse: vi.fn(),
  startAssessment: vi.fn(),
  submitAssessment: vi.fn(),
}));

const questions = [
  { assessment_question_id: 1, order_index: 0, question_type: 'single_choice' as const, stem: '单选题干', options: [{ key: 'A', text: '甲' }, { key: 'B', text: '乙' }], difficulty: 'easy' as const, saved_answer: null },
  { assessment_question_id: 2, order_index: 1, question_type: 'true_false' as const, stem: '判断题干', options: [{ key: 'TRUE', text: '正确' }, { key: 'FALSE', text: '错误' }], difficulty: 'medium' as const, saved_answer: null },
  { assessment_question_id: 3, order_index: 2, question_type: 'multiple_choice' as const, stem: '多选题干', options: [{ key: 'A', text: '甲' }, { key: 'B', text: '乙' }, { key: 'C', text: '丙' }], difficulty: 'hard' as const, saved_answer: null },
];

describe('DiagnosticAssessmentView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    vi.mocked(fetchAssessment).mockResolvedValue({
      id: 12, course_id: 2, course_name: '数据结构', status: 'in_progress', questions,
      question_count: 3, answered_count: 0, created_at: 'now', started_at: 'now', submitted_at: null,
    });
    vi.mocked(saveAssessmentResponse).mockImplementation(async (_assessment, questionId, selected) => ({
      assessment_question_id: questionId, selected_options: selected, answered_at: 'now',
    }));
  });

  it('supports single choice, true/false, multiple choice and question navigation', async () => {
    const wrapper = mount(DiagnosticAssessmentView, { attachTo: document.body });
    await flushPromises();
    expect(wrapper.text()).toContain('单选题');
    await wrapper.findAll('.el-radio')[0]!.trigger('click');
    await flushPromises();
    expect(saveAssessmentResponse).toHaveBeenLastCalledWith(12, 1, ['A']);
    await wrapper.findAll('.number-grid button')[1]!.trigger('click');
    expect(wrapper.text()).toContain('判断题');
    await wrapper.findAll('.el-radio')[1]!.trigger('click');
    await flushPromises();
    expect(saveAssessmentResponse).toHaveBeenLastCalledWith(12, 2, ['FALSE']);
    await wrapper.findAll('.number-grid button')[2]!.trigger('click');
    expect(wrapper.text()).toContain('多选题');
    await wrapper.findAll('.el-checkbox')[0]!.trigger('click');
    await wrapper.findAll('.el-checkbox')[2]!.trigger('click');
    await flushPromises();
    expect(saveAssessmentResponse).toHaveBeenLastCalledWith(12, 3, ['A', 'C']);
    expect(wrapper.text()).toContain('已保存');
    wrapper.unmount();
  });

  it('shows unanswered counts in the submission confirmation', async () => {
    const wrapper = mount(DiagnosticAssessmentView, { attachTo: document.body });
    await flushPromises();
    await wrapper.findAll('.number-grid button')[2]!.trigger('click');
    const submitButton = wrapper.findAll('button').find((button) => button.text() === '提交诊断');
    await submitButton?.trigger('click');
    await flushPromises();
    expect(document.body.textContent).toContain('未答 3 题');
    expect(document.body.textContent).toContain('提交后不能修改答案');
    wrapper.unmount();
  });
});
