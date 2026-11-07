import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import LearningSummary from '@/components/learning/LearningSummary.vue';
import type { LearningSession } from '@/types/learningSession';

function session(delta: number | null, status: LearningSession['recommendation_refresh_status'] = 'succeeded'): LearningSession {
  return {
    session_id: 1, user_id: 1, course_id: 2, course_name: '计算机系统',
    target_knowledge_node_id: 3, target_knowledge_node_name: 'Cache',
    source_learning_plan_id: null, practice_assessment_id: 4, status: 'completed',
    session_contract_version: 'learning_session_v1', recommendation_refresh_status: status,
    completion_summary: {
      practice_summary: { total_questions: 5, correct_answers: 4, accuracy: 0.8 },
      evidence_ids: [1, 2, 3, 4, 5],
      mastery_changes: [{ knowledge_node_id: 3, before: 52, after: delta === null ? null : 52 + delta,
        delta, confidence: 'medium', calculated_at: '2026-01-01T00:00:00Z' }],
      recommendation: { knowledge_node_id: 7, title: '替换策略', description: '结合课程材料继续复习。',
        reason_codes: ['review_needed'], plan_id: 8 },
    },
    tasks: [], started_at: null, completed_at: null, cancelled_at: null,
    created_at: '2026-01-01', updated_at: '2026-01-01', reused: false,
  };
}

describe('learning settlement summary', () => {
  it.each([[16, '提高 16 个百分点'], [-8, '下降 8 个百分点'], [0, '本次掌握度保持不变'], [null, '当前证据尚不足以比较变化']])(
    'shows real mastery change %s', (delta, text) => {
      const current = session(delta);
      const wrapper = mount(LearningSummary, { props: { session: current, retrying: false, continuation: current.completion_summary!.recommendation } });
      expect(wrapper.text()).toContain(text);
      expect(wrapper.text()).toContain('52%');
      expect(wrapper.text()).toContain('80%');
      expect(wrapper.text()).toContain('替换策略');
    },
  );
  it('does not claim recalculation when no new evidence was created', () => {
    const current = session(0);
    current.completion_summary!.evidence_ids = [];
    const wrapper = mount(LearningSummary, { props: { session: current, retrying: false } });
    expect(wrapper.text()).toContain('本次练习未形成新的有效学习证据');
    expect(wrapper.text()).not.toContain('系统依据实际答题结果重新计算掌握度');
  });
  it('handles empty recommendations and retryable failure', async () => {
    const empty = session(0);
    if (empty.completion_summary) empty.completion_summary.recommendation = null;
    const wrapper = mount(LearningSummary, { props: { session: empty, retrying: false } });
    expect(wrapper.text()).toContain('当前没有可用的下一步推荐');
    await wrapper.setProps({ session: session(0, 'failed'), continuationError: 'failed' });
    expect(wrapper.text()).toContain('学习结果已保存');
    wrapper.findComponent({ name: 'ElButton' }).vm.$emit('click');
    expect(wrapper.emitted('retry')).toHaveLength(1);
  });
  it('ends this round instead of offering the same target again', () => {
    const repeated = session(0);
    repeated.completion_summary!.recommendation!.knowledge_node_id = repeated.target_knowledge_node_id;
    const wrapper = mount(LearningSummary, { props: { session: repeated, retrying: false, continuation: repeated.completion_summary!.recommendation } });
    expect(wrapper.text()).toContain('本轮学习已完成');
    expect(wrapper.text()).toContain('返回学习页');
    expect(wrapper.text()).not.toContain('学习下一个知识点');
  });
  it('shows actual wrong-answer details supplied by the practice panel', () => {
    const wrapper = mount(LearningSummary, { props: { session: session(0), retrying: false, attempts: [{
      attempt_id: 10, assessment_question_id: 11, question_id: 12, question_number: 1,
      question_type: 'single_choice', stem: '缓存映射？', options: [], difficulty: 'medium',
      selected_options: ['B'], correct_answer: ['A'], explanation: '按块号映射。', is_correct: false,
      points_awarded: '0', source_refs: [], submitted_at: '2026-01-01',
    }] } });
    expect(wrapper.text()).toContain('查看本轮错题');
    expect(wrapper.text()).toContain('缓存映射？');
    expect(wrapper.text()).toContain('按块号映射。');
  });
});
