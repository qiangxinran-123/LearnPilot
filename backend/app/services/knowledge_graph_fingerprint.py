import hashlib
import json

from sqlalchemy.orm import Session

from backend.app.models import KnowledgeRelationType
from backend.app.repositories import KnowledgeNodeRepository
from backend.app.repositories.knowledge_edge_repository import KnowledgeEdgeRepository


def knowledge_graph_fingerprint(session: Session, course_id: int) -> str:
    nodes = {node.id for node in KnowledgeNodeRepository(session).list_by_course(course_id)}
    edges = {
        (edge.source_node_id, edge.target_node_id)
        for edge in KnowledgeEdgeRepository(session).list_current_by_course(course_id)
        if edge.relation_type == KnowledgeRelationType.CONTAINS
        and edge.source_node_id in nodes
        and edge.target_node_id in nodes
    }
    payload = json.dumps({"nodes": sorted(nodes), "contains": sorted(edges)}, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
