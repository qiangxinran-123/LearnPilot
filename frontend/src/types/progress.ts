import type { ConfidenceLevel, KnowledgeStateAvailability, MasteryStatus } from '@/types/mastery';

export interface ProgressNode {
  node_id: number;
  name: string;
  parent_ids: number[];
  mastery_score: string | null;
  mastery_status: MasteryStatus;
  confidence_level: ConfidenceLevel;
  evidence_count: number;
  calculation_state: KnowledgeStateAvailability;
}
export interface ProgressKnowledge {
  course_id: number;
  nodes: ProgressNode[];
}
export interface ProgressOverview {
  course_id: number;
  overall_mastery: string | null;
  evaluated_node_count: number;
  evaluable_node_count: number;
  coverage_ratio: number | null;
  status_counts: Record<MasteryStatus, number>;
  weak_nodes: ProgressNode[];
}
