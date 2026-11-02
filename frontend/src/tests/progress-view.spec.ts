import { createPinia } from 'pinia';
import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ElSelect } from 'element-plus';
import ProgressView from '@/views/ProgressView.vue';
import { fetchCourses } from '@/services/courses';
import { fetchKnowledgeModel } from '@/services/knowledge';
import { fetchProgressKnowledge, fetchProgressOverview } from '@/services/progress';
import { fetchReviewRisk } from '@/services/reviewRisk';
import type { ProgressNode, ProgressOverview } from '@/types/progress';

const routing = vi.hoisted(() => ({ push: vi.fn(), replace: vi.fn(), route: { query: {} } }));
vi.mock('vue-router', async () => ({
  ...await vi.importActual('vue-router'),
  useRouter: () => ({ push: routing.push, replace: routing.replace }),
  useRoute: () => routing.route,
}));
vi.mock('@/services/courses', () => ({ fetchCourses: vi.fn() }));
vi.mock('@/services/knowledge', () => ({ fetchKnowledgeModel: vi.fn() }));
vi.mock('@/services/reviewRisk', () => ({ fetchReviewRisk: vi.fn() }));
vi.mock('@/services/progress', () => ({ fetchProgressKnowledge: vi.fn(), fetchProgressOverview: vi.fn() }));

const weak: ProgressNode = { node_id: 11, name: '很长的知识点名称', parent_ids: [10], mastery_score: '0.00',
  mastery_status: 'needs_attention', confidence_level: 'low', evidence_count: 3, calculation_state: 'calculated' };
const unknown: ProgressNode = { node_id: 12, name: '尚无证据', parent_ids: [10], mastery_score: null,
  mastery_status: 'not_assessed', confidence_level: 'insufficient', evidence_count: 0, calculation_state: 'not_calculated' };
const overview: ProgressOverview = { course_id: 7, overall_mastery: '0.00', evaluated_node_count: 1,
  evaluable_node_count: 2, coverage_ratio: 0.5,
  status_counts: { good_performance: 0, needs_reinforcement: 0, possibly_weak: 0, needs_attention: 1, not_assessed: 1 },
  weak_nodes: [weak] };
const model = { course_id: 7, nodes: [{ id: 10, course_id: 7, name: '模块', normalized_name: '模块',
  description: '', importance: 'medium' as const, difficulty: 'basic' as const, created_at: '', updated_at: '' }], edges: [] };
function mountPage() { return mount(ProgressView, { global: { plugins: [createPinia()], stubs: { ProgressHistoryPanel: { template: '<div class="history-stub"><slot /></div>' }, RouterLink: { template: '<a><slot /></a>' } } } }); }
describe('progress overview', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchReviewRisk).mockResolvedValue({ course_id: 7, assessed_at: '', total_node_count: 2, counts: { review_due: 0, watch: 0, low_risk: 1, insufficient_data: 1 }, items: [] });
    vi.mocked(fetchCourses).mockResolvedValue({ count: 2, courses: [
      { id: 7, name: '课程一', description: '' }, { id: 8, name: '课程二', description: '' },
    ] });
    vi.mocked(fetchKnowledgeModel).mockResolvedValue(model);
    vi.mocked(fetchProgressOverview).mockResolvedValue(overview);
    vi.mocked(fetchProgressKnowledge).mockResolvedValue({ course_id: 7, nodes: [unknown, weak] });
  });
  it('shows real zero, null, coverage, confidence, sorted nodes and map navigation', async () => {
    const wrapper = mountPage();
    await flushPromises();
    expect(wrapper.text()).toContain('0.00%');
    expect(wrapper.text()).not.toContain('暂无数据');
    await wrapper.find('.comparison-toggle').trigger('click');
    expect(wrapper.text()).toContain('暂无数据');
    expect(wrapper.text()).toContain('尚未计算');
    expect(wrapper.text()).toContain('已评估 1 / 2');
    expect(wrapper.text()).toContain('覆盖率 50.0%');
    expect(wrapper.text()).toContain('置信度：低');
    expect(wrapper.findAll('.chart-row')[0]?.text()).toContain(weak.name);
    expect(wrapper.findAll('.review-row')).toHaveLength(1);
    await wrapper.find('.node-link').trigger('click');
    expect(routing.push).toHaveBeenCalledWith({ name: 'course-detail', params: { courseId: 7 },
      query: { tab: 'knowledge-structure', nodeId: '11' } });
  });
  it('does not turn missing mastery into zero', async () => {
    vi.mocked(fetchProgressOverview).mockResolvedValue({ ...overview, overall_mastery: null,
      evaluated_node_count: 0, coverage_ratio: 0, weak_nodes: [] });
    vi.mocked(fetchProgressKnowledge).mockResolvedValue({ course_id: 7, nodes: [unknown] });
    const wrapper = mountPage();
    await flushPromises();
    expect(wrapper.text()).toContain('暂无足够学习数据');
    expect(wrapper.find('.summary-score').exists()).toBe(false);
  });
  it('shows loading, error and retry', async () => {
    let reject!: (reason: Error) => void;
    vi.mocked(fetchProgressOverview).mockReturnValueOnce(new Promise((_resolve, fail) => { reject = fail; }));
    const wrapper = mountPage();
    await flushPromises();
    expect(wrapper.find('[aria-label="正在加载"]').exists()).toBe(true);
    reject(new Error('failed'));
    await flushPromises();
    expect(wrapper.find('[role="alert"]').exists()).toBe(true);
    await wrapper.find('[role="alert"] button').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('已评估 1 / 2');
  });
  it('ignores old course requests when selection changes', async () => {
    let resolveOld!: (value: ProgressOverview) => void;
    vi.mocked(fetchProgressOverview).mockImplementation((id) => id === 7
      ? new Promise((resolve) => { resolveOld = resolve; })
      : Promise.resolve({ ...overview, course_id: 8, overall_mastery: '80.00' }));
    const wrapper = mountPage();
    await flushPromises();
    wrapper.findComponent(ElSelect).vm.$emit('update:modelValue', 8);
    await flushPromises();
    expect(wrapper.text()).toContain('80.00%');
    resolveOld(overview);
    await flushPromises();
    expect(wrapper.text()).toContain('80.00%');
    expect(wrapper.find('.summary-score').text()).toBe('80.00%');
  });
  it('filters the leaf chart by module and shows stale state', async () => {
    vi.mocked(fetchProgressKnowledge).mockResolvedValue({
      course_id: 7, nodes: [weak, { ...unknown, calculation_state: 'stale', parent_ids: [] }],
    });
    const wrapper = mountPage();
    await flushPromises();
    await wrapper.find('.comparison-toggle').trigger('click');
    expect(wrapper.text()).toContain('状态已过期');
    wrapper.findAllComponents(ElSelect)[1]?.vm.$emit('update:modelValue', '10');
    await flushPromises();
    expect(wrapper.findAll('.chart-row')).toHaveLength(1);
    expect(wrapper.find('.chart-row').text()).toContain(weak.name);
  });
  it('limits the selected module to six assessed nodes and resets expansion on filter changes', async () => {
    const nodes = Array.from({ length: 9 }, (_, index) => ({
      ...weak, node_id: 20 + index, name: `节点 ${index}`, parent_ids: index < 7 ? [10] : [],
    }));
    vi.mocked(fetchProgressKnowledge).mockResolvedValue({ course_id: 7, nodes: [...nodes, unknown] });
    const wrapper = mountPage();
    await flushPromises();
    expect(wrapper.findAll('.chart-row')).toHaveLength(6);
    expect(wrapper.find('.comparison-toggle').text()).toContain('共 10 个');
    await wrapper.find('.comparison-toggle').trigger('click');
    expect(wrapper.findAll('.chart-row')).toHaveLength(10);
    expect(wrapper.text()).toContain('暂无数据');
    wrapper.findAllComponents(ElSelect)[1]?.vm.$emit('update:modelValue', '10');
    await flushPromises();
    expect(wrapper.findAll('.chart-row')).toHaveLength(6);
    expect(wrapper.find('.comparison-toggle').text()).toContain('共 8 个');
    await wrapper.find('.comparison-toggle').trigger('click');
    expect(wrapper.findAll('.chart-row')).toHaveLength(8);
    await wrapper.find('.comparison-toggle').trigger('click');
    expect(wrapper.findAll('.chart-row')).toHaveLength(6);
  });
  it('shows a course empty state', async () => {
    vi.mocked(fetchCourses).mockResolvedValue({ count: 0, courses: [] });
    const wrapper = mountPage();
    await flushPromises();
    expect(wrapper.text()).toContain('还没有课程');
    expect(fetchProgressOverview).not.toHaveBeenCalled();
  });
});
