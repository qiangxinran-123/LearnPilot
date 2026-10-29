export type TrendRange = '7d' | '30d' | 'all';
export interface TrendPoint {
  recorded_at: string;
  segment: number;
  overall_mastery: string;
  evaluated_node_count: number;
  evaluable_node_count: number;
  coverage_ratio: number;
}
export interface ProgressTrend {
  course_id: number;
  range: TrendRange;
  points: TrendPoint[];
  excluded_incompatible_history: boolean;
}
export interface LearningEvent {
  id: string;
  event_type: 'diagnosis_completed' | 'learning_session_completed';
  occurred_at: string;
  course_id: number;
  knowledge_node_id: number | null;
  knowledge_node_name: string | null;
}
export interface LearningHistory {
  course_id: number;
  events: LearningEvent[];
  next_cursor: string | null;
}
