export type LearningPlanAvailability = 'available' | 'stale' | 'not_available';
export type LearningPlanStatus = 'available' | 'superseded';
export type LearningPlanLevel = 'personalized' | 'preliminary' | 'foundational';
export type LearningTaskType = 'concept_review' | 'example_walkthrough' | 'targeted_practice';
export type RecommendationAvailabilityStatus =
  | 'available'
  | 'unavailable'
  | 'needs_initial_diagnostic'
  | 'needs_prerequisite_assessment'
  | 'no_eligible_candidate'
  | 'all_mastered'
  | 'invalid_context';
export type RecommendationReasonCode =
  | 'knowledge_gap'
  | 'low_mastery'
  | 'prerequisite_gap'
  | 'prerequisite_for_other_nodes'
  | 'high_course_importance'
  | 'review_needed'
  | 'insufficient_evidence'
  | 'neutral_course_importance'
  | 'neutral_review_risk'
  | 'no_eligible_candidate'
  | 'all_mastered'
  | 'invalid_prerequisite_graph';
export type PrerequisiteEvidenceStatus =
  'satisfied' | 'unsatisfied' | 'insufficient_evidence' | 'invalid';

export interface PriorityBreakdown {
  knowledge_gap: string | null;
  dependency_importance: string | null;
  course_importance: string | null;
  review_risk: string | null;
  total_priority: string | null;
}

export interface PrerequisiteEvidence {
  source_node_id: number;
  target_node_id: number;
  status: PrerequisiteEvidenceStatus;
}

export interface LearningTask {
  task_id: number;
  knowledge_node_id: number;
  task_type: LearningTaskType;
  title: string;
  description: string;
  order_index: number;
  estimated_minutes: number | null;
}

export interface LearningPlan {
  plan_id: number;
  user_id: number;
  course_id: number;
  target_node_id: number;
  reason_codes: RecommendationReasonCode[];
  priority_score: string;
  priority_breakdown: PriorityBreakdown;
  prerequisite_evidence: PrerequisiteEvidence[];
  blocked_target_node_ids: number[];
  status: LearningPlanStatus;
  tasks: LearningTask[];
  created_at: string;
  updated_at: string;
}

export interface LearningPlanResponse {
  availability: LearningPlanAvailability;
  recommendation_status: RecommendationAvailabilityStatus;
  plan_level: LearningPlanLevel | null;
  plan: LearningPlan | null;
  reused: boolean;
}

export type LearningPlanViewState =
  'idle' | 'loading' | 'available' | 'stale' | 'unavailable' | 'error';
