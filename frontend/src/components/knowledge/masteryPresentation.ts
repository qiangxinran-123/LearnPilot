import type { ConfidenceLevel, KnowledgeNodeMastery, MasteryStatus } from '@/types/mastery';

export const masteryStatusLabel: Record<MasteryStatus, string> = {
  not_assessed: '待评估',
  good_performance: '表现较好',
  needs_reinforcement: '有待巩固',
  possibly_weak: '可能薄弱',
  needs_attention: '需要关注',
};

export const confidenceLabel: Record<ConfidenceLevel, string> = {
  insufficient: '证据不足',
  low: '低',
  medium: '中',
  high: '高',
};

export function isUsableMastery(
  state: KnowledgeNodeMastery | undefined,
): state is KnowledgeNodeMastery {
  return state?.calculation_state === 'calculated';
}

export function masteryScoreLabel(state: KnowledgeNodeMastery | undefined): string {
  if (!isUsableMastery(state) || state?.mastery_score === null) return '待评估';
  const score = Number(state.mastery_score);
  return Number.isFinite(score) ? `${score.toFixed(0)}%` : '待评估';
}

export function masteryTone(state: KnowledgeNodeMastery | undefined): string {
  if (!isUsableMastery(state) || state?.mastery_score === null) return 'unassessed';
  if (state.mastery_status === 'good_performance') {
    return state.confidence_level === 'medium' || state.confidence_level === 'high'
      ? 'good'
      : 'cautious';
  }
  return state.mastery_status;
}
