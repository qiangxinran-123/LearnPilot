import { flushPromises, mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { createCourse, fetchCourses } from '@/services/courses';
import CoursesView from '@/views/CoursesView.vue';

const mockedPush = vi.hoisted(() => vi.fn());

vi.mock('@/services/courses', () => ({
  fetchCourses: vi.fn(),
  createCourse: vi.fn(),
}));

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: mockedPush }),
}));

const mockedFetchCourses = vi.mocked(fetchCourses);
const mockedCreateCourse = vi.mocked(createCourse);

function mountCoursesView() {
  const pinia = createPinia();
  setActivePinia(pinia);

  return mount(CoursesView, {
    global: {
      plugins: [pinia],
      stubs: {
        RouterLink: {
          template: '<a><slot /></a>',
        },
      },
    },
  });
}

describe('CoursesView', () => {
  beforeEach(() => {
    mockedFetchCourses.mockReset();
    mockedCreateCourse.mockReset();
    mockedPush.mockReset();
  });

  it('renders actual courses returned by the API client', async () => {
    mockedFetchCourses.mockResolvedValue({
      count: 1,
      courses: [
        {
          id: 7,
          name: '线性代数',
          description: '向量、矩阵与线性变换。',
          semester: '2026 秋季',
        },
      ],
    });

    const wrapper = mountCoursesView();
    await flushPromises();

    expect(wrapper.text()).toContain('线性代数');
    expect(wrapper.text()).toContain('向量、矩阵与线性变换。');
    expect(wrapper.text()).toContain('2026 秋季');
  });

  it('renders the empty state when the API returns no courses', async () => {
    mockedFetchCourses.mockResolvedValue({ count: 0, courses: [] });

    const wrapper = mountCoursesView();
    await flushPromises();

    expect(wrapper.text()).toContain('开始你的第一门课程');
  });

  it('renders a recoverable error state when the API request fails', async () => {
    mockedFetchCourses.mockRejectedValue(new Error('offline'));

    const wrapper = mountCoursesView();
    await flushPromises();

    expect(wrapper.text()).toContain('课程加载失败');
    expect(wrapper.findAll('button').some((button) => button.text() === '重新加载')).toBe(true);
  });

  it('opens the newly created course with the ID returned by the API', async () => {
    mockedFetchCourses.mockResolvedValue({ count: 0, courses: [] });
    mockedCreateCourse.mockResolvedValue({ id: 23, name: '离散数学', description: '' });

    const wrapper = mountCoursesView();
    await flushPromises();

    wrapper.findComponent({ name: 'CourseFormDialog' }).vm.$emit('submit', { name: '离散数学' });
    await flushPromises();

    expect(mockedCreateCourse).toHaveBeenCalledWith({ name: '离散数学' });
    expect(mockedPush).toHaveBeenCalledWith({
      name: 'course-detail',
      params: { courseId: 23 },
    });
  });

  it('keeps the create dialog open when creation fails', async () => {
    mockedFetchCourses.mockResolvedValue({ count: 0, courses: [] });
    mockedCreateCourse.mockRejectedValue(new Error('offline'));

    const wrapper = mountCoursesView();
    await flushPromises();
    const dialog = wrapper.findComponent({ name: 'CourseFormDialog' });

    await dialog.vm.$emit('update:modelValue', true);
    await dialog.find('input').setValue('离散数学');
    await dialog.find('form').trigger('submit');
    await flushPromises();

    expect(dialog.props('modelValue')).toBe(true);
    expect(dialog.find('input').element.value).toBe('离散数学');
    expect(mockedPush).not.toHaveBeenCalled();
  });
});
