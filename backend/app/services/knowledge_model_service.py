from __future__ import annotations

from fastapi import Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.settings import Settings, get_settings
from backend.app.db.models import KnowledgeEdge, KnowledgeNode, KnowledgeSource, Material, User
from backend.app.db.session import get_db
from backend.app.models import normalize_knowledge_name
from backend.app.repositories import (
    CourseRepository,
    KnowledgeEdgeRepository,
    KnowledgeNodeRepository,
    KnowledgeSourceRepository,
    MaterialContentRepository,
    MaterialRepository,
    UserRepository,
)
from backend.app.schemas.knowledge import (
    KnowledgeEdgeCreate,
    KnowledgeNodeCreate,
    KnowledgeNodeUpdate,
    KnowledgeSourceCreate,
)
from backend.app.services.course_service import ResourceNotFoundError
from backend.app.services.knowledge_relationship_validation import (
    KnowledgeRelationshipValidationError,
    RelationshipEdgeSpec,
    validate_relationship_edges,
)


class KnowledgeModelError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class KnowledgeNodeNotFoundError(KnowledgeModelError):
    def __init__(self) -> None:
        super().__init__("KNOWLEDGE_NODE_NOT_FOUND", "Knowledge node not found.")


class KnowledgeModelService:
    def __init__(
        self,
        session: Session,
        course_repository: CourseRepository,
        material_repository: MaterialRepository,
        content_repository: MaterialContentRepository,
        node_repository: KnowledgeNodeRepository,
        edge_repository: KnowledgeEdgeRepository,
        source_repository: KnowledgeSourceRepository,
        user_repository: UserRepository,
        settings: Settings,
    ) -> None:
        self.session = session
        self.course_repository = course_repository
        self.material_repository = material_repository
        self.content_repository = content_repository
        self.node_repository = node_repository
        self.edge_repository = edge_repository
        self.source_repository = source_repository
        self.user_repository = user_repository
        self.settings = settings

    def get_knowledge_model(self, course_id: int) -> tuple[list[KnowledgeNode], list[KnowledgeEdge]]:
        with self.session.begin():
            owner = self._get_or_create_owner()
            self._require_course(course_id, owner.id)
            return (
                self.node_repository.list_by_course(course_id),
                self.edge_repository.list_current_by_course(course_id),
            )

    def get_node_detail(
        self, course_id: int, node_id: int
    ) -> tuple[KnowledgeNode, list[KnowledgeSource], list[KnowledgeEdge]]:
        with self.session.begin():
            owner = self._get_or_create_owner()
            self._require_course(course_id, owner.id)
            node = self.node_repository.get_by_id(node_id)
            if node is None or node.course_id != course_id or not node.is_active:
                raise KnowledgeNodeNotFoundError()
            return (
                node,
                self.source_repository.list_for_node(node_id),
                self.edge_repository.list_current_for_node(node_id),
            )

    def create_node(self, course_id: int, payload: KnowledgeNodeCreate) -> KnowledgeNode:
        with self.session.begin():
            owner = self._get_or_create_owner()
            self._require_course(course_id, owner.id)
            return self.node_repository.create(
                KnowledgeNode(
                    course_id=course_id,
                    name=payload.name,
                    normalized_name=normalize_knowledge_name(payload.name),
                    description=payload.description,
                    importance=payload.importance,
                    difficulty=payload.difficulty,
                )
            )

    def update_node(self, course_id: int, node_id: int, payload: KnowledgeNodeUpdate) -> KnowledgeNode:
        with self.session.begin():
            owner = self._get_or_create_owner()
            self._require_course(course_id, owner.id)
            node = self._require_node_for_course(node_id, course_id, hide_mismatch=True)
            changes = payload.model_dump(exclude_unset=True)
            if "name" in changes:
                node.name = changes["name"]
                node.normalized_name = normalize_knowledge_name(changes["name"])
            for field in ("description", "importance", "difficulty"):
                if field in changes:
                    setattr(node, field, changes[field])
            return self.node_repository.update(node)

    def delete_node(self, course_id: int, node_id: int) -> None:
        with self.session.begin():
            owner = self._get_or_create_owner()
            self._require_course(course_id, owner.id)
            node = self._require_node_for_course(node_id, course_id, hide_mismatch=True)
            self.node_repository.delete(node)

    def create_edge(self, course_id: int, payload: KnowledgeEdgeCreate) -> KnowledgeEdge:
        if payload.source_node_id == payload.target_node_id:
            raise KnowledgeModelError("KNOWLEDGE_SELF_EDGE", "A knowledge node cannot relate to itself.")
        try:
            with self.session.begin():
                owner = self._get_or_create_owner()
                self._require_course(course_id, owner.id)
                self._require_node_for_course(payload.source_node_id, course_id)
                self._require_node_for_course(payload.target_node_id, course_id)
                if self.edge_repository.exists(
                    course_id,
                    payload.source_node_id,
                    payload.target_node_id,
                    payload.relation_type,
                ):
                    raise KnowledgeModelError(
                        "KNOWLEDGE_DUPLICATE_EDGE",
                        "The knowledge edge already exists.",
                    )
                try:
                    validate_relationship_edges(
                        node_ids={node.id for node in self.node_repository.list_by_course(course_id)},
                        edges=[
                            *(
                                RelationshipEdgeSpec(
                                    edge.source_node_id,
                                    edge.target_node_id,
                                    edge.relation_type,
                                )
                                for edge in self.edge_repository.list_current_by_course(course_id)
                            ),
                            RelationshipEdgeSpec(
                                payload.source_node_id,
                                payload.target_node_id,
                                payload.relation_type,
                            ),
                        ],
                    )
                except KnowledgeRelationshipValidationError as error:
                    raise KnowledgeModelError("KNOWLEDGE_EDGE_INVALID", str(error)) from error
                return self.edge_repository.create(
                    KnowledgeEdge(
                        course_id=course_id,
                        source_node_id=payload.source_node_id,
                        target_node_id=payload.target_node_id,
                        relation_type=payload.relation_type,
                    )
                )
        except IntegrityError as error:
            raise KnowledgeModelError("KNOWLEDGE_EDGE_INVALID", "The knowledge edge is invalid.") from error

    def create_source(self, course_id: int, node_id: int, payload: KnowledgeSourceCreate) -> KnowledgeSource:
        try:
            with self.session.begin():
                owner = self._get_or_create_owner()
                self._require_course(course_id, owner.id)
                node = self._require_node_for_course(node_id, course_id)
                material = self.material_repository.get_by_id(payload.material_id)
                if material is None:
                    raise KnowledgeModelError(
                        "KNOWLEDGE_SOURCE_INVALID",
                        "The source material does not exist.",
                    )
                if material.course_id != node.course_id:
                    raise KnowledgeModelError(
                        "KNOWLEDGE_COURSE_MISMATCH",
                        "Knowledge node and source material must belong to the same course.",
                    )
                self._require_source_reference(material, payload.source_reference)
                if self.source_repository.exists(node_id, material.id, payload.source_reference):
                    raise KnowledgeModelError(
                        "KNOWLEDGE_SOURCE_INVALID",
                        "The knowledge source already exists.",
                    )
                return self.source_repository.create(
                    KnowledgeSource(
                        knowledge_node_id=node_id,
                        material_id=material.id,
                        source_reference=payload.source_reference,
                        excerpt=payload.excerpt,
                    )
                )
        except IntegrityError as error:
            raise KnowledgeModelError("KNOWLEDGE_SOURCE_INVALID", "The knowledge source is invalid.") from error

    def _get_or_create_owner(self) -> User:
        owner = self.user_repository.get_by_email(self.settings.legacy_bootstrap_user)
        if owner is not None:
            return owner
        return self.user_repository.add(
            User(
                email=self.settings.legacy_bootstrap_user,
                display_name=self.settings.legacy_bootstrap_user_display_name,
                is_active=True,
            )
        )

    def _require_course(self, course_id: int, owner_id: int) -> None:
        if self.course_repository.get_for_owner(course_id, owner_id) is None:
            raise ResourceNotFoundError("Course")

    def _require_node_for_course(self, node_id: int, course_id: int, *, hide_mismatch: bool = False) -> KnowledgeNode:
        node = self.node_repository.get_by_id(node_id)
        if node is None:
            raise KnowledgeNodeNotFoundError()
        if node.course_id != course_id:
            if hide_mismatch:
                raise KnowledgeNodeNotFoundError()
            raise KnowledgeModelError(
                "KNOWLEDGE_COURSE_MISMATCH",
                "All knowledge model entities must belong to the same course.",
            )
        return node

    def _require_source_reference(self, material: Material, source_reference: str) -> None:
        content = self.content_repository.get_for_material(material.id)
        if content is None:
            raise KnowledgeModelError(
                "KNOWLEDGE_SOURCE_INVALID",
                "The source material has no traceable parsed content.",
            )
        references = {
            str(segment.get("source_reference"))
            for segment in content.segments
            if isinstance(segment, dict) and segment.get("source_reference") is not None
        }
        if source_reference not in references:
            raise KnowledgeModelError(
                "KNOWLEDGE_SOURCE_INVALID",
                "The source reference does not exist in the material content.",
            )


def get_knowledge_model_service(
    session: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> KnowledgeModelService:
    return KnowledgeModelService(
        session=session,
        course_repository=CourseRepository(session),
        material_repository=MaterialRepository(session),
        content_repository=MaterialContentRepository(session),
        node_repository=KnowledgeNodeRepository(session),
        edge_repository=KnowledgeEdgeRepository(session),
        source_repository=KnowledgeSourceRepository(session),
        user_repository=UserRepository(session),
        settings=settings,
    )


__all__ = [
    "KnowledgeModelError",
    "KnowledgeModelService",
    "KnowledgeNodeNotFoundError",
    "get_knowledge_model_service",
]
