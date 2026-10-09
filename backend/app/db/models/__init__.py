from backend.app.db.models.course import Course
from backend.app.db.models.knowledge_candidate import KnowledgeCandidate
from backend.app.db.models.knowledge_candidate_resolution import KnowledgeCandidateResolution
from backend.app.db.models.knowledge_candidate_source import KnowledgeCandidateSource
from backend.app.db.models.knowledge_canonicalization_run import KnowledgeCanonicalizationRun
from backend.app.db.models.knowledge_edge import KnowledgeEdge
from backend.app.db.models.knowledge_edge_evidence import KnowledgeEdgeEvidence
from backend.app.db.models.knowledge_extraction_run import KnowledgeExtractionRun
from backend.app.db.models.knowledge_node import KnowledgeNode
from backend.app.db.models.knowledge_relationship_run import KnowledgeRelationshipRun
from backend.app.db.models.knowledge_source import KnowledgeSource
from backend.app.db.models.material import Material
from backend.app.db.models.material_content import MaterialContent
from backend.app.db.models.material_summary import MaterialSummary
from backend.app.db.models.study_card import StudyCard
from backend.app.db.models.user import User

__all__ = [
    "Course",
    "KnowledgeCandidate",
    "KnowledgeCandidateResolution",
    "KnowledgeCandidateSource",
    "KnowledgeCanonicalizationRun",
    "KnowledgeEdge",
    "KnowledgeEdgeEvidence",
    "KnowledgeRelationshipRun",
    "KnowledgeExtractionRun",
    "KnowledgeNode",
    "KnowledgeSource",
    "Material",
    "MaterialContent",
    "MaterialSummary",
    "StudyCard",
    "User",
]
