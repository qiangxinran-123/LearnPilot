import { defineComponent } from 'vue';
import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import CourseOverview from '@/components/knowledge/CourseOverview.vue';
import { fetchCanonicalNodes } from '@/services/knowledge';
import type { Material } from '@/types/course';
import type { KnowledgeBuildStatus, KnowledgeNode } from '@/types/knowledge';

vi.mock('@/services/knowledge', () => ({ fetchCanonicalNodes: vi.fn() }));

const LinkStub = defineComponent({
  props: ['to'],
  template: '<a :href="to"><slot /></a>',
});

const materials: Material[] = [
  {
    id: 31,
    course_id: 7,
    title: '讲义一',
    type: 'document',
    summary: '',
    size_bytes: 100,
    storage_status: 'stored',
    text_preview: '',
    text_length: 100,
    extracted: true,
    extraction_status: 'SUCCESS',
    page_count: 1,
  },
  {
    id: 32,
    course_id: 7,
    title: '讲义二',
    type: 'document',
    summary: '',
    size_bytes: 100,
    storage_status: 'stored',
    text_preview: '',
    text_length: 100,
    extracted: true,
    extraction_status: 'SUCCESS',
    page_count: 1,
  },
];

const nodes: KnowledgeNode[] = Array.from({ length: 30 }, (_, index) => ({
  id: index + 1,
  course_id: 7,
  name: index === 0 ? '导数' : `知识点 ${index + 1}`,
  normalized_name: index === 0 ? '导数' : `知识点 ${index + 1}`,
  description: index === 0 ? '函数变化率。' : '',
  importance: 'medium',
  difficulty: 'basic',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
}));

function status(overrides: Partial<KnowledgeBuildStatus> = {}): KnowledgeBuildStatus {
  return {
    course_id: 7,
    state: 'ready',
    stage: null,
    job_id: null,
    material_count: 2,
    ready_material_count: 2,
    synced_material_count: 2,
    pending_sync_material_count: 0,
    pending_parse_material_count: 0,
    failed_material_count: 0,
    last_added_node_count: 0,
    last_reused_node_count: 30,
    node_count: 30,
    contains_edge_count: 2,
    prerequisite_edge_count: 1,
    needs_update: false,
    can_build: true,
    has_model: true,
    error_code: null,
    error_message: null,
    started_at: null,
    completed_at: null,
    ...overrides,
  };
}

function mockPage(sourceNodes = nodes): void {
  vi.mocked(fetchCanonicalNodes).mockImplementation(async (courseId, options = {}) => {
    const query = options.query?.trim() ?? '';
    const offset = options.offset ?? 0;
    const limit = options.limit ?? 8;
    const filtered = sourceNodes.filter((node) => node.name.includes(query));
    return {
      course_id: courseId,
      total: filtered.length,
      offset,
      limit,
      nodes: filtered.slice(offset, offset + limit),
    };
  });
}

async function mountOverview({ attachTo }: { attachTo?: HTMLElement } = {}) {
  const wrapper = mount(CourseOverview, {
    props: {
      courseId: 7,
      materials,
      status: status(),
      statusState: 'ready',
      statusError: '',
      buildError: '',
      isRunning: false,
    },
    attachTo,
    global: { stubs: { RouterLink: LinkStub } },
  });
  await new Promise((resolve) => setTimeout(resolve, 5));
  await flushPromises();
  return wrapper;
}

async function waitForSearch(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 250));
  await flushPromises();
}

describe('CourseOverview', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockPage();
  });

  it('renders three real stats and the three permanent learning task cards, without student state', async () => {
    const wrapper = await mountOverview();

    expect(wrapper.findAll('.overview-stat strong').map((element) => element.text())).toEqual([
      '2',
      '30',
      '3',
    ]);
    expect(wrapper.findAll('.overview-action').map((element) => element.text())).toEqual([
      expect.stringContaining('理解课程资料'),
      expect.stringContaining('查找知识点'),
      expect.stringContaining('了解课程结构'),
    ]);
    expect(wrapper.text()).not.toMatch(/掌握度|学习进度|智能推荐/);
    expect(fetchCanonicalNodes).toHaveBeenCalledWith(7, {
      query: '',
      offset: 0,
      limit: 6,
    });
  });

  it('activates materials and structure cards, and focuses the knowledge search card', async () => {
    const wrapper = await mountOverview({ attachTo: document.body });
    const cards = wrapper.findAll('.overview-action');

    await cards[0]?.trigger('click');
    await cards[2]?.trigger('click');
    await cards[1]?.trigger('click');

    expect(wrapper.emitted('materials')).toHaveLength(1);
    expect(wrapper.emitted('structure')).toHaveLength(1);
    expect(document.activeElement).toBe(wrapper.find('input[type="search"]').element);
    wrapper.unmount();
  });

  it('searches the current course, shows no-result feedback, and restores the default list when cleared', async () => {
    const wrapper = await mountOverview();
    const searchInput = wrapper.find('input[type="search"]');

    await searchInput.setValue('导数');
    await waitForSearch();
    expect(fetchCanonicalNodes).toHaveBeenLastCalledWith(7, {
      query: '导数',
      offset: 0,
      limit: 6,
    });
    expect(wrapper.findAll('.overview-node')).toHaveLength(1);
    expect(wrapper.text()).toContain('函数变化率。');

    await searchInput.setValue('不存在的概念');
    await waitForSearch();
    expect(wrapper.text()).toContain('没有找到匹配的课程知识点');

    await searchInput.setValue('');
    await waitForSearch();
    expect(wrapper.findAll('.overview-node')).toHaveLength(6);
  });

  it('shows an honest empty state when no canonical nodes exist', async () => {
    mockPage([]);
    const wrapper = await mountOverview();

    expect(wrapper.text()).toContain('当前课程暂无已确认的知识点');
    expect(wrapper.findAll('.overview-node')).toHaveLength(0);
    expect(wrapper.find('.overview-link').exists()).toBe(false);
  });

  it('opens a bounded full list with pagination instead of loading every node at once', async () => {
    const wrapper = await mountOverview();

    expect(wrapper.findAll('.overview-node')).toHaveLength(6);
    await wrapper.find('.overview-link').trigger('click');
    await new Promise((resolve) => setTimeout(resolve, 5));
    await flushPromises();
    expect(fetchCanonicalNodes).toHaveBeenLastCalledWith(7, {
      query: '',
      offset: 0,
      limit: 24,
    });
    expect(wrapper.findAll('.overview-node')).toHaveLength(24);

    const nextButton = wrapper.findAll('button').find((button) => button.text().includes('下一页'));
    await nextButton?.trigger('click');
    await flushPromises();
    expect(fetchCanonicalNodes).toHaveBeenLastCalledWith(7, {
      query: '',
      offset: 24,
      limit: 24,
    });
    expect(wrapper.findAll('.overview-node')).toHaveLength(6);
  });

  it('links directly from each real canonical node to its course-scoped detail route', async () => {
    const wrapper = await mountOverview();
    const link = wrapper.find('.overview-node__link');

    expect(link.text()).toContain('查看知识详情');
    expect(link.attributes('href')).toBe('/courses/7/knowledge/1?from=overview');
    expect(wrapper.findAll('.overview-node')).toHaveLength(6);
  });
});
