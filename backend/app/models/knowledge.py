from __future__ import annotations

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


def normalize_knowledge_name(name: str) -> str:
    """Apply deterministic M3-A normalization without semantic inference."""

    return " ".join(name.split()).casefold()
