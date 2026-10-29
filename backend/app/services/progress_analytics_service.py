from collections import deque
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.orm import Session

from backend.app.core.settings import Settings
from backend.app.models import KnowledgeRelationType, MasteryStatus
from backend.app.repositories import KnowledgeNodeRepository
from backend.app.repositories.knowledge_edge_repository import KnowledgeEdgeRepository
from backend.app.schemas.progress import ProgressKnowledge, ProgressNode, ProgressOverview
from backend.app.services.mastery_read_service import MasteryReadError, MasteryReadService


class ProgressAnalyticsService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.mastery = MasteryReadService(session, settings)

    def knowledge(self, course_id: int) -> ProgressKnowledge:
        # M5 owns authorization, freshness, score, confidence, and evidence semantics.
        states = self.mastery.course_mastery(course_id)
        nodes = KnowledgeNodeRepository(self.session).list_by_course(course_id)
        node_ids = {node.id for node in nodes}
        parents: dict[int, set[int]] = {node_id: set() for node_id in node_ids}
        children: dict[int, set[int]] = {node_id: set() for node_id in node_ids}
        for edge in KnowledgeEdgeRepository(self.session).list_current_by_course(course_id):
            if edge.relation_type != KnowledgeRelationType.CONTAINS:
                continue
            if edge.source_node_id in node_ids and edge.target_node_id in node_ids:
                children[edge.source_node_id].add(edge.target_node_id)
                parents[edge.target_node_id].add(edge.source_node_id)

        # Kahn's algorithm rejects cycles rather than silently inventing a denominator.
        indegree = {node_id: len(value) for node_id, value in parents.items()}
        queue = deque(node_id for node_id in sorted(node_ids) if indegree[node_id] == 0)
        visited = 0
        while queue:
            node_id = queue.popleft()
            visited += 1
            for child in sorted(children[node_id]):
                indegree[child] -= 1
                if indegree[child] == 0:
                    queue.append(child)
        if visited != len(node_ids):
            raise MasteryReadError("INVALID_KNOWLEDGE_HIERARCHY", "Knowledge hierarchy contains a cycle.")

        by_id = {state.knowledge_node_id: state for state in states.nodes}
        leaves = []
        for node in nodes:
            if children[node.id]:
                continue
            state = by_id[node.id]
            leaves.append(
                ProgressNode(
                    node_id=node.id,
                    name=node.name,
                    parent_ids=sorted(parents[node.id]),
                    mastery_score=state.mastery_score,
                    mastery_status=state.mastery_status,
                    confidence_level=state.confidence_level,
                    evidence_count=state.evidence_count,
                    calculation_state=state.calculation_state,
                )
            )
        return ProgressKnowledge(course_id=course_id, nodes=leaves)

    def overview(self, course_id: int) -> ProgressOverview:
        nodes = self.knowledge(course_id).nodes
        assessed = [node for node in nodes if node.mastery_score is not None]
        average = (
            (sum((node.mastery_score for node in assessed), Decimal(0)) / len(assessed)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if assessed
            else None
        )
        counts = {status: 0 for status in MasteryStatus}
        for node in nodes:
            counts[node.mastery_status] += 1
        weak = [
            node
            for node in assessed
            if node.mastery_status in {MasteryStatus.POSSIBLY_WEAK, MasteryStatus.NEEDS_ATTENTION}
        ]
        return ProgressOverview(
            course_id=course_id,
            overall_mastery=average,
            evaluated_node_count=len(assessed),
            evaluable_node_count=len(nodes),
            coverage_ratio=len(assessed) / len(nodes) if nodes else None,
            status_counts=counts,
            weak_nodes=weak,
        )
