import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import DiagnoseView from '@/views/DiagnoseView.vue';
import { fetchCourses } from '@/services/courses';
import { createOrResumeAssessment, fetchAssessments, fetchDiagnosticReadiness } from '@/services/diagnostics';

const push = vi.fn();
vi.mock('vue-router', () => ({ useRouter: () => ({ push }) }));
vi.mock('@/services/courses', () => ({ fetchCourses: vi.fn() }));
vi.mock('@/services/diagnostics', () => ({
  createOrResumeAssessment: vi.fn(),
  fetchAssessments: vi.fn(),
  fetchDiagnosticReadiness: vi.fn(),
}));

const course = { id: 3, name: '离散数学', description: '集合、关系与图论' };
const ready = {
  course_id: 3,
  status: 'ready' as const,
  can_start: true,
  estimated_question_count: 8,
  estimated_minutes: 10,
  eligible_knowledge_nodes: 4,
  covered_knowledge_nodes: 4,
  available_questions: 12,
  required_questions: 8,
  reason_code: null,
  message: 'ready',
};

describe('DiagnoseView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchCourses).mockResolvedValue({ count: 1, courses: [course] });
    vi.mocked(fetchAssessments).mockResolvedValue({ count: 0, assessments: [] });
    vi.mocked(fetchDiagnosticReadiness).mockResolvedValue(ready);
  });

  it('loads real courses, readiness, creates an assessment and routes to it', async () => {
    vi.mocked(createOrResumeAssessment).mockResolvedValue({
      id: 19,
      course_id: 3,
      course_name: course.name,
      status: 'ready',
      questions: [],
      question_count: 8,
      answered_count: 0,
      created_at: '2026-10-17T10:00:00Z',
      started_at: null,
      submitted_at: null,
    });
    const wrapper = mount(DiagnoseView);
    await flushPromises();
    expect(wrapper.text()).toContain('诊断已就绪');
    expect(wrapper.text()).toContain('8 题');
    await wrapper.get('button.el-button--primary').trigger('click');
    await flushPromises();
    expect(createOrResumeAssessment).toHaveBeenCalledWith(3);
    expect(push).toHaveBeenCalledWith({ name: 'diagnostic-assessment', params: { assessmentId: 19 } });
  });

  it('shows insufficient bank facts without enabling a low-quality start', async () => {
    vi.mocked(fetchDiagnosticReadiness).mockResolvedValue({
      ...ready,
      status: 'question_bank_insufficient',
      can_start: false,
      estimated_question_count: null,
      estimated_minutes: null,
      available_questions: 6,
      covered_knowledge_nodes: 2,
      reason_code: 'QUESTION_BANK_INSUFFICIENT',
    });
    const wrapper = mount(DiagnoseView);
    await flushPromises();
    expect(wrapper.text()).toContain('诊断题目尚不充足');
    expect(wrapper.text()).toContain('已有 6 道合格题');
    expect(wrapper.text()).not.toContain('开始初始诊断');
  });

  it('renders history and resumes an unfinished assessment', async () => {
    vi.mocked(fetchAssessments).mockResolvedValue({
      count: 1,
      assessments: [{
        id: 8,
        course_id: 3,
        course_name: course.name,
        status: 'in_progress',
        question_count: 8,
        answered_count: 2,
        correct_questions: null,
        accuracy: null,
        created_at: '2026-10-17T10:00:00Z',
        submitted_at: null,
      }],
    });
    const wrapper = mount(DiagnoseView);
    await flushPromises();
    expect(wrapper.text()).toContain('继续诊断');
    const continueButton = wrapper.findAll('button').find((button) => button.text() === '继续诊断');
    await continueButton?.trigger('click');
    expect(push).toHaveBeenCalledWith({ name: 'diagnostic-assessment', params: { assessmentId: 8 } });
  });
});
