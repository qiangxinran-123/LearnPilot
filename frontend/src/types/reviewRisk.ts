import type { ConfidenceLevel, KnowledgeStateAvailability, MasteryStatus } from '@/types/mastery';

export type ReviewRiskLevel = 'review_due' | 'watch' | 'low_risk' | 'insufficient_data';
export interface ReviewRiskItem {
  knowledge_node_id: number;
  name: string;
  mastery_score: string | null;
  mastery_status: MasteryStatus;
  confidence_level: ConfidenceLevel;
  calculation_state: KnowledgeStateAvailability;
  evidence_count: number;
  risk_level: ReviewRiskLevel;
  reason_code: string;
  reason_text: string;
  last_practice_at: string | null;
  days_since_practice: number | null;
}
export interface ReviewRiskResponse {
  course_id: number;
  assessed_at: string;
  total_node_count: number;
  counts: Record<ReviewRiskLevel, number>;
  items: ReviewRiskItem[];
}
