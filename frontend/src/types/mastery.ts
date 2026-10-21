export type MasteryStatus =
  'not_assessed' | 'good_performance' | 'needs_reinforcement' | 'possibly_weak' | 'needs_attention';
export type ConfidenceLevel = 'insufficient' | 'low' | 'medium' | 'high';
export type ConfidenceReasonCode =
  | 'insufficient_evidence'
  | 'single_assessment'
  | 'limited_difficulty_coverage'
  | 'performance_variation'
  | 'sufficient_evidence';
export type KnowledgeStateAvailability = 'calculated' | 'not_calculated' | 'stale';
export type EvidenceSourceType = 'diagnostic';
export type EvidenceDifficulty = 'easy' | 'medium' | 'hard';

export interface KnowledgeNodeMastery {
  knowledge_node_id: number;
  mastery_score: string | null;
  mastery_status: MasteryStatus;
  confidence_level: ConfidenceLevel;
  confidence_reason_codes: ConfidenceReasonCode[];
  evidence_count: number;
  independent_evidence_count: number;
  assessment_count: number;
  knowledge_model_version: string | null;
  algorithm_version: string | null;
  calculated_at: string | null;
  calculation_state: KnowledgeStateAvailability;
}

export interface CourseMasteryResponse {
  course_id: number;
  nodes: KnowledgeNodeMastery[];
}

export interface EvidenceExplanationItem {
  evidence_id: number;
  source_type: EvidenceSourceType;
  source_assessment_id: number;
  source_question_reference: number;
  historical_knowledge_node_reference: number;
  normalized_score: string;
  difficulty: EvidenceDifficulty;
  attribution_weight: string;
  occurred_at: string;
}

export interface KnowledgeEvidenceExplanation {
  course_id: number;
  knowledge_node_id: number;
  state: KnowledgeNodeMastery;
  summary: {
    effective_evidence_count: number;
    independent_evidence_count: number;
    assessment_count: number;
    evidence_returned: number;
  };
  evidence: EvidenceExplanationItem[];
}
