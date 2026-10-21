export type KnowledgeImportance = 'low' | 'medium' | 'high';
export type KnowledgeDifficulty = 'basic' | 'intermediate' | 'advanced';
export type KnowledgeRelationType = 'contains' | 'prerequisite';
export type KnowledgeEdgeEvidenceType = 'material' | 'model_inference' | 'structural';

export interface KnowledgeNode {
  id: number;
  course_id: number;
  name: string;
  normalized_name: string;
  description: string;
  importance: KnowledgeImportance;
  difficulty: KnowledgeDifficulty;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeEdge {
  id: number;
  course_id: number;
  source_node_id: number;
  target_node_id: number;
  relation_type: KnowledgeRelationType;
  created_at: string;
  updated_at: string;
}

export interface KnowledgeSource {
  id: number;
  knowledge_node_id: number;
  material_id: number;
  source_reference: string;
  excerpt: string | null;
  material_title?: string | null;
  original_text_excerpt?: string | null;
  original_text_truncated?: boolean;
  created_at: string;
}

export interface KnowledgeEdgeEvidence {
  id: number;
  knowledge_edge_id: number;
  course_id: number;
  material_id: number | null;
  source_reference: string | null;
  excerpt: string | null;
  evidence_type: KnowledgeEdgeEvidenceType;
  reason: string;
  created_at: string;
}

export interface KnowledgeRelationshipEdge extends KnowledgeEdge {
  evidence: KnowledgeEdgeEvidence[];
}

export interface KnowledgeRelationshipRun {
  id: number;
  course_id: number;
  status: 'pending' | 'running' | 'success' | 'failed';
  node_count: number;
  contains_edge_count: number;
  prerequisite_edge_count: number;
  is_current: boolean;
}

export interface KnowledgeModelResponse {
  course_id: number;
  nodes: KnowledgeNode[];
  edges: KnowledgeEdge[];
}

export interface KnowledgeNodeDetailResponse {
  node: KnowledgeNode;
  sources: KnowledgeSource[];
  related_edges: KnowledgeEdge[];
}

export interface KnowledgeRelationshipsResponse {
  run: KnowledgeRelationshipRun;
  contains_edges: KnowledgeRelationshipEdge[];
  prerequisite_edges: KnowledgeRelationshipEdge[];
  reused: boolean;
}
export interface KnowledgeModelBuildResponse {
  course_id: number;
  material_count: number;
  node_count: number;
  contains_edge_count: number;
  prerequisite_edge_count: number;
  reused: boolean;
}

export type KnowledgeBuildState =
  | 'no_materials'
  | 'not_ready'
  | 'not_built'
  | 'running'
  | 'ready'
  | 'update_available'
  | 'failed'
  | 'update_failed';

export type KnowledgeBuildStage = 'queued' | 'extracting' | 'canonicalizing' | 'relationships';

export interface KnowledgeBuildStatus {
  course_id: number;
  state: KnowledgeBuildState;
  stage: KnowledgeBuildStage | null;
  job_id: number | null;
  material_count: number;
  ready_material_count: number;
  node_count: number;
  contains_edge_count: number;
  prerequisite_edge_count: number;
  needs_update: boolean;
  can_build: boolean;
  has_model: boolean;
  error_code: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface KnowledgeBuildJobResponse {
  job_id: number;
  status: 'running' | 'success';
  stage: KnowledgeBuildStage | null;
  reused: boolean;
}

export interface CanonicalNodePage {
  course_id: number;
  total: number;
  offset: number;
  limit: number;
  nodes: KnowledgeNode[];
}
