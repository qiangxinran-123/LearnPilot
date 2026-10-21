import { computed, ref } from 'vue';
import { flushPromises, mount } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import CourseDetailView from '@/views/CourseDetailView.vue';
import { fetchCourse } from '@/services/courses';
import { fetchMaterials } from '@/services/materials';
import type { Material } from '@/types/course';

vi.mock('@/services/courses', () => ({
  deleteCourse: vi.fn(),
  fetchCourse: vi.fn(),
  updateCourse: vi.fn(),
}));
vi.mock('@/services/materials', () => ({ fetchMaterials: vi.fn() }));
vi.mock('@/composables/useCourseKnowledgeWorkspace', () => ({
  useCourseKnowledgeWorkspace: () => ({
    status: ref(null),
    model: ref(null),
    statusState: ref('ready'),
    modelState: ref('ready'),
    statusError: ref(''),
    modelError: ref(''),
    buildError: ref(''),
    isRunning: computed(() => false),
    refresh: vi.fn(),
    refreshStatus: vi.fn(),
    refreshModel: vi.fn(),
    startBuild: vi.fn(),
  }),
}));

const materials: Material[] = [
  {
    id: 31,
    course_id: 7,
    title: '已解析讲义',
    type: 'document',
    summary: '',
    size_bytes: 100,
    storage_status: 'STORED',
    text_preview: '',
    text_length: 100,
    extracted: true,
    extraction_status: 'SUCCESS',
    page_count: 1,
  },
  {
    id: 32,
    course_id: 7,
    title: '正在解析的资料',
    type: 'document',
    summary: '',
    size_bytes: 100,
    storage_status: 'STORED',
    text_preview: '',
    text_length: 0,
    extracted: false,
    extraction_status: 'NOT_REQUESTED',
    page_count: 0,
  },
  {
    id: 33,
    course_id: 7,
    title: '解析失败资料',
    type: 'document',
    summary: '',
    size_bytes: 100,
    storage_status: 'STORED',
    text_preview: '',
    text_length: 0,
    extracted: false,
    extraction_status: 'PARSE_FAILED',
    page_count: 0,
  },
];

async function mountCourse() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/courses/:courseId', name: 'course-detail', component: CourseDetailView },
      {
        path: '/courses/:courseId/materials/:materialId',
        name: 'material-detail',
        component: { template: '<div />' },
      },
    ],
  });
  await router.push('/courses/7?tab=materials');
  await router.isReady();
  const wrapper = mount(CourseDetailView, {
    global: {
      plugins: [router],
      stubs: {
        CourseFormDialog: true,
        MaterialUploadDialog: true,
        CourseOverview: true,
      },
    },
  });
  await flushPromises();
  return { router, wrapper };
}

describe('CourseDetailView material AI discoverability', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchCourse).mockResolvedValue({ id: 7, name: '计算机系统', description: '' });
    vi.mocked(fetchMaterials).mockResolvedValue({
      course_id: 7,
      count: materials.length,
      materials,
    });
  });

  it('advertises the existing learning tools only for successfully parsed materials', async () => {
    const { wrapper } = await mountCourse();

    expect(wrapper.text()).toContain('打开资料，可生成摘要、制作学习卡片，并针对内容提问。');
    expect(wrapper.findAll('.material-row__tools')).toHaveLength(1);
    expect(wrapper.text()).toContain('等待解析');
    expect(wrapper.text()).toContain('解析失败');
    expect(
      wrapper.findAll('button').filter((button) => button.text().includes('查看资料与学习工具')),
    ).toHaveLength(3);
  });

  it('keeps the existing material-detail route as the single entry point', async () => {
    const { router, wrapper } = await mountCourse();
    const button = wrapper
      .findAll('button')
      .find((candidate) => candidate.text().includes('查看资料与学习工具'));

    await button?.trigger('click');
    await flushPromises();
    expect(router.currentRoute.value.path).toBe('/courses/7/materials/31');
  });
});
