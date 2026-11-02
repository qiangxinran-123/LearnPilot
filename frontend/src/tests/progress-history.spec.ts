import { flushPromises, mount } from '@vue/test-utils';
import { ElSelect } from 'element-plus';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ProgressHistoryPanel from '@/components/progress/ProgressHistoryPanel.vue';
import { fetchLearningHistory, fetchProgressTrend } from '@/services/progressHistory';
import type { ProgressTrend } from '@/types/progressHistory';

const routing = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('vue-router', async () => ({ ...await vi.importActual('vue-router'), useRouter: () => routing }));
vi.mock('@/services/progressHistory', () => ({ fetchLearningHistory: vi.fn(), fetchProgressTrend: vi.fn() }));
function mountPanel() {
  return mount(ProgressHistoryPanel, { props: { courseId: 1 }, global: { stubs: { ElDialog: {
    name: 'ElDialog', props: ['modelValue'], emits: ['update:modelValue'],
    template: '<div v-if="modelValue" role="dialog"><slot /></div>',
  } } } });
}
async function openHistory(wrapper: ReturnType<typeof mountPanel>) {
  const button = wrapper.findAll('button').find((item) => item.text() === '查看学习历史');
  expect(button).toBeDefined();
  await button!.trigger('click');
  await flushPromises();
}
const points: ProgressTrend = { course_id: 1, range: '30d', excluded_incompatible_history: false, points: [
  { recorded_at: '2026-10-01T09:00:00Z', segment: 0, overall_mastery: '30.00', coverage_ratio: 0.5, evaluated_node_count: 1, evaluable_node_count: 2 },
  { recorded_at: '2026-10-05T09:00:00Z', segment: 0, overall_mastery: '60.00', coverage_ratio: 1, evaluated_node_count: 2, evaluable_node_count: 2 },
] };
describe('progress history', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchProgressTrend).mockResolvedValue(points);
    vi.mocked(fetchLearningHistory).mockResolvedValue({ course_id: 1, next_cursor: null, events: [
      { id: 'learning_session_completed-1', event_type: 'learning_session_completed', occurred_at: '2026-10-05T09:00:00Z', course_id: 1, knowledge_node_id: 3, knowledge_node_name: '集合映射' },
      { id: 'diagnosis_completed-1', event_type: 'diagnosis_completed', occurred_at: '2026-10-01T09:00:00Z', course_id: 1, knowledge_node_id: null, knowledge_node_name: null },
    ] });
  });
  it('shows real points, coverage, history and navigation', async () => {
    const wrapper = mountPanel();
    await flushPromises();
    expect(wrapper.findAll('circle')).toHaveLength(2);
    expect(wrapper.find('circle title').text()).toContain('30.00%');
    expect(wrapper.find('circle title').text()).toContain('50.0%');
    await wrapper.find('circle').trigger('mouseenter');
    expect(wrapper.find('.point-tooltip').text()).toContain('30.00%');
    await wrapper.find('circle').trigger('mouseleave');
    expect(wrapper.find('.point-tooltip').exists()).toBe(false);
    expect(wrapper.find('.event-row').exists()).toBe(false);
    await openHistory(wrapper);
    expect(wrapper.text()).toContain('暂无可确认的掌握度变化记录');
    expect(wrapper.findAll('.event-row').map((row) => row.text())).toEqual([
      expect.stringContaining('完成学习会话'), expect.stringContaining('完成诊断'),
    ]);
    await wrapper.find('.event-row button').trigger('click');
    expect(routing.push).toHaveBeenCalledWith({ name: 'course-detail', params: { courseId: 1 },
      query: { tab: 'knowledge-structure', nodeId: '3' } });
  });
  it('does not draw a line with fewer than two points', async () => {
    vi.mocked(fetchProgressTrend).mockResolvedValue({ ...points, points: [points.points[0]!] });
    vi.mocked(fetchLearningHistory).mockResolvedValue({ course_id: 1, next_cursor: null, events: [] });
    const wrapper = mountPanel();
    await flushPromises();
    expect(wrapper.find('polyline').exists()).toBe(false);
    expect(wrapper.findAll('circle')).toHaveLength(1);
    expect(wrapper.find('circle title').text()).toContain('30.00%');
    expect(wrapper.text()).toContain('学习记录正在积累');
    await openHistory(wrapper);
    expect(wrapper.text()).toContain('还没有学习记录');
  });
  it('requests the selected range and ignores stale course results', async () => {
    let resolveOld!: (value: ProgressTrend) => void;
    vi.mocked(fetchProgressTrend).mockImplementation((id) => id === 1
      ? new Promise((resolve) => { resolveOld = resolve; })
      : Promise.resolve({ ...points, course_id: id, points: [] }));
    const wrapper = mountPanel();
    await wrapper.setProps({ courseId: 2 });
    await flushPromises();
    expect(wrapper.text()).toContain('学习记录正在积累');
    resolveOld(points);
    await flushPromises();
    expect(wrapper.find('polyline').exists()).toBe(false);
    wrapper.findComponent(ElSelect).vm.$emit('update:modelValue', '7d');
    await flushPromises();
    expect(fetchProgressTrend).toHaveBeenLastCalledWith(2, '7d');
  });
  it('keeps trend range when closing history and replaces old course history', async () => {
    vi.mocked(fetchLearningHistory).mockImplementation(async (courseId) => ({
      course_id: courseId, next_cursor: null, events: [{
        id: `learning_session_completed-${courseId}`, event_type: 'learning_session_completed',
        occurred_at: '2026-10-05T09:00:00Z', course_id: courseId,
        knowledge_node_id: courseId, knowledge_node_name: `课程${courseId}记录`,
      }],
    }));
    const wrapper = mountPanel();
    await flushPromises();
    wrapper.findComponent(ElSelect).vm.$emit('update:modelValue', '7d');
    await flushPromises();
    await openHistory(wrapper);
    expect(wrapper.text()).toContain('课程1记录');
    await wrapper.findComponent({ name: 'ElDialog' }).vm.$emit('update:modelValue', false);
    await flushPromises();
    expect(fetchProgressTrend).toHaveBeenLastCalledWith(1, '7d');
    await wrapper.setProps({ courseId: 2 });
    await flushPromises();
    await openHistory(wrapper);
    expect(wrapper.text()).toContain('课程2记录');
    expect(wrapper.text()).not.toContain('课程1记录');
    expect(fetchProgressTrend).toHaveBeenLastCalledWith(2, '7d');
  });
  it('displays history errors and retries within the dialog', async () => {
    vi.mocked(fetchLearningHistory).mockRejectedValueOnce(new Error('failed'));
    const wrapper = mountPanel();
    await flushPromises();
    await openHistory(wrapper);
    expect(wrapper.find('[role="alert"]').exists()).toBe(true);
    await wrapper.find('[role="alert"] button').trigger('click');
    await flushPromises();
    expect(wrapper.text()).toContain('集合映射');
  });
  it('orders real points by time and does not draw through invalid data', async () => {
    vi.mocked(fetchProgressTrend).mockResolvedValue({ ...points, points: [
      points.points[1]!, { ...points.points[0]!, recorded_at: 'invalid' }, points.points[0]!,
    ] });
    const wrapper = mountPanel();
    await flushPromises();
    expect(wrapper.findAll('circle title').map((title) => title.text())).toEqual([
      expect.stringContaining('30.00%'), expect.stringContaining('60.00%'),
    ]);
    expect(wrapper.find('polyline').exists()).toBe(false);
    expect(wrapper.text()).toContain('部分历史数据无效');
  });
  it('does not connect incomparable segments', async () => {
    vi.mocked(fetchProgressTrend).mockResolvedValue({ ...points, excluded_incompatible_history: true, points: [
      points.points[0]!, { ...points.points[1]!, segment: 1 },
    ] });
    const wrapper = mountPanel();
    await flushPromises();
    expect(wrapper.find('polyline').exists()).toBe(false);
    expect(wrapper.text()).toContain('不可比的历史记录');
  });
  it('shows loading and retries an error', async () => {
    let reject!: (reason: Error) => void;
    vi.mocked(fetchProgressTrend).mockReturnValueOnce(new Promise((_resolve, fail) => { reject = fail; }));
    const wrapper = mountPanel();
    expect(wrapper.find('[aria-label="正在加载"]').exists()).toBe(true);
    reject(new Error('failed'));
    await flushPromises();
    expect(wrapper.find('[role="alert"]').exists()).toBe(true);
    await wrapper.find('[role="alert"] button').trigger('click');
    await flushPromises();
    expect(wrapper.findAll('circle')).toHaveLength(2);
  });
});
