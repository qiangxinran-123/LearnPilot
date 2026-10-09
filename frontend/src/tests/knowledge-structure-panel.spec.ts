import { defineComponent } from 'vue';
import { flushPromises, mount } from '@vue/test-utils';
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
import type { KnowledgeModelResponse } from '@/types/knowledge';

vi.mock('@/services/knowledge', () => ({
  buildKnowledgeModel: vi.fn(),
  fetchKnowledgeModel: vi.fn(),
  fetchKnowledgeNodeDetail: vi.fn(),
  fetchKnowledgeRelationships: vi.fn(),
}));

vi.mock('@/components/knowledge/g6Loader', () => ({
  loadG6Graph: vi.fn(async () =>
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

async function mountPanel(panelMaterials: Material[] = materials) {
  const wrapper = mount(KnowledgeStructurePanel, {
    props: { courseId: 7, materials: panelMaterials },
  });
  await flushPromises();
  await flushPromises();
  return wrapper;
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
    mockedServices().model.mockResolvedValue({ ...baseModel, nodes: [], edges: [] });

    const wrapper = await mountPanel();

    expect(wrapper.text()).toContain('尚未建立课程知识结构');
    expect(wrapper.text()).toContain('建立知识结构');
  });

  it('shows a recoverable loading error when the model request fails', async () => {
    mockedServices().model.mockRejectedValue(new ApiError('服务暂不可用。', { status: 500 }));

    const wrapper = await mountPanel();

    expect(wrapper.text()).toContain('课程知识结构加载失败');
    expect(wrapper.text()).toContain('重新加载');
  });

  it('allows a legacy extracted M2 material to start the build flow', async () => {
    const services = mockedServices();
    services.build.mockResolvedValue({
      course_id: 7,
      material_count: 1,
      node_count: 2,
      contains_edge_count: 1,
      prerequisite_edge_count: 0,
      reused: true,
    });
    const legacyMaterials = [{ ...materials[0]!, extraction_status: 'EXTRACTED' as const }];

    const wrapper = await mountPanel(legacyMaterials);
    const buildButton = wrapper.findAll('button').find((button) => button.text().includes('更新知识结构'));

    expect(buildButton?.attributes('disabled')).toBeUndefined();
    await buildButton?.trigger('click');
    await flushPromises();
    expect(services.build).toHaveBeenCalledTimes(1);
  });

  it('builds once, refreshes the model, and keeps the UI in the course context', async () => {
    const services = mockedServices();
    services.build.mockResolvedValue({
      course_id: 7,
      material_count: 1,
      node_count: 2,
      contains_edge_count: 1,
      prerequisite_edge_count: 0,
      reused: false,
    });
    services.model.mockResolvedValue(baseModel);

    const wrapper = await mountPanel();
    const buildButton = wrapper.findAll('button').find((button) => button.text().includes('更新知识结构'));

    expect(buildButton).toBeDefined();
    await buildButton?.trigger('click');
    await flushPromises();

    expect(services.build).toHaveBeenCalledTimes(1);
    expect(services.model.mock.calls.length).toBeGreaterThanOrEqual(2);
    expect(wrapper.text()).toContain('课程知识结构');
  });

  it('keeps the current model visible when an update fails', async () => {
    const services = mockedServices();
    services.build.mockRejectedValue(new ApiError('生成服务暂不可用。', { status: 502 }));

    const wrapper = await mountPanel();
    const buildButton = wrapper.findAll('button').find((button) => button.text().includes('更新知识结构'));

    expect(wrapper.findAll('.knowledge-stat strong')[0]?.text()).toBe('2');

    await buildButton?.trigger('click');
    await flushPromises();

    expect(wrapper.text()).toContain('更新知识结构失败，当前结果已保留');
    expect(wrapper.text()).toContain('生成服务暂不可用。');
    expect(wrapper.findAll('.knowledge-stat strong')[0]?.text()).toBe('2');
  });

  it('reports a refresh failure after a build without claiming the update succeeded', async () => {
    const services = mockedServices();
    services.build.mockResolvedValue({
      course_id: 7,
      material_count: 1,
      node_count: 2,
      contains_edge_count: 1,
      prerequisite_edge_count: 0,
      reused: false,
    });
    services.model
      .mockResolvedValueOnce(baseModel)
      .mockRejectedValueOnce(new ApiError('最新模型暂时不可读取。', { status: 503 }));

    const wrapper = await mountPanel();
    const buildButton = wrapper.findAll('button').find((button) => button.text().includes('更新知识结构'));

    await buildButton?.trigger('click');
    await flushPromises();

    expect(wrapper.text()).toContain('更新知识结构失败，当前结果已保留');
    expect(wrapper.text()).toContain('最新模型暂时不可读取。');
    expect(wrapper.findAll('.knowledge-stat strong')[0]?.text()).toBe('2');
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
