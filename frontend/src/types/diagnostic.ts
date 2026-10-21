export type AssessmentStatus = 'draft' | 'ready' | 'in_progress' | 'submitted';
export type DiagnosticQuestionType = 'single_choice' | 'true_false' | 'multiple_choice';
export type QuestionDifficulty = 'easy' | 'medium' | 'hard';

export interface DiagnosticReadiness {
  course_id: number;
  status: 'ready' | 'knowledge_not_ready' | 'question_bank_insufficient';
  can_start: boolean;
  estimated_question_count: number | null;
  estimated_minutes: number | null;
  eligible_knowledge_nodes: number;
  covered_knowledge_nodes: number;
  available_questions: number;
  required_questions: number;
  reason_code: string | null;
  message: string;
}

export interface QuestionOption {
  key: string;
  text: string;
}

export interface CandidateQuestion {
  assessment_question_id: number;
  order_index: number;
  question_type: DiagnosticQuestionType;
  stem: string;
  options: QuestionOption[];
  difficulty: QuestionDifficulty;
  saved_answer: string[] | null;
}

export interface Assessment {
  id: number;
  course_id: number;
  course_name: string;
  status: AssessmentStatus;
  questions: CandidateQuestion[];
  question_count: number;
  answered_count: number;
  created_at: string;
  started_at: string | null;
  submitted_at: string | null;
}

export interface SavedResponse {
  assessment_question_id: number;
  selected_options: string[];
  answered_at: string;
}

export interface AssessmentSummary {
  id: number;
  course_id: number;
  course_name: string;
  status: AssessmentStatus;
  question_count: number;
  answered_count: number;
  correct_questions: number | null;
  accuracy: number | null;
  created_at: string;
  submitted_at: string | null;
}

export interface AssessmentListResponse {
  count: number;
  assessments: AssessmentSummary[];
}

export interface DiagnosticResult {
  assessment_id: number;
  course_id: number;
  course_name: string;
  submitted_at: string;
  total_questions: number;
  answered_questions: number;
  correct_questions: number;
  total_points: number;
  earned_points: number;
  accuracy: number;
  report_policy_version: string;
  covered_knowledge_nodes: number;
  needs_attention_nodes: number;
  knowledge_performance: DiagnosticNodePerformance[];
  question_reviews: DiagnosticQuestionReview[];
}

export type EvidenceStatus = 'not_assessed' | 'limited_evidence' | 'basic_evidence';
export type PreliminaryStatus =
  | 'not_assessed'
  | 'limited_evidence'
  | 'needs_attention'
  | 'partially_correct'
  | 'good_performance';

export interface DiagnosticHistoricalNode {
  historical_node_id: number;
  historical_node_name: string;
  map_available: boolean;
}

export interface DiagnosticNodePerformance extends DiagnosticHistoricalNode {
  question_count: number;
  answered_count: number;
  correct_count: number;
  incorrect_count: number;
  unanswered_count: number;
  accuracy: number | null;
  evidence_status: EvidenceStatus;
  preliminary_status: PreliminaryStatus;
}

export interface DiagnosticSourceReference {
  material_id: number | null;
  material_title: string | null;
  source_reference: string;
  excerpt: string | null;
  is_accessible: boolean;
}

export interface DiagnosticQuestionReview {
  assessment_question_id: number;
  order_index: number;
  question_type: DiagnosticQuestionType;
  stem: string;
  options: QuestionOption[];
  selected_options: string[];
  correct_answer: string[];
  explanation: string;
  is_correct: boolean;
  points_awarded: number;
  primary_node: DiagnosticHistoricalNode;
  secondary_nodes: DiagnosticHistoricalNode[];
  source_refs: DiagnosticSourceReference[];
}

export type AnswerSaveState = 'idle' | 'unsaved' | 'saving' | 'saved' | 'failed';
