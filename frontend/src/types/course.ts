export interface CourseSummary {
  id: number;
  name: string;
  description: string;
  category?: string | null;
  learning_goal?: string | null;
  target_date?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  material_count?: number;
  /** Retained only while older imported CampusAI data exposes it. */
  semester?: string;
}

export interface CourseInput {
  name: string;
  description?: string;
  category?: string | null;
  learning_goal?: string | null;
  target_date?: string | null;
}

export interface CourseListResponse {
  count: number;
  courses: CourseSummary[];
}

export interface CourseDeleteResponse {
  id: number;
  deleted: boolean;
}

export type ExtractionStatus =
  | 'SUCCESS'
  /** Legacy parsed material status retained for M2 compatibility. */
  | 'EXTRACTED'
  | 'EMPTY_CONTENT'
  | 'DECODE_ERROR'
  | 'PARSE_FAILED'
  | 'UNSUPPORTED_FORMAT'
  | 'NOT_REQUESTED'
  | 'LEGACY_CONTENT_PARTIAL'
  | 'LEGACY_CONTENT_UNAVAILABLE';

export interface MaterialSummaryCard {
  id: number;
  question: string;
  answer: string;
  knowledge_hint?: string | null;
  source_reference?: string | null;
  order_index: number;
  source_material_id: number;
  card_type: string;
  created_at: string;
}

export interface Material {
  id: number;
  course_id: number;
  title: string;
  type: string;
  summary: string;
  filename?: string | null;
  original_filename?: string | null;
  media_type?: string | null;
  extension?: string | null;
  size_bytes: number;
  storage_status: string;
  text_preview: string;
  text_length: number;
  extracted: boolean;
  extraction_status: ExtractionStatus;
  extraction_error_code?: string | null;
  extraction_error_message?: string | null;
  parser_name?: string | null;
  parser_version?: string | null;
  page_count: number;
  created_at?: string | null;
  updated_at?: string | null;
  ai_summary?: string | null;
  summary_generated?: boolean | null;
  summary_method?: string | null;
  summary_updated_at?: string | null;
  cards?: MaterialSummaryCard[] | null;
  cards_generated?: boolean | null;
  cards_generated_at?: string | null;
  cards_method?: string | null;
}

export interface MaterialListResponse {
  course_id: number;
  count: number;
  materials: Material[];
}

export interface MaterialContentResponse {
  material_id: number;
  text: string;
  offset: number;
  limit: number;
  total_length: number;
  has_more: boolean;
  page_count: number;
  parser_name: string;
  parser_version: string;
}

export interface SummaryContent {
  overview: string;
  key_concepts: string[];
  important_points: string[];
  common_mistakes: string[];
  review_suggestions: string[];
  provider: string;
  model: string;
  prompt_version: string;
  generated_at: string;
  updated_at: string;
}

export interface MaterialSummaryResponse {
  id: number;
  material_id: number;
  summary: SummaryContent | null;
  ai_summary: string | null;
  summary_generated: boolean;
  summary_method: string | null;
  summary_updated_at: string | null;
}

export interface CardGenerationResponse {
  material_id: number;
  count: number;
  cards: MaterialSummaryCard[];
  cards_generated: boolean;
  cards_generated_at: string | null;
  cards_method: string | null;
}

export interface MaterialQAResponse {
  material_id: number;
  answer: string;
  references: string[];
  grounded: boolean;
  provider?: string | null;
  model?: string | null;
  prompt_version?: string | null;
}
