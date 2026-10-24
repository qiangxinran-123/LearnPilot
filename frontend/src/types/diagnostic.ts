export type AssessmentStatus = 'draft' | 'ready' | 'in_progress' | 'submitted';
export type DiagnosticQuestionType = 'single_choice' | 'true_false' | 'multiple_choice';
export type QuestionDifficulty = 'easy' | 'medium' | 'hard';
export type QuestionValidationStatus = 'pending' | 'validated' | 'rejected';

export interface QuestionBankNode {
  knowledge_node_id: number;
  knowledge_node_name: string;
  has_validated_question: boolean;
  has_pending_question: boolean;
}

export interface QuestionBankReadiness {
  course_id: number;
  validated_count: number;
  pending_count: number;
  rejected_count: number;
  covered_core_nodes: number;
  total_core_nodes: number;
  minimum_required: number;
  required_questions: number;
  can_start: boolean;
  reason_code: string | null;
  required_nodes: QuestionBankNode[];
}

export interface QuestionBankSourceReference {
  material_id: number | null;
  material_title: string | null;
  source_reference: string;
  excerpt: string | null;
}

export interface QuestionBankItem {
  question_id: number;
  course_id: number;
  knowledge_node_id: number | null;
  knowledge_node_name: string | null;
  question_type: DiagnosticQuestionType;
  difficulty: QuestionDifficulty;
  stem: string;
  options: QuestionOption[];
  correct_answer: string[];
  explanation: string;
  source_refs: QuestionBankSourceReference[];
  validation_status: QuestionValidationStatus;
  created_at: string;
}

export interface QuestionBankListResponse {
  count: number;
  questions: QuestionBankItem[];
}

export interface DiagnosticQuestionGenerationResponse {
  provider: string;
  model: string;
  prompt_version: string;
  requested_count: number;
  accepted_count: number;
  questions: QuestionBankItem[];
}

export interface CourseQuestionPreparationFailure {
  knowledge_node_id: number;
  knowledge_node_name: string;
  code: string;
  message: string;
}

export interface CourseQuestionPreparationResponse {
  course_id: number;
  planned_count: number;
  generated_count: number;
  failed_count: number;
  pending_review_count: number;
  questions: QuestionBankItem[];
  failures: CourseQuestionPreparationFailure[];
}

export interface QuestionReviewResponse {
  question: QuestionBankItem;
}

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

export interface AssessmentDiscardResponse {
  assessment_id: number;
  discarded: true;
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
