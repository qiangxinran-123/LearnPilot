import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import ReviewRiskPanel from '@/components/progress/ReviewRiskPanel.vue';
import { fetchReviewRisk } from '@/services/reviewRisk';
import type { ReviewRiskResponse } from '@/types/reviewRisk';
import type { ProgressNode } from '@/types/progress';

const routing = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock('vue-router', async () => ({ ...await vi.importActual('vue-router'), useRouter: () => routing }));
vi.mock('@/services/reviewRisk', () => ({ fetchReviewRisk: vi.fn() }));
const weak: ProgressNode = { node_id: 11, name: '很长的薄弱知识点', parent_ids: [], mastery_score: '35.00',
  mastery_status: 'needs_attention', confidence_level: 'medium', evidence_count: 6, calculation_state: 'calculated' };
const response: ReviewRiskResponse = { course_id: 1, assessed_at: '2026-10-28T08:00:00Z', total_node_count: 2,
  counts: { review_due: 1, watch: 0, low_risk: 0, insufficient_data: 1 },
  items: [{ knowledge_node_id: 11, name: weak.name, mastery_score: weak.mastery_score,
    mastery_status: weak.mastery_status, confidence_level: weak.confidence_level, evidence_count: 6,
    calculation_state: 'calculated', risk_level: 'review_due', reason_code: 'weak_mastery',
    reason_text: '当前掌握状态提示该知识点可能薄弱，值得巩固。',
    last_practice_at: '2026-10-01T08:00:00Z', days_since_practice: 27 }] };
const mountPanel = (courseId = 1, evaluatedCount = 1, weakNodes = [weak]) =>
  mount(ReviewRiskPanel, { props: { courseId, evaluatedCount, weakNodes } });
describe('review risk integration', () => {
  beforeEach(() => { vi.clearAllMocks(); vi.mocked(fetchReviewRisk).mockResolvedValue(response); });
  it('merges weakness with risk, shows evidence and routes to the map', async () => {
    const wrapper = mountPanel(); await flushPromises();
    expect(wrapper.findAll('.review-row')).toHaveLength(1);
    expect(wrapper.text()).toContain('建议巩固');
    expect(wrapper.text()).toContain('当前掌握状态提示');
    expect(wrapper.text()).toContain('最近有效练习');
    expect(wrapper.text()).toContain('置信度 中');
    expect(wrapper.text()).toContain('需要关注');
    expect(wrapper.text()).toContain('部分知识点证据不足或状态不可用');
    await wrapper.find('.review-row button').trigger('click');
    expect(routing.push).toHaveBeenCalledWith({ name: 'course-detail', params: { courseId: 1 },
      query: { tab: 'knowledge-structure', nodeId: '11' } });
  });
  it('distinguishes no data from no reminder', async () => {
    const clean = { ...response, items: [], counts: { review_due: 0, watch: 0, low_risk: 1, insufficient_data: 0 } };
    vi.mocked(fetchReviewRisk).mockResolvedValue(clean);
    const empty = mountPanel(1, 0, []); await flushPromises();
    expect(empty.text()).toContain('完成诊断或学习后');
    const quiet = mountPanel(1, 1, []); await flushPromises();
    expect(quiet.text()).toContain('目前没有识别到明显的复习提醒');
  });
  it('keeps weak data when the risk request fails and retries independently', async () => {
    vi.mocked(fetchReviewRisk).mockRejectedValueOnce(new Error('failure')).mockResolvedValueOnce(response);
    const wrapper = mountPanel(); await flushPromises();
    expect(wrapper.text()).toContain('复习提醒加载失败');
    expect(wrapper.text()).toContain(weak.name);
    await wrapper.find('[role="alert"] button').trigger('click'); await flushPromises();
    expect(wrapper.findAll('.review-row')).toHaveLength(1);
  });
  it('suppresses an earlier weak score when risk data says current mastery is unavailable', async () => {
    vi.mocked(fetchReviewRisk).mockResolvedValue({ ...response, counts: { ...response.counts, review_due: 0 },
      items: [{ ...response.items[0]!, mastery_score: null, risk_level: 'insufficient_data',
        calculation_state: 'stale', reason_code: 'stale_mastery' }] });
    const wrapper = mountPanel(); await flushPromises();
    expect(wrapper.findAll('.review-row')).toHaveLength(0);
    expect(wrapper.text()).toContain('状态不可用');
    expect(wrapper.text()).not.toContain('35.00%');
  });
  it('uses the newer M5 classification if an earlier weak node is now low risk', async () => {
    vi.mocked(fetchReviewRisk).mockResolvedValue({ ...response, counts: { ...response.counts, review_due: 0, low_risk: 1 },
      items: [{ ...response.items[0]!, mastery_score: '90.00', mastery_status: 'good_performance',
        risk_level: 'low_risk', reason_code: 'recent_practice' }] });
    const wrapper = mountPanel(); await flushPromises();
    expect(wrapper.findAll('.review-row')).toHaveLength(0);
    expect(wrapper.text()).not.toContain('35.00%');
  });
  it('shows loading and rejects stale course results', async () => {
    let resolveOld!: (value: ReviewRiskResponse) => void;
    vi.mocked(fetchReviewRisk).mockImplementation((id) => id === 1
      ? new Promise((resolve) => { resolveOld = resolve; })
      : Promise.resolve({ ...response, course_id: 2, items: [] }));
    const wrapper = mountPanel();
    expect(wrapper.find('[aria-label="正在加载"]').exists()).toBe(true);
    await wrapper.setProps({ courseId: 2, weakNodes: [] }); await flushPromises();
    resolveOld(response); await flushPromises();
    expect(wrapper.text()).not.toContain(weak.name);
    expect(fetchReviewRisk).toHaveBeenLastCalledWith(2);
  });
});
