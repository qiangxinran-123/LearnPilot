from __future__ import annotations

import re
import unicodedata
from enum import StrEnum


class KnowledgeImportance(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class KnowledgeDifficulty(StrEnum):
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class KnowledgeRelationType(StrEnum):
    """Directed relationship semantics for the course knowledge model."""

    # source is the parent concept; target is the child concept.
    CONTAINS = "contains"
    # source is required knowledge; target is the dependent knowledge.
    PREREQUISITE = "prerequisite"


class KnowledgeExtractionStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class KnowledgeCanonicalizationStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class KnowledgeRelationshipStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class KnowledgeResolutionType(StrEnum):
    EXACT = "exact"
    SEMANTIC_MERGE = "semantic_merge"
    NEW_NODE = "new_node"


class KnowledgeEdgeEvidenceType(StrEnum):
    MATERIAL = "material"
    MODEL_INFERENCE = "model_inference"
    STRUCTURAL = "structural"


def normalize_knowledge_name(name: str) -> str:
    """Apply conservative deterministic normalization without semantic inference."""

    normalized = unicodedata.normalize("NFKC", name)
    normalized = normalized.translate(str.maketrans({"‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-"}))
    normalized = re.sub(r"\s*-\s*", "-", normalized)
    return " ".join(normalized.split()).casefold()
