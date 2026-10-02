import { defineComponent } from 'vue';
import { flushPromises, mount } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  askMaterialQuestion,
  fetchMaterialCards,
  fetchMaterialSummary,
  generateMaterialCards,
  generateMaterialSummary,
} from '@/services/ai-materials';
import { ApiError } from '@/services/http';
import { deleteMaterial, fetchMaterial, fetchMaterialContent } from '@/services/materials';
import type {
  CardGenerationResponse,
  Material,
  MaterialContentResponse,
  MaterialSummaryResponse,
} from '@/types/course';
import MaterialDetailView from '@/views/MaterialDetailView.vue';

vi.mock('@/services/materials', () => ({
  fetchMaterial: vi.fn(),
  fetchMaterialContent: vi.fn(),
  deleteMaterial: vi.fn(),
}));
vi.mock('@/services/ai-materials', () => ({
  fetchMaterialSummary: vi.fn(),
  fetchMaterialCards: vi.fn(),
  generateMaterialSummary: vi.fn(),
  generateMaterialCards: vi.fn(),
  askMaterialQuestion: vi.fn(),
}));

const fetchDetail = vi.mocked(fetchMaterial);
const fetchContent = vi.mocked(fetchMaterialContent);
const fetchSummary = vi.mocked(fetchMaterialSummary);
const fetchCards = vi.mocked(fetchMaterialCards);
const generateSummary = vi.mocked(generateMaterialSummary);
const generateCards = vi.mocked(generateMaterialCards);
const askQuestion = vi.mocked(askMaterialQuestion);
const removeMaterial = vi.mocked(deleteMaterial);

const material: Material = {
  id: 4,
  course_id: 2,
  title: '缓存讲义',
  type: 'PDF',
  summary: '',
  original_filename: 'lecture.pdf',
  size_bytes: 2048,
  storage_status: 'STORED',
  text_preview: '缓存是高速存储器。',
  text_length: 10,
  extracted: true,
  extraction_status: 'SUCCESS',
  page_count: 1,
  created_at: '2026-09-20T08:00:00Z',
};
const content: MaterialContentResponse = {
  material_id: 4,
  text: '缓存是高速存储器。',
  offset: 0,
  limit: 12_000,
  total_length: 10,
  has_more: false,
  page_count: 1,
  parser_name: 'pymupdf',
  parser_version: '1',
};
const noSummary: MaterialSummaryResponse = {
  id: 4,
  material_id: 4,
  summary: null,
  ai_summary: null,
  summary_generated: false,
  summary_method: null,
  summary_updated_at: null,
};
const noCards: CardGenerationResponse = {
  material_id: 4,
  count: 0,
  cards: [],
  cards_generated: false,
  cards_generated_at: null,
  cards_method: null,
};
const PaneStub = defineComponent({ template: '<section><slot /></section>' });
const ConfirmStub = defineComponent({
  emits: ['confirm'],
  template:
    '<div><slot name="reference" /><button type="button" data-test="confirm-delete" @click="$emit(\'confirm\')">确认删除</button></div>',
});

async function mountDetail() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/courses/:courseId/materials/:materialId', component: MaterialDetailView },
      { path: '/courses/:courseId', component: PaneStub },
    ],
  });
  await router.push('/courses/2/materials/4');
  await router.isReady();
  const wrapper = mount(MaterialDetailView, {
    global: {
      plugins: [router],
      stubs: {
        'el-tabs': PaneStub,
        'el-tab-pane': PaneStub,
        'el-popconfirm': ConfirmStub,
      },
    },
  });
  return { router, wrapper };
}

function ready() {
  fetchDetail.mockResolvedValue(material);
  fetchContent.mockResolvedValue(content);
  fetchSummary.mockResolvedValue(noSummary);
  fetchCards.mockResolvedValue(noCards);
}

describe('MaterialDetailView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    ready();
  });

  it('loads persisted content and empty summary/card states', async () => {
    const { wrapper } = await mountDetail();
    await flushPromises();

    expect(fetchDetail).toHaveBeenCalledWith(4);
    expect(fetchContent).toHaveBeenCalledWith(4);
    expect(fetchSummary).toHaveBeenCalledWith(4);
    expect(fetchCards).toHaveBeenCalledWith(4);
    expect(wrapper.text()).toContain('缓存讲义');
    expect(wrapper.text()).toContain('缓存是高速存储器。');
    expect(wrapper.text()).toContain('尚未生成摘要');
    expect(wrapper.text()).toContain('尚未生成学习卡片');
  });

  it('shows saved summary and cards without regenerating on page load', async () => {
    fetchSummary.mockResolvedValue({
      ...noSummary,
      summary_generated: true,
      summary: {
        overview: '缓存缩短访问时间。',
        key_concepts: ['局部性'],
        important_points: ['热点数据可复用'],
        common_mistakes: [],
        review_suggestions: ['比较缓存与主存'],
        provider: 'mock',
        model: 'deterministic-m2',
        prompt_version: 'summary_v1',
        generated_at: '2026-09-20T08:00:00Z',
        updated_at: '2026-09-20T08:00:00Z',
      },
    });
    fetchCards.mockResolvedValue({
      ...noCards,
      count: 1,
      cards_generated: true,
      cards_method: 'mock',
      cards: [
        {
          id: 11,
          question: '缓存有什么用途？',
          answer: '缩短数据访问时间。',
          knowledge_hint: '存储层次',
          source_reference: '第 1 页',
          order_index: 1,
          source_material_id: 4,
          card_type: 'AI',
          created_at: '2026-09-20T08:00:00Z',
        },
      ],
    });
    const { wrapper } = await mountDetail();
    await flushPromises();

    expect(wrapper.text()).toContain('缓存缩短访问时间。');
    expect(wrapper.text()).toContain('局部性');
    expect(wrapper.text()).toContain('生成来源：mock / deterministic-m2 · summary_v1');
    expect(wrapper.text()).toContain('缓存有什么用途？');
    expect(wrapper.text()).not.toContain('缩短数据访问时间。');
    await wrapper.get('.study-card').trigger('click');
    expect(wrapper.text()).toContain('缩短数据访问时间。');
    expect(wrapper.text()).toContain('来源：第 1 页');
    expect(generateSummary).not.toHaveBeenCalled();
    expect(generateCards).not.toHaveBeenCalled();
  });

  it('keeps the summary empty state visible when AI generation fails', async () => {
    generateSummary.mockRejectedValue(
      new ApiError('请先配置大模型。', { code: 'AI_NOT_CONFIGURED' }),
    );
    const { wrapper } = await mountDetail();
    await flushPromises();

    const button = wrapper
      .findAll('button')
      .find((candidate) => candidate.text().includes('生成摘要'));
    expect(button).toBeDefined();
    await button?.trigger('click');
    await flushPromises();

    expect(generateSummary).toHaveBeenCalledWith(4);
    expect(wrapper.get('.ai-error').text()).toBe('请先配置大模型。');
    expect(wrapper.text()).toContain('尚未生成摘要');
  });

  it('renders a material-grounded answer with its returned reference', async () => {
    askQuestion.mockResolvedValue({
      material_id: 4,
      answer: '缓存用于减少访问延迟。',
      references: ['第 1 页'],
      grounded: true,
      provider: 'mock',
      model: 'deterministic-m2',
      prompt_version: 'material_qa_v1',
    });
    const { wrapper } = await mountDetail();
    await flushPromises();

    await wrapper.get('textarea').setValue('  缓存的用途是什么？  ');
    await wrapper.get('form').trigger('submit');
    await flushPromises();

    expect(askQuestion).toHaveBeenCalledWith(4, '缓存的用途是什么？');
    expect(wrapper.text()).toContain('缓存用于减少访问延迟。');
    expect(wrapper.text()).toContain('第 1 页');
    expect(wrapper.text()).toContain('回答来源：mock / deterministic-m2 · material_qa_v1');
  });

  it('shows parse failure without requesting content or generating new AI artifacts', async () => {
    fetchDetail.mockResolvedValue({
      ...material,
      extracted: false,
      extraction_status: 'PARSE_FAILED',
      extraction_error_message: 'PDF 结构损坏。',
    });
    const { wrapper } = await mountDetail();
    await flushPromises();

    expect(wrapper.text()).toContain('资料解析失败');
    expect(wrapper.text()).toContain('请确认文件完整后重新上传。');
    expect(fetchContent).not.toHaveBeenCalled();
    expect(fetchSummary).toHaveBeenCalledWith(4);
    expect(fetchCards).toHaveBeenCalledWith(4);
    expect(generateSummary).not.toHaveBeenCalled();
    expect(generateCards).not.toHaveBeenCalled();
    expect(askQuestion).not.toHaveBeenCalled();
  });

  it('shows a recoverable material loading error', async () => {
    fetchDetail.mockRejectedValue(new ApiError('资料不存在。', { status: 404 }));
    const { wrapper } = await mountDetail();
    await flushPromises();

    expect(wrapper.text()).toContain('资料加载失败');
    expect(wrapper.text()).toContain('资料不存在。');
    expect(wrapper.text()).toContain('重新加载');
  });

  it('deletes only after confirmation, then returns to the course', async () => {
    removeMaterial.mockResolvedValue({ id: 4, deleted: true });
    const { router, wrapper } = await mountDetail();
    await flushPromises();

    expect(removeMaterial).not.toHaveBeenCalled();
    await wrapper.get('[data-test="confirm-delete"]').trigger('click');
    await flushPromises();

    expect(removeMaterial).toHaveBeenCalledWith(4);
    expect(router.currentRoute.value.fullPath).toBe('/courses/2');
  });
});
