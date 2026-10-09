"""Pure structural validation for the M3-D course knowledge model."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from backend.app.models import KnowledgeRelationType


@dataclass(frozen=True)
class RelationshipEdgeSpec:
    source_node_id: int
    target_node_id: int
    relation_type: KnowledgeRelationType


class KnowledgeRelationshipValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def validate_relationship_edges(
    *,
    node_ids: set[int],
    edges: Iterable[RelationshipEdgeSpec],
) -> None:
    """Validate directed edges against M3-D''s two independent graph semantics."""

    materialized = list(edges)
    seen: set[tuple[int, int, KnowledgeRelationType]] = set()
    for edge in materialized:
        if edge.source_node_id not in node_ids or edge.target_node_id not in node_ids:
            raise KnowledgeRelationshipValidationError(
                "KNOWLEDGE_RELATIONSHIP_UNKNOWN_NODE",
                "Relationship edges may only reference the current canonical node snapshot.",
            )
        if edge.source_node_id == edge.target_node_id:
            raise KnowledgeRelationshipValidationError(
                "KNOWLEDGE_RELATIONSHIP_SELF_EDGE",
                "A knowledge relationship cannot point to itself.",
            )
        key = (edge.source_node_id, edge.target_node_id, edge.relation_type)
        if key in seen:
            raise KnowledgeRelationshipValidationError(
                "KNOWLEDGE_RELATIONSHIP_DUPLICATE_EDGE",
                "A relationship type may appear only once for the same directed node pair.",
            )
        seen.add(key)

    contains_edges = [edge for edge in materialized if edge.relation_type == KnowledgeRelationType.CONTAINS]
    prerequisite_edges = [edge for edge in materialized if edge.relation_type == KnowledgeRelationType.PREREQUISITE]
    _validate_contains_forest(contains_edges)
    _validate_dag(prerequisite_edges, "KNOWLEDGE_PREREQUISITE_CYCLE", "Prerequisite relationships must form a DAG.")


def _validate_contains_forest(edges: list[RelationshipEdgeSpec]) -> None:
    parent_by_child: dict[int, int] = {}
    for edge in edges:
        existing_parent = parent_by_child.get(edge.target_node_id)
        if existing_parent is not None and existing_parent != edge.source_node_id:
            raise KnowledgeRelationshipValidationError(
                "KNOWLEDGE_CONTAINS_MULTIPLE_PARENTS",
                "A child concept can have at most one CONTAINS parent.",
            )
        parent_by_child[edge.target_node_id] = edge.source_node_id
    _validate_dag(edges, "KNOWLEDGE_CONTAINS_CYCLE", "CONTAINS relationships must form a forest.")


def _validate_dag(edges: list[RelationshipEdgeSpec], error_code: str, message: str) -> None:
    children: dict[int, list[int]] = defaultdict(list)
    state: dict[int, int] = {}
    for edge in edges:
        children[edge.source_node_id].append(edge.target_node_id)

    def visit(node_id: int) -> None:
        node_state = state.get(node_id, 0)
        if node_state == 1:
            raise KnowledgeRelationshipValidationError(error_code, message)
        if node_state == 2:
            return
        state[node_id] = 1
        for child_id in children[node_id]:
            visit(child_id)
        state[node_id] = 2

    for source_node_id in list(children):
        visit(source_node_id)
