import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import DiagnosticAssessmentView from '@/views/DiagnosticAssessmentView.vue';
import { discardAssessment, fetchAssessment, saveAssessmentResponse } from '@/services/diagnostics';

const routerMocks = vi.hoisted(() => ({
  push: vi.fn(),
  leaveGuard: undefined as ((to: { fullPath: string }) => boolean) | undefined,
}));
vi.mock('vue-router', () => ({
  onBeforeRouteLeave: (guard: (to: { fullPath: string }) => boolean) => {
    routerMocks.leaveGuard = guard;
  },
  useRoute: () => ({ params: { assessmentId: '12' } }),
  useRouter: () => ({ push: routerMocks.push }),
}));
vi.mock('@/services/diagnostics', () => ({
  discardAssessment: vi.fn(),
  fetchAssessment: vi.fn(),
  fetchAssessmentResult: vi.fn(),
  saveAssessmentResponse: vi.fn(),
  startAssessment: vi.fn(),
  submitAssessment: vi.fn(),
}));

const questions = [
  { assessment_question_id: 1, order_index: 0, question_type: 'single_choice' as const, stem: '请分析 x86-64 表达式 16(%rbx,%rcx,4) 与 movq %rax, %rbx，并判断 x < 0U && test S2, S1 时的结果。', options: [{ key: 'A', text: '这是一个包含中文、EnglishTermWithoutAnyBreakOpportunity1234567890 和逻辑运算符 || 的超长选项' }, { key: 'B', text: '乙' }], difficulty: 'easy' as const, saved_answer: null },
  { assessment_question_id: 2, order_index: 1, question_type: 'true_false' as const, stem: '判断题干', options: [{ key: 'TRUE', text: '正确' }, { key: 'FALSE', text: '错误' }], difficulty: 'medium' as const, saved_answer: null },
  { assessment_question_id: 3, order_index: 2, question_type: 'multiple_choice' as const, stem: '多选题干', options: [{ key: 'A', text: '甲' }, { key: 'B', text: '乙' }, { key: 'C', text: '丙' }], difficulty: 'hard' as const, saved_answer: null },
];

describe('DiagnosticAssessmentView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    routerMocks.leaveGuard = undefined;
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

  it('keeps the complete long stem and option available while answering', async () => {
    const wrapper = mount(DiagnosticAssessmentView);
    await flushPromises();

    expect(wrapper.get('.question-card h2').text()).toContain('16(%rbx,%rcx,4)');
    expect(wrapper.get('.question-card h2').text()).toContain('x < 0U && test S2, S1');
    expect(wrapper.text()).toContain('EnglishTermWithoutAnyBreakOpportunity1234567890');
    expect(wrapper.find('.review-title').exists()).toBe(false);
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

  it('offers save, discard, and continue actions before leaving an unfinished diagnosis', async () => {
    vi.mocked(discardAssessment).mockResolvedValue({ assessment_id: 12, discarded: true });
    const wrapper = mount(DiagnosticAssessmentView, { attachTo: document.body });
    await flushPromises();

    await wrapper.get('.back-link').trigger('click');
    await flushPromises();
    expect(document.body.textContent).toContain('确定退出本次诊断？');
    expect(document.body.textContent).toContain('保存并退出');
    expect(document.body.textContent).toContain('放弃本次作答');
    expect(document.body.textContent).toContain('继续答题');

    const continueButton = [...document.body.querySelectorAll('button')]
      .find((button) => button.textContent?.includes('继续答题')) as HTMLButtonElement;
    continueButton.click();
    await flushPromises();
    expect(discardAssessment).not.toHaveBeenCalled();
    expect(routerMocks.push).not.toHaveBeenCalled();

    await wrapper.get('.back-link').trigger('click');
    await flushPromises();
    const discardButton = [...document.body.querySelectorAll('button')]
      .find((button) => button.textContent?.includes('放弃本次作答')) as HTMLButtonElement;
    discardButton.click();
    await flushPromises();
    expect(discardAssessment).toHaveBeenCalledTimes(1);
    expect(routerMocks.push).toHaveBeenCalledWith('/diagnose');
    wrapper.unmount();
  });

  it('blocks route navigation until save and exit succeeds', async () => {
    let rejectSave!: (error: Error) => void;
    vi.mocked(saveAssessmentResponse).mockImplementationOnce(() => new Promise((_resolve, reject) => {
      rejectSave = reject;
    }));
    const wrapper = mount(DiagnosticAssessmentView, { attachTo: document.body });
    await flushPromises();
    await wrapper.findAll('.el-radio')[0]!.trigger('click');
    await Promise.resolve();

    expect(routerMocks.leaveGuard?.({ fullPath: '/courses' })).toBe(false);
    await flushPromises();
    const saveButton = [...document.body.querySelectorAll('button')]
      .find((button) => button.textContent?.includes('保存并退出')) as HTMLButtonElement;
    saveButton.click();
    rejectSave(new Error('offline'));
    await flushPromises();
    expect(routerMocks.push).not.toHaveBeenCalled();
    expect(document.body.textContent).toContain('确定退出本次诊断？');
    wrapper.unmount();
  });

  it('waits for the saved answer before leaving through save and exit', async () => {
    let releaseSave!: () => void;
    vi.mocked(saveAssessmentResponse).mockImplementationOnce(() => new Promise((resolve) => {
      releaseSave = () => resolve({
        assessment_question_id: 1,
        selected_options: ['A'],
        answered_at: 'now',
      });
    }));
    const wrapper = mount(DiagnosticAssessmentView, { attachTo: document.body });
    await flushPromises();
    await wrapper.findAll('.el-radio')[0]!.trigger('click');
    await wrapper.get('.back-link').trigger('click');
    await flushPromises();
    const saveButton = [...document.body.querySelectorAll('button')]
      .find((button) => button.textContent?.includes('保存并退出')) as HTMLButtonElement;
    saveButton.click();
    await Promise.resolve();
    expect(routerMocks.push).not.toHaveBeenCalled();

    releaseSave();
    await flushPromises();
    expect(routerMocks.push).toHaveBeenCalledWith('/diagnose');
    wrapper.unmount();
  });
});
