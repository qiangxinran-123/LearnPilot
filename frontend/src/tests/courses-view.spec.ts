import { flushPromises, mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { fetchCourses } from '@/services/courses';
import CoursesView from '@/views/CoursesView.vue';

vi.mock('@/services/courses', () => ({
  fetchCourses: vi.fn(),
}));

const mockedFetchCourses = vi.mocked(fetchCourses);

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
});
