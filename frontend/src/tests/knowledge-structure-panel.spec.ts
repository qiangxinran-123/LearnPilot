import { defineComponent } from 'vue';
import { flushPromises, mount } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import KnowledgeEdgeDetail from '@/components/knowledge/KnowledgeEdgeDetail.vue';
import KnowledgeNodeDetail from '@/components/knowledge/KnowledgeNodeDetail.vue';
import KnowledgeStructurePanel from '@/components/knowledge/KnowledgeStructurePanel.vue';
import { ApiError } from '@/services/http';
import {
  buildKnowledgeModel,
  fetchKnowledgeModel,
  fetchKnowledgeNodeDetail,
  fetchKnowledgeRelationships,
} from '@/services/knowledge';
import type { Material } from '@/types/course';
import type { KnowledgeBuildStatus, KnowledgeModelResponse } from '@/types/knowledge';

vi.mock('@/services/knowledge', () => ({
  buildKnowledgeModel: vi.fn(),
  fetchKnowledgeModel: vi.fn(),
  fetchKnowledgeNodeDetail: vi.fn(),
  fetchKnowledgeRelationships: vi.fn(),
}));

vi.mock('@/components/knowledge/g6Loader', () => ({
  loadG6Graph: vi.fn(
    async () =>
      class {
        public setData = vi.fn();
        public render = vi.fn(async () => undefined);
        public fitView = vi.fn(async () => undefined);
        public zoomBy = vi.fn(async () => undefined);
        public zoomTo = vi.fn(async () => undefined);
        public resize = vi.fn();
        public destroy = vi.fn();
        public on = vi.fn();
      },
  ),
}));

const DrawerStub = defineComponent({
  props: ['modelValue'],
  emits: ['update:modelValue'],
  template: '<aside v-if="modelValue"><slot /></aside>',
});

const baseModel: KnowledgeModelResponse = {
  course_id: 7,
  nodes: [
    {
      id: 1,
      course_id: 7,
      name: '向量',
      normalized_name: '向量',
      description: '描述向量空间中的基本对象。',
      importance: 'high',
      difficulty: 'basic',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
    {
      id: 2,
      course_id: 7,
      name: '线性变换',
      normalized_name: '线性变换',
      description: '描述线性映射。',
      importance: 'medium',
      difficulty: 'intermediate',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
  ],
  edges: [
    {
      id: 21,
      course_id: 7,
      source_node_id: 1,
      target_node_id: 2,
      relation_type: 'contains',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
    {
      id: 22,
      course_id: 7,
      source_node_id: 1,
      target_node_id: 2,
      relation_type: 'prerequisite',
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    },
  ],
};

const materials: Material[] = [
  {
    id: 31,
    course_id: 7,
    title: '线性代数讲义',
    type: 'document',
    summary: '',
    size_bytes: 100,
    storage_status: 'stored',
    text_preview: '',
    text_length: 10,
    extracted: true,
    extraction_status: 'SUCCESS' as const,
    page_count: 1,
  },
];

function mockedServices() {
  return {
    build: vi.mocked(buildKnowledgeModel),
    model: vi.mocked(fetchKnowledgeModel),
    node: vi.mocked(fetchKnowledgeNodeDetail),
    relationships: vi.mocked(fetchKnowledgeRelationships),
  };
}

const baseStatus: KnowledgeBuildStatus = {
  course_id: 7,
  state: 'update_available',
  stage: null,
  job_id: null,
  material_count: 1,
  ready_material_count: 1,
  node_count: 2,
  contains_edge_count: 1,
  prerequisite_edge_count: 1,
  needs_update: true,
  can_build: true,
  has_model: true,
  error_code: null,
  error_message: null,
  started_at: null,
  completed_at: null,
};

async function mountPanel(
  overrides: Partial<{
    model: KnowledgeModelResponse | null;
    modelState: 'loading' | 'ready' | 'error';
    modelError: string;
    status: KnowledgeBuildStatus | null;
    isRunning: boolean;
    materials: Material[];
  }> = {},
) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/courses/:courseId', name: 'course-detail', component: { template: '<div />' } },
      {
        path: '/courses/:courseId/knowledge/:nodeId',
        name: 'knowledge-detail',
        component: { template: '<div />' },
      },
    ],
  });
  await router.push('/courses/7?tab=knowledge-structure');
  await router.isReady();
  const wrapper = mount(KnowledgeStructurePanel, {
    props: {
      courseId: 7,
      materials,
      model: baseModel,
      modelState: 'ready',
      modelError: '',
      status: baseStatus,
      isRunning: false,
      ...overrides,
    },
    global: { plugins: [router] },
  });
  await flushPromises();
  await flushPromises();
  return { wrapper, router };
}

describe('KnowledgeStructurePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    const services = mockedServices();
    services.model.mockResolvedValue(baseModel);
    services.relationships.mockRejectedValue(
      new ApiError('关系尚未建立。', { code: 'KNOWLEDGE_RELATIONSHIP_NOT_READY', status: 409 }),
    );
  });

  it('shows a truthful empty state when no canonical nodes exist', async () => {
    const { wrapper } = await mountPanel({
      model: { ...baseModel, nodes: [], edges: [] },
      status: { ...baseStatus, state: 'not_built', node_count: 0, has_model: false },
    });

    expect(wrapper.text()).toContain('当前课程暂无已确认的知识点');
    expect(wrapper.text()).toContain('生成课程知识结构');
  });

  it('shows a recoverable loading error when the model request fails', async () => {
    const { wrapper } = await mountPanel({
      model: null,
      modelState: 'error',
      modelError: '服务暂不可用。',
    });
    expect(wrapper.text()).toContain('课程知识结构加载失败');
    await wrapper
      .findAll('button')
      .find((button) => button.text().includes('重试'))
      ?.trigger('click');
    expect(wrapper.emitted('retry')).toHaveLength(1);
  });

  it('allows a legacy extracted M2 material to start the build flow', async () => {
    const { wrapper } = await mountPanel({
      materials: [{ ...materials[0]!, extraction_status: 'EXTRACTED' as const }],
    });
    const buildButton = wrapper
      .findAll('button')
      .find((button) => button.text().includes('更新知识结构'));

    expect(buildButton?.attributes('disabled')).toBeUndefined();
    await buildButton?.trigger('click');
    expect(wrapper.emitted('build')).toHaveLength(1);
  });

  it('renders one unified map and focuses nodes without leaving the course', async () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    const { wrapper, router } = await mountPanel();
    expect(wrapper.text()).toContain('课程知识地图');
    expect(wrapper.text()).toContain('课程知识导航');
    expect(wrapper.text()).toContain('直接学习关系');
    expect(wrapper.text()).not.toContain('层级视图');
    expect(wrapper.text()).not.toContain('关系图视图');
    expect(wrapper.text()).toContain('1 条层级关系');
    expect(wrapper.text()).toContain('1 条先修关系');
    const navigatorNode = wrapper.findAll('.knowledge-navigator__node')[1]!;
    expect(navigatorNode.element.tagName).toBe('BUTTON');
    await navigatorNode.trigger('click');
    await flushPromises();
    expect(router.currentRoute.value.name).toBe('course-detail');
    expect(router.currentRoute.value.query.nodeId).toBe('2');
    expect(wrapper.find('.knowledge-preview h3').text()).toBe('线性变换');
    expect(scrollIntoView).not.toHaveBeenCalled();
  });

  it('uses a valid URL nodeId and safely replaces an invalid one', async () => {
    const { wrapper, router } = await mountPanel();
    await router.replace('/courses/7?tab=knowledge-structure&nodeId=2');
    await flushPromises();
    expect(wrapper.find('.knowledge-preview h3').text()).toBe('线性变换');

    await router.replace('/courses/7?tab=knowledge-structure&nodeId=999');
    await flushPromises();
    expect(router.currentRoute.value.query.nodeId).toBe('1');
    expect(wrapper.find('.knowledge-preview h3').text()).toBe('向量');
  });

  it('searches and clears canonical nodes in the left navigator', async () => {
    const { wrapper } = await mountPanel();
    const input = wrapper.find('input[type="search"]');
    await input.setValue('线性变换');
    expect(wrapper.text()).toContain('找到 1 个匹配项');
    await wrapper.find('.knowledge-navigator__search button').trigger('click');
    expect((input.element as HTMLInputElement).value).toBe('');
  });

  it('opens full detail only through the explicit preview link', async () => {
    const { wrapper } = await mountPanel();
    const detailLink = wrapper.find('.knowledge-preview__detail');
    expect(detailLink.attributes('href')).toBe('/courses/7/knowledge/1?from=knowledge-structure');
  });

  it('keeps the current model visible when an update fails', async () => {
    const { wrapper } = await mountPanel({
      status: {
        ...baseStatus,
        state: 'update_failed',
        error_message: '生成服务暂不可用。',
      },
    });
    expect(wrapper.text()).toContain('2 个知识点');
    expect(wrapper.text()).toContain('生成服务暂不可用。');
    expect(wrapper.text()).toContain('重试更新');
  });

  it('reports a refresh failure after a build without claiming the update succeeded', async () => {
    const { wrapper } = await mountPanel({
      modelError: '最新模型暂时不可读取。',
    });
    expect(wrapper.text()).toContain('当前仍展示已读取的知识结构');
    expect(wrapper.text()).toContain('最新模型暂时不可读取。');
    expect(wrapper.text()).toContain('2 个知识点');
  });
});

describe('knowledge detail drawers', () => {
  it('renders node provenance with a real material title and bounded excerpt control', () => {
    const wrapper = mount(KnowledgeNodeDetail, {
      props: {
        modelValue: true,
        materials,
        detail: {
          node: baseModel.nodes[0]!,
          sources: [
            {
              id: 41,
              knowledge_node_id: 1,
              material_id: 31,
              source_reference: '第 2 页',
              excerpt: '向量是具有大小和方向的数学对象。',
              created_at: '2026-01-01T00:00:00Z',
            },
          ],
          related_edges: [],
        },
      },
      global: { stubs: { 'el-drawer': DrawerStub } },
    });

    expect(wrapper.text()).toContain('描述向量空间中的基本对象。');
    expect(wrapper.text()).toContain('线性代数讲义');
    expect(wrapper.text()).toContain('第 2 页');
    expect(wrapper.text()).toContain('展开摘录');
  });

  it('states contains and prerequisite directions explicitly without invented evidence', () => {
    const containsWrapper = mount(KnowledgeEdgeDetail, {
      props: {
        modelValue: true,
        edge: baseModel.edges[0]!,
        nodes: baseModel.nodes,
        evidence: [],
        materials,
      },
      global: { stubs: { 'el-drawer': DrawerStub } },
    });
    const prerequisiteWrapper = mount(KnowledgeEdgeDetail, {
      props: {
        modelValue: true,
        edge: { ...baseModel.edges[0]!, relation_type: 'prerequisite' },
        nodes: baseModel.nodes,
        evidence: [],
        materials,
      },
      global: { stubs: { 'el-drawer': DrawerStub } },
    });

    expect(containsWrapper.text()).toContain('层级关系');
    expect(containsWrapper.text()).toContain('向量”包含或统摄“线性变换');
    expect(prerequisiteWrapper.text()).toContain('先修关系');
    expect(prerequisiteWrapper.text()).toContain('学习“线性变换”前，需要先掌握“向量”');
    expect(prerequisiteWrapper.text()).toContain('暂未记录可展示的生成依据');
  });
});
