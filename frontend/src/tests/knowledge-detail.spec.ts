import { flushPromises, mount } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { fetchCourse } from '@/services/courses';
import { ApiError } from '@/services/http';
import {
  fetchKnowledgeModel,
  fetchKnowledgeNodeDetail,
  fetchKnowledgeRelationships,
} from '@/services/knowledge';
import { fetchMaterials } from '@/services/materials';
import type { Material } from '@/types/course';
import type {
  KnowledgeEdge,
  KnowledgeModelResponse,
  KnowledgeNode,
  KnowledgeNodeDetailResponse,
  KnowledgeRelationshipsResponse,
} from '@/types/knowledge';
import KnowledgeDetailView from '@/views/KnowledgeDetailView.vue';

vi.mock('@/services/courses', () => ({ fetchCourse: vi.fn() }));
vi.mock('@/services/materials', () => ({ fetchMaterials: vi.fn() }));
vi.mock('@/services/knowledge', () => ({
  fetchKnowledgeModel: vi.fn(),
  fetchKnowledgeNodeDetail: vi.fn(),
  fetchKnowledgeRelationships: vi.fn(),
}));

const courseId = 7;
const timestamp = '2026-01-01T00:00:00Z';
function node(id: number, name: string, description = ''): KnowledgeNode {
  return {
    id,
    course_id: courseId,
    name,
    normalized_name: name,
    description,
    importance: 'medium',
    difficulty: 'basic',
    created_at: timestamp,
    updated_at: timestamp,
  };
}
function edge(
  id: number,
  source: number,
  target: number,
  type: KnowledgeEdge['relation_type'],
): KnowledgeEdge {
  return {
    id,
    course_id: courseId,
    source_node_id: source,
    target_node_id: target,
    relation_type: type,
    created_at: timestamp,
    updated_at: timestamp,
  };
}

const nodes = [
  node(1, '线性空间'),
  node(2, '向量', '向量是线性空间中的对象。'),
  node(3, '向量加法'),
  node(4, '集合'),
  node(5, '线性变换'),
];
const edges = [
  edge(11, 1, 2, 'contains'),
  edge(12, 2, 3, 'contains'),
  edge(13, 4, 2, 'prerequisite'),
  edge(14, 2, 5, 'prerequisite'),
];
const model: KnowledgeModelResponse = { course_id: courseId, nodes, edges };
const material: Material = {
  id: 31,
  course_id: courseId,
  title: '线性代数讲义',
  type: 'PDF',
  extension: '.pdf',
  summary: '',
  size_bytes: 1024,
  storage_status: 'STORED',
  text_preview: '',
  text_length: 100,
  extracted: true,
  extraction_status: 'SUCCESS',
  page_count: 2,
};
const nodeDetail: KnowledgeNodeDetailResponse = {
  node: nodes[1]!,
  related_edges: edges,
  sources: [
    {
      id: 61,
      knowledge_node_id: 2,
      material_id: 31,
      source_reference: '第 2 页',
      excerpt: '向量可进行加法运算。',
      created_at: timestamp,
    },
  ],
};
const relationships: KnowledgeRelationshipsResponse = {
  run: {
    id: 10,
    course_id: courseId,
    status: 'success',
    node_count: 5,
    contains_edge_count: 2,
    prerequisite_edge_count: 2,
    is_current: true,
  },
  contains_edges: [
    {
      ...edges[0]!,
      evidence: [
        {
          id: 71,
          knowledge_edge_id: 11,
          course_id: courseId,
          material_id: null,
          source_reference: null,
          excerpt: null,
          evidence_type: 'structural',
          reason: '由课程层级约束得到。',
          created_at: timestamp,
        },
      ],
    },
  ],
  prerequisite_edges: [
    {
      ...edges[2]!,
      evidence: [
        {
          id: 72,
          knowledge_edge_id: 13,
          course_id: courseId,
          material_id: 31,
          source_reference: '第 2 页',
          excerpt: '先学习集合，再理解向量。',
          evidence_type: 'material',
          reason: '原文支持这条先修关系。',
          created_at: timestamp,
        },
      ],
    },
  ],
  reused: false,
};

const mockedCourse = vi.mocked(fetchCourse);
const mockedMaterials = vi.mocked(fetchMaterials);
const mockedModel = vi.mocked(fetchKnowledgeModel);
const mockedDetail = vi.mocked(fetchKnowledgeNodeDetail);
const mockedRelationships = vi.mocked(fetchKnowledgeRelationships);

async function mountDetail(path = '/courses/7/knowledge/2') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      {
        path: '/courses/:courseId/knowledge/:nodeId',
        name: 'knowledge-detail',
        component: KnowledgeDetailView,
      },
      {
        path: '/courses/:courseId/materials/:materialId',
        name: 'material-detail',
        component: { template: '<p>资料</p>' },
      },
      { path: '/courses/:courseId', name: 'course-detail', component: { template: '<p>课程</p>' } },
    ],
  });
  await router.push(path);
  await router.isReady();
  const wrapper = mount(KnowledgeDetailView, { global: { plugins: [router] } });
  await flushPromises();
  return { router, wrapper };
}

describe('KnowledgeDetailView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockedCourse.mockResolvedValue({ id: courseId, name: '线性代数', description: '' });
    mockedMaterials.mockResolvedValue({ course_id: courseId, count: 1, materials: [material] });
    mockedModel.mockResolvedValue(model);
    mockedDetail.mockResolvedValue(nodeDetail);
    mockedRelationships.mockResolvedValue(relationships);
  });

  it('keeps source excerpts and relation evidence collapsed until the user asks for them', async () => {
    const { wrapper } = await mountDetail();

    expect(mockedModel).toHaveBeenCalledWith(courseId, { canonicalOnly: true });
    expect(wrapper.get('h1').text()).toBe('向量');
    expect(wrapper.text()).toContain('向量是线性空间中的对象。');
    expect(wrapper.text()).toContain('线性代数讲义');
    expect(wrapper.text()).toContain('第 2 页');
    expect(wrapper.text()).not.toContain('向量可进行加法运算。');
    expect(wrapper.text()).toContain('知识关联依据');
    expect(wrapper.text()).not.toContain('结构约束说明 · 非资料原文');
    expect(wrapper.text()).not.toContain('原文支持这条先修关系。');
    expect(wrapper.text()).toContain('单资料问答');
    expect(wrapper.get('.knowledge-page__map-link').attributes('href')).toBe(
      '/courses/7?tab=knowledge-structure&nodeId=2',
    );

    const sourceDisclosure = wrapper.get('.knowledge-page__source-list button');
    expect(sourceDisclosure.attributes('aria-expanded')).toBe('false');
    await sourceDisclosure.trigger('click');
    expect(sourceDisclosure.attributes('aria-expanded')).toBe('true');
    expect(wrapper.text()).toContain('知识点来源依据');
    expect(wrapper.text()).toContain('向量可进行加法运算。');
    await sourceDisclosure.trigger('click');
    expect(wrapper.text()).not.toContain('向量可进行加法运算。');

    const relationDisclosure = wrapper.get('.knowledge-page__evidence button');
    expect(relationDisclosure.attributes('aria-expanded')).toBe('false');
    await relationDisclosure.trigger('click');
    expect(wrapper.text()).toContain('结构约束说明 · 非资料原文');
    expect(wrapper.text()).toContain('原文支持这条先修关系。');

    const sourceLink = wrapper.findAll('a').find((link) => link.text().includes('查看资料'));
    expect(sourceLink?.attributes('href')).toContain('/courses/7/materials/31?tab=content&source=');
    expect(
      new URL(sourceLink?.attributes('href') ?? '', 'http://localhost').searchParams.get('source'),
    ).toBe('第 2 页');
  });

  it('keeps CONTAINS hierarchy separate from PREREQUISITE direction and opens related nodes', async () => {
    const { router, wrapper } = await mountDetail();
    const parent = wrapper.get('#relation-parent').element.closest('section')!;
    const child = wrapper.get('#relation-child').element.closest('section')!;
    const prerequisite = wrapper.get('#relation-prerequisite').element.closest('section')!;
    const dependent = wrapper.get('#relation-dependent').element.closest('section')!;

    expect(parent.textContent).toContain('线性空间');
    expect(parent.textContent).not.toContain('集合');
    expect(child.textContent).toContain('向量加法');
    expect(prerequisite.textContent).toContain('集合');
    expect(prerequisite.textContent).not.toContain('线性空间');
    expect(dependent.textContent).toContain('线性变换');
    expect(wrapper.text()).toContain('和哪些知识有关？');
    expect(wrapper.text()).toContain('学习前可以先了解');
    expect(wrapper.text()).toContain('接下来还可以看看');
    expect(wrapper.text()).toContain('属于哪个主题？');
    expect(wrapper.text()).toContain('这个主题包含什么？');
    expect(wrapper.text()).not.toContain('所属上级主题');
    expect(wrapper.text()).not.toContain('先修知识');

    const linkedNode = wrapper.findAll('a').find((link) => link.text().includes('向量加法'));
    await linkedNode?.trigger('click');
    await flushPromises();
    expect(router.currentRoute.value.path).toBe('/courses/7/knowledge/3');
    expect(router.currentRoute.value.query).toEqual({ from: 'overview' });
  });

  it('does not invent explanations, links, or citations when provenance is absent or inaccessible', async () => {
    mockedDetail.mockResolvedValue({
      node: { ...nodes[1]!, description: '' },
      related_edges: [],
      sources: [{ ...nodeDetail.sources[0]!, material_id: 999, source_reference: '第 2 页' }],
    });
    mockedRelationships.mockRejectedValue(
      new ApiError('尚未建立关系', { code: 'KNOWLEDGE_RELATIONSHIP_NOT_READY', status: 409 }),
    );
    const { wrapper } = await mountDetail();

    expect(wrapper.text()).toContain('尚无经过保存的概念说明');
    expect(wrapper.text()).toContain('来源资料已删除或不可访问');
    expect(wrapper.text()).toContain('资料不可访问，无法打开原文');
    expect(wrapper.text()).toContain('当前还没有建立这个知识点与其他知识点的联系');
    expect(wrapper.find('.knowledge-page__evidence').exists()).toBe(false);
    expect(
      wrapper.findAll('a').some((link) => link.attributes('href')?.includes('/materials/999')),
    ).toBe(false);
  });

  it('groups sources by stable material id while preserving every real position', async () => {
    const secondMaterial = { ...material, id: 32, title: '线性代数习题课', extension: '.txt' };
    mockedMaterials.mockResolvedValue({
      course_id: courseId,
      count: 2,
      materials: [material, secondMaterial],
    });
    mockedDetail.mockResolvedValue({
      ...nodeDetail,
      sources: [
        nodeDetail.sources[0]!,
        {
          ...nodeDetail.sources[0]!,
          id: 62,
          source_reference: '第 5 页',
          excerpt: '同一资料中的另一处真实依据。',
        },
        {
          ...nodeDetail.sources[0]!,
          id: 63,
          material_id: 32,
          source_reference: '',
          excerpt: '没有位置字段的真实依据。',
        },
      ],
    });
    const { wrapper } = await mountDetail();

    const sourceGroups = wrapper.findAll('.knowledge-page__source-list > li');
    expect(sourceGroups).toHaveLength(2);
    expect(sourceGroups[0]!.text()).toContain('第 2 页');
    expect(sourceGroups[0]!.text()).toContain('第 5 页');
    expect(sourceGroups[1]!.text()).toContain('线性代数习题课');
    expect(wrapper.text()).not.toContain('第 0 页');
    expect(wrapper.text()).not.toContain('没有位置字段的真实依据。');
    expect(wrapper.findAll('.knowledge-page__source-list button')).toHaveLength(3);
  });

  it('shows a relationship evidence error instead of disguising it as an empty state', async () => {
    mockedRelationships.mockRejectedValue(
      new ApiError('服务暂时不可用', { code: 'INTERNAL_ERROR', status: 500 }),
    );
    const { wrapper } = await mountDetail();

    expect(wrapper.text()).toContain('关系依据暂时无法读取');
    expect(wrapper.find('.knowledge-page__evidence').exists()).toBe(false);
  });

  it('resets disclosure state when navigating directly to another knowledge detail', async () => {
    mockedDetail.mockImplementation((_courseId, id) =>
      Promise.resolve(id === 2 ? nodeDetail : { node: nodes[2]!, related_edges: [], sources: [] }),
    );
    const { router, wrapper } = await mountDetail();
    await wrapper.get('.knowledge-page__source-list button').trigger('click');
    expect(wrapper.text()).toContain('向量可进行加法运算。');

    await router.push('/courses/7/knowledge/3');
    await flushPromises();
    expect(wrapper.get('h1').text()).toBe('向量加法');
    expect(wrapper.text()).not.toContain('向量可进行加法运算。');
    expect(wrapper.text()).toContain('当前知识点尚未记录资料来源');
  });

  it('rejects missing and cross-course nodes without exposing their contents', async () => {
    mockedDetail.mockRejectedValueOnce(new ApiError('Not found', { status: 404 }));
    const missing = await mountDetail();
    expect(missing.wrapper.text()).toContain('知识点不存在或不属于当前课程');

    mockedDetail.mockResolvedValueOnce({ ...nodeDetail, node: { ...nodes[1]!, course_id: 8 } });
    const otherCourse = await mountDetail();
    expect(otherCourse.wrapper.text()).toContain('知识点不存在或不属于当前课程');
    expect(otherCourse.wrapper.text()).not.toContain('向量是线性空间中的对象');
  });

  it('does not let a stale response overwrite a newer node after rapid navigation', async () => {
    let releaseOld: ((value: KnowledgeNodeDetailResponse) => void) | undefined;
    mockedDetail.mockImplementation((_courseId, id) =>
      id === 2
        ? new Promise((resolve) => {
            releaseOld = resolve;
          })
        : Promise.resolve({ node: nodes[2]!, related_edges: [], sources: [] }),
    );
    const { router, wrapper } = await mountDetail();
    await router.push('/courses/7/knowledge/3');
    await flushPromises();
    expect(wrapper.get('h1').text()).toBe('向量加法');

    releaseOld?.(nodeDetail);
    await flushPromises();
    expect(wrapper.get('h1').text()).toBe('向量加法');
  });
});
