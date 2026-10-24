import { defineComponent } from 'vue';
import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import DiagnoseView from '@/views/DiagnoseView.vue';
import { fetchCourses } from '@/services/courses';
import { createOrResumeAssessment, fetchAssessments } from '@/services/diagnostics';

const push = vi.fn();
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {} }),
  useRouter: () => ({ push }),
}));
vi.mock('@/services/courses', () => ({ fetchCourses: vi.fn() }));
vi.mock('@/services/diagnostics', () => ({
  createOrResumeAssessment: vi.fn(),
  fetchAssessments: vi.fn(),
}));
vi.mock('@/components/diagnostic/QuestionBankPanel.vue', () => ({
  default: defineComponent({
    props: { courseId: Number, courseName: String },
    emits: ['start', 'knowledge'],
    template: '<div class="bank-stub">{{ courseName }} 题库状态<button @click="$emit(\'start\')">开始诊断</button></div>',
  }),
}));

const course = { id: 3, name: '离散数学', description: '集合、关系与图论' };
describe('DiagnoseView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchCourses).mockResolvedValue({ count: 1, courses: [course] });
    vi.mocked(fetchAssessments).mockResolvedValue({ count: 0, assessments: [] });
  });

  it('loads real courses, mounts the course question-bank workspace, and starts from its event', async () => {
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
    expect(wrapper.text()).toContain('离散数学 题库状态');
    await wrapper.get('.bank-stub button').trigger('click');
    await flushPromises();
    expect(createOrResumeAssessment).toHaveBeenCalledWith(3);
    expect(push).toHaveBeenCalledWith({ name: 'diagnostic-assessment', params: { assessmentId: 19 } });
  });

  it('switches courses without retaining the previous course workspace', async () => {
    vi.mocked(fetchCourses).mockResolvedValue({
      count: 2,
      courses: [course, { id: 4, name: '计算机系统', description: '体系结构' }],
    });
    const wrapper = mount(DiagnoseView);
    await flushPromises();
    expect(wrapper.text()).toContain('离散数学 题库状态');
    const target = wrapper.findAll('.course-list button').find((item) => item.text().includes('计算机系统'));
    await target?.trigger('click');
    expect(wrapper.text()).toContain('计算机系统 题库状态');
    expect(wrapper.text()).not.toContain('离散数学 题库状态');
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
    expect(wrapper.text()).toContain('继续作答');
    expect(wrapper.text()).toContain('已完成');
    expect(wrapper.text()).toContain('2 / 8 题');
    const continueButton = wrapper.findAll('button').find((button) => button.text() === '继续作答');
    await continueButton?.trigger('click');
    expect(push).toHaveBeenCalledWith({ name: 'diagnostic-assessment', params: { assessmentId: 8 } });
  });

  it('keeps an existing draft resumable when the current readiness check fails', async () => {
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

    expect(wrapper.text()).toContain('诊断草稿已保存');
    expect(wrapper.text()).toContain('继续作答');
  });
});
