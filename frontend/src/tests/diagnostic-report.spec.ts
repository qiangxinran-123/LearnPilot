import { flushPromises, mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import DiagnosticReportView from '@/views/DiagnosticReportView.vue';
import { fetchAssessmentResult } from '@/services/diagnostics';

const push = vi.fn();
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { assessmentId: '12' } }),
  useRouter: () => ({ push }),
}));
vi.mock('@/services/diagnostics', () => ({ fetchAssessmentResult: vi.fn() }));

const report = {
  assessment_id: 12, course_id: 2, course_name: '数据结构', submitted_at: '2026-10-18T00:00:00Z',
  total_questions: 3, answered_questions: 2, correct_questions: 1, total_points: 3, earned_points: 1,
  accuracy: 1 / 3, report_policy_version: 'diagnostic_node_performance_v1', covered_knowledge_nodes: 1,
  needs_attention_nodes: 1,
  knowledge_performance: [{ historical_node_id: 8, historical_node_name: 'LRU 替换', map_available: true,
    question_count: 3, answered_count: 2, correct_count: 1, incorrect_count: 1, unanswered_count: 1,
    accuracy: 1 / 3, evidence_status: 'basic_evidence' as const, preliminary_status: 'needs_attention' as const }],
  question_reviews: [{ assessment_question_id: 1, order_index: 0, question_type: 'single_choice' as const,
    stem: 'LRU 选择哪个块？', options: [{ key: 'A', text: '最近使用' }, { key: 'B', text: '最久未使用' }],
    selected_options: [], correct_answer: ['B'], explanation: 'LRU 选择最久未使用的块。', is_correct: false,
    points_awarded: 0, primary_node: { historical_node_id: 8, historical_node_name: 'LRU 替换', map_available: true },
    secondary_nodes: [], source_refs: [{ material_id: 4, material_title: '缓存讲义', source_reference: 'PDF 第 12 页', excerpt: '替换策略', is_accessible: false }] }],
};

describe('DiagnosticReportView', () => {
  beforeEach(() => { vi.clearAllMocks(); vi.mocked(fetchAssessmentResult).mockResolvedValue(report); });

  it('renders historical node performance, unanswered review, and unavailable source safely', async () => {
    const wrapper = mount(DiagnosticReportView, { attachTo: document.body });
    await flushPromises();
    expect(wrapper.text()).toContain('LRU 替换');
    expect(wrapper.text()).toContain('需要关注');
    expect(wrapper.text()).toContain('未作答');
    expect(wrapper.text()).toContain('正确答案');
    expect(wrapper.text()).toContain('原始资料当前不可访问');
    wrapper.unmount();
  });

  it('uses exact historical node id for the existing knowledge-map route', async () => {
    const wrapper = mount(DiagnosticReportView, { attachTo: document.body });
    await flushPromises();
    await wrapper.findAll('button').find((button) => button.text().includes('知识地图'))?.trigger('click');
    expect(push).toHaveBeenCalledWith({ name: 'course-detail', params: { courseId: 2 }, query: { tab: 'knowledge-structure', nodeId: '8' } });
    wrapper.unmount();
  });

  it('shows a retryable error when the report is unavailable', async () => {
    vi.mocked(fetchAssessmentResult).mockRejectedValueOnce(new Error('not submitted'));
    const wrapper = mount(DiagnosticReportView);
    await flushPromises();
    expect(wrapper.text()).toContain('报告暂不可用');
    wrapper.unmount();
  });
});
