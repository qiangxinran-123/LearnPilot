from backend.app.repositories.course_knowledge_build_state_repository import CourseKnowledgeBuildStateRepository
from backend.app.repositories.course_repository import CourseRepository
from backend.app.repositories.knowledge_candidate_repository import KnowledgeCandidateRepository
from backend.app.repositories.knowledge_candidate_resolution_repository import KnowledgeCandidateResolutionRepository
from backend.app.repositories.knowledge_candidate_source_repository import KnowledgeCandidateSourceRepository
from backend.app.repositories.knowledge_canonicalization_run_repository import KnowledgeCanonicalizationRunRepository
from backend.app.repositories.knowledge_edge_evidence_repository import KnowledgeEdgeEvidenceRepository
from backend.app.repositories.knowledge_edge_repository import KnowledgeEdgeRepository
from backend.app.repositories.knowledge_extraction_run_repository import KnowledgeExtractionRunRepository
from backend.app.repositories.knowledge_node_repository import KnowledgeNodeRepository
from backend.app.repositories.knowledge_relationship_run_repository import KnowledgeRelationshipRunRepository
from backend.app.repositories.knowledge_source_repository import KnowledgeSourceRepository
from backend.app.repositories.material_content_repository import MaterialContentRepository
from backend.app.repositories.material_repository import MaterialRepository
from backend.app.repositories.material_summary_repository import MaterialSummaryRepository
from backend.app.repositories.study_card_repository import StudyCardRepository
from backend.app.repositories.user_repository import UserRepository

__all__ = [
    "CourseRepository",
    "CourseKnowledgeBuildStateRepository",
    "KnowledgeCandidateRepository",
    "KnowledgeCandidateResolutionRepository",
    "KnowledgeCandidateSourceRepository",
    "KnowledgeCanonicalizationRunRepository",
    "KnowledgeEdgeRepository",
    "KnowledgeEdgeEvidenceRepository",
    "KnowledgeRelationshipRunRepository",
    "KnowledgeExtractionRunRepository",
    "KnowledgeNodeRepository",
    "KnowledgeSourceRepository",
    "MaterialContentRepository",
    "MaterialRepository",
    "MaterialSummaryRepository",
    "StudyCardRepository",
    "UserRepository",
]
