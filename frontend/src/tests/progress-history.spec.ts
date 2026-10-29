import { flushPromises, mount } from '@vue/test-utils';
import { ElSelect } from 'element-plus';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ProgressHistoryPanel from '@/components/progress/ProgressHistoryPanel.vue';
import { fetchLearningHistory, fetchProgressTrend } from '@/services/progressHistory';
import type { ProgressTrend } from '@/types/progressHistory';

const routing = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('vue-router', async () => ({ ...await vi.importActual('vue-router'), useRouter: () => routing }));
vi.mock('@/services/progressHistory', () => ({ fetchLearningHistory: vi.fn(), fetchProgressTrend: vi.fn() }));
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
    const wrapper = mount(ProgressHistoryPanel, { props: { courseId: 1 } });
    await flushPromises();
    expect(wrapper.findAll('circle')).toHaveLength(2);
    expect(wrapper.find('circle title').text()).toContain('30.00%');
    expect(wrapper.find('circle title').text()).toContain('50.0%');
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
    const wrapper = mount(ProgressHistoryPanel, { props: { courseId: 1 } });
    await flushPromises();
    expect(wrapper.find('polyline').exists()).toBe(false);
    expect(wrapper.text()).toContain('学习记录正在积累');
    expect(wrapper.text()).toContain('还没有学习记录');
  });
  it('requests the selected range and ignores stale course results', async () => {
    let resolveOld!: (value: ProgressTrend) => void;
    vi.mocked(fetchProgressTrend).mockImplementation((id) => id === 1
      ? new Promise((resolve) => { resolveOld = resolve; })
      : Promise.resolve({ ...points, course_id: id, points: [] }));
    const wrapper = mount(ProgressHistoryPanel, { props: { courseId: 1 } });
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
  it('does not connect incomparable segments', async () => {
    vi.mocked(fetchProgressTrend).mockResolvedValue({ ...points, excluded_incompatible_history: true, points: [
      points.points[0]!, { ...points.points[1]!, segment: 1 },
    ] });
    const wrapper = mount(ProgressHistoryPanel, { props: { courseId: 1 } });
    await flushPromises();
    expect(wrapper.find('polyline').exists()).toBe(false);
    expect(wrapper.text()).toContain('不可比的历史记录');
  });
  it('shows loading and retries an error', async () => {
    let reject!: (reason: Error) => void;
    vi.mocked(fetchProgressTrend).mockReturnValueOnce(new Promise((_resolve, fail) => { reject = fail; }));
    const wrapper = mount(ProgressHistoryPanel, { props: { courseId: 1 } });
    expect(wrapper.find('[aria-label="正在加载"]').exists()).toBe(true);
    reject(new Error('failed'));
    await flushPromises();
    expect(wrapper.find('[role="alert"]').exists()).toBe(true);
    await wrapper.find('[role="alert"] button').trigger('click');
    await flushPromises();
    expect(wrapper.findAll('circle')).toHaveLength(2);
  });
});
