import { defineComponent } from 'vue';
import { flushPromises, mount } from '@vue/test-utils';
import { createMemoryHistory, createRouter } from 'vue-router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  askMaterialQuestion,
  fetchMaterialCards,
  generateMaterialCards,
} from '@/services/ai-materials';
import { ApiError } from '@/services/http';
import { deleteMaterial, fetchMaterial, fetchMaterialContent } from '@/services/materials';
import type {
  CardGenerationResponse,
  Material,
  MaterialContentResponse,
} from '@/types/course';
import MaterialDetailView from '@/views/MaterialDetailView.vue';

vi.mock('@/services/materials', () => ({
  fetchMaterial: vi.fn(),
  fetchMaterialContent: vi.fn(),
  deleteMaterial: vi.fn(),
}));
vi.mock('@/services/ai-materials', () => ({
  fetchMaterialCards: vi.fn(),
  generateMaterialCards: vi.fn(),
  askMaterialQuestion: vi.fn(),
}));

const fetchDetail = vi.mocked(fetchMaterial);
const fetchContent = vi.mocked(fetchMaterialContent);
const fetchCards = vi.mocked(fetchMaterialCards);
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
  fetchCards.mockResolvedValue(noCards);
}

describe('MaterialDetailView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    ready();
  });

  it('loads persisted content and card state without any summary UI or request', async () => {
    const { wrapper } = await mountDetail();
    await flushPromises();

    expect(fetchDetail).toHaveBeenCalledWith(4);
    expect(fetchContent).toHaveBeenCalledWith(4);
    expect(fetchCards).toHaveBeenCalledWith(4);
    expect(wrapper.text()).toContain('缓存讲义');
    expect(wrapper.text()).toContain('缓存是高速存储器。');
    expect(wrapper.text()).toContain('尚未生成学习卡片');
    expect(wrapper.text()).toContain('从资料中生成便于回顾的问答卡片。');
    expect(wrapper.text()).toContain('围绕当前资料提问，并查看回答依据。');
    expect(wrapper.text()).not.toContain('生成摘要');
    expect(wrapper.text()).not.toContain('核心概览');
    expect(wrapper.text()).not.toContain('刷新摘要状态');
  });

  it('shows saved cards without regenerating on page load', async () => {
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

    expect(wrapper.text()).toContain('缓存有什么用途？');
    expect(wrapper.text()).not.toContain('缩短数据访问时间。');
    const card = wrapper.get('.study-card');
    expect(card.element.tagName).toBe('BUTTON');
    expect(card.attributes('aria-expanded')).toBe('false');
    expect(card.text()).toContain('点击卡片查看答案');
    expect(card.text()).toContain('查看答案');

    const cardButton = card.element as HTMLButtonElement;
    cardButton.focus();
    cardButton.click();
    await wrapper.vm.$nextTick();
    expect(card.attributes('aria-expanded')).toBe('true');
    expect(wrapper.text()).toContain('缩短数据访问时间。');
    expect(card.text()).toContain('点击返回问题');
    expect(card.text()).toContain('返回问题');
    expect(wrapper.text()).toContain('来源：第 1 页');

    cardButton.click();
    await wrapper.vm.$nextTick();
    expect(card.attributes('aria-expanded')).toBe('false');
    expect(wrapper.text()).not.toContain('缩短数据访问时间。');
    expect(generateCards).not.toHaveBeenCalled();
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
    expect(fetchCards).toHaveBeenCalledWith(4);
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
