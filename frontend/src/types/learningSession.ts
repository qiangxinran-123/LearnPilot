export type LearningSessionStatus = 'created' | 'in_progress' | 'completed' | 'cancelled';
export type LearningSessionTaskPhase = 'concept_learning' | 'guided_example' | 'adaptive_practice';
export type LearningSessionTaskStatus = 'not_started' | 'in_progress' | 'completed';
export type RecommendationRefreshStatus = 'not_requested' | 'pending' | 'succeeded' | 'failed';

export interface MasteryChange {
  knowledge_node_id: number;
  before: number | null;
  after: number | null;
  delta: number | null;
  confidence: string;
  calculated_at: string;
}

export interface SettlementSummary {
  practice_summary: { total_questions: number; correct_answers: number; accuracy: number };
  mastery_changes: MasteryChange[];
  evidence_ids: number[];
  recommendation: {
    knowledge_node_id: number;
    title: string;
    reason_codes: RecommendationReasonCode[];
    description: string;
    plan_id: number;
  } | null;
}

export interface LearningSessionTask {
  task_id: number;
  phase: LearningSessionTaskPhase;
  order_index: number;
  status: LearningSessionTaskStatus;
  source_learning_task_id: number | null;
  progress: Record<string, string | number | boolean>;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface LearningSession {
  session_id: number;
  user_id: number;
  course_id: number;
  course_name: string;
  target_knowledge_node_id: number;
  target_knowledge_node_name: string;
  source_learning_plan_id: number | null;
  practice_assessment_id: number | null;
  status: LearningSessionStatus;
  session_contract_version: string;
  completion_summary: SettlementSummary | null;
  recommendation_refresh_status: RecommendationRefreshStatus;
  tasks: LearningSessionTask[];
  started_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  created_at: string;
  updated_at: string;
  reused: boolean;
}

export interface ActiveLearningSessionResponse {
  session: LearningSession | null;
}

export interface LearningSessionCreateRequest {
  course_id: number;
  target_knowledge_node_id?: number;
  learning_plan_id?: number;
}

export type LearningContentStatus = 'ready' | 'empty';
export type LearningContentRelevance = 'direct' | 'supplemental';

export interface LearningContentSegment {
  material_id: number;
  material_title: string;
  material_type: string;
  segment_index: number;
  fragment_index: number;
  text: string;
  source_reference: string;
  relevance: LearningContentRelevance;
  content_hash: string;
  text_truncated: boolean;
}

export interface LearningContent {
  session_id: number;
  course_id: number;
  knowledge_node_id: number;
  knowledge_node_name: string;
  knowledge_node_description: string;
  phase: LearningSessionTaskPhase;
  status: LearningContentStatus;
  grounded: boolean;
  segments: LearningContentSegment[];
  limits: {
    max_segments: number;
    max_segment_chars: number;
    max_total_chars: number;
    max_segments_per_material: number;
  };
}

export type TeachingStrategy =
  | 'hint'
  | 'guided_question'
  | 'example'
  | 'step_by_step_explanation'
  | 'full_explanation';

export interface TutorCitation {
  material_id: number;
  material_title: string;
  material_type: string;
  source_reference: string;
  content_hash: string;
}

export interface TutorMessage {
  message_id: number;
  exchange_id: string;
  session_id: number;
  task_state_id: number | null;
  role: 'user' | 'assistant';
  mode: TeachingStrategy;
  content: string;
  citations: TutorCitation[];
  grounded: boolean;
  insufficient_evidence: boolean;
  created_at: string;
}

export interface TutorMessageList {
  session_id: number;
  messages: TutorMessage[];
}

export interface TutorExchange {
  session_id: number;
  user_message: TutorMessage;
  tutor_message: TutorMessage;
  reused: boolean;
}

export interface TutorMessageCreateRequest {
  message: string;
  mode: TeachingStrategy;
}

export type QuestionDifficulty = 'easy' | 'medium' | 'hard';
export type QuestionType = 'single_choice' | 'multiple_choice' | 'true_false';
export type PracticeStatus = 'in_progress' | 'completed' | 'question_bank_empty';

export interface PracticeOption {
  key: string;
  text: string;
}

export interface PracticeSourceReference {
  material_id: number | null;
  material_title: string | null;
  source_reference: string;
  excerpt: string | null;
}

export interface PracticeQuestion {
  assessment_question_id: number;
  question_id: number;
  question_number: number;
  question_type: QuestionType;
  stem: string;
  options: PracticeOption[];
  difficulty: QuestionDifficulty;
}

export interface PracticeAttempt extends PracticeQuestion {
  attempt_id: number;
  selected_options: string[];
  correct_answer: string[];
  explanation: string;
  is_correct: boolean;
  points_awarded: string;
  source_refs: PracticeSourceReference[];
  submitted_at: string;
}

export interface PracticeSummary {
  answered_count: number;
  correct_count: number;
  accuracy: string;
}

export interface AdaptivePractice {
  session_id: number;
  knowledge_node_id: number;
  assessment_id: number;
  status: PracticeStatus;
  current_difficulty: QuestionDifficulty;
  current_question: PracticeQuestion | null;
  answered_count: number;
  max_questions: number;
  attempts: PracticeAttempt[];
  summary: PracticeSummary | null;
  reused: boolean;
}
import type { RecommendationReasonCode } from './learningPlan';
