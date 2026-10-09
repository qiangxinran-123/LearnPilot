from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.core.settings import Settings, get_settings
from backend.app.db.models import KnowledgeNode, Material, User
from backend.app.db.session import get_db
from backend.app.repositories import (
    CourseRepository,
    KnowledgeCanonicalizationRunRepository,
    KnowledgeNodeRepository,
    MaterialContentRepository,
    MaterialRepository,
    UserRepository,
)
from backend.app.services.course_service import ResourceNotFoundError
from backend.app.services.knowledge_canonicalization_service import (
    KnowledgeCanonicalizationError,
    KnowledgeCanonicalizationService,
    get_knowledge_canonicalization_service,
)
from backend.app.services.knowledge_extraction_service import (
    KnowledgeExtractionError,
    KnowledgeExtractionService,
    get_knowledge_extraction_service,
)
from backend.app.services.knowledge_relationship_service import (
    KnowledgeRelationshipError,
    KnowledgeRelationshipService,
    get_knowledge_relationship_service,
)


class CourseKnowledgeBuildError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class CourseKnowledgeBuildResult:
    course_id: int
    material_count: int
    node_count: int
    contains_edge_count: int
    prerequisite_edge_count: int
    reused: bool


@dataclass(frozen=True)
class _CanonicalModelCheckpoint:
    run_id: int | None
    active_managed_node_ids: frozenset[int]


class CourseKnowledgeBuildService:
    """Thin orchestration for the established M3-B, M3-C, and M3-D stages.

    This service intentionally owns no extraction, canonicalization, or relationship
    inference logic. Its responsibility is limited to validating that a course has
    usable material, invoking the existing stage services in order, and restoring the
    previously active canonical model if the final stage cannot publish a coherent
    relationship set.
    """

    def __init__(
        self,
        session: Session,
        course_repository: CourseRepository,
        material_repository: MaterialRepository,
        content_repository: MaterialContentRepository,
        canonicalization_run_repository: KnowledgeCanonicalizationRunRepository,
        node_repository: KnowledgeNodeRepository,
        user_repository: UserRepository,
        settings: Settings,
        extraction_service: KnowledgeExtractionService,
        canonicalization_service: KnowledgeCanonicalizationService,
        relationship_service: KnowledgeRelationshipService,
    ) -> None:
        self.session = session
        self.course_repository = course_repository
        self.material_repository = material_repository
        self.content_repository = content_repository
        self.canonicalization_run_repository = canonicalization_run_repository
        self.node_repository = node_repository
        self.user_repository = user_repository
        self.settings = settings
        self.extraction_service = extraction_service
        self.canonicalization_service = canonicalization_service
        self.relationship_service = relationship_service

    def build(self, course_id: int) -> CourseKnowledgeBuildResult:
        ready_materials = self._load_ready_materials(course_id)
        checkpoint = self._capture_checkpoint(course_id)

        extraction_results = []
        try:
            for material in ready_materials:
                extraction_results.append(self.extraction_service.extract(course_id, material.id, regenerate=False))
            canonicalization_result = self.canonicalization_service.canonicalize(
                course_id,
                regenerate=False,
            )
        except (KnowledgeExtractionError, KnowledgeCanonicalizationError) as error:
            raise self._stage_error(error) from error

        try:
            relationship_result = self.relationship_service.generate_relationships(
                course_id,
                regenerate=False,
            )
        except KnowledgeRelationshipError as error:
            if not canonicalization_result.reused:
                self._restore_checkpoint(course_id, checkpoint)
            raise self._stage_error(error) from error

        return CourseKnowledgeBuildResult(
            course_id=course_id,
            material_count=len(ready_materials),
            node_count=len(canonicalization_result.nodes),
            contains_edge_count=sum(edge.relation_type.value == "contains" for edge in relationship_result.edges),
            prerequisite_edge_count=sum(
                edge.relation_type.value == "prerequisite" for edge in relationship_result.edges
            ),
            reused=(
                all(result.reused for result in extraction_results)
                and canonicalization_result.reused
                and relationship_result.reused
            ),
        )

    def _load_ready_materials(self, course_id: int) -> list[Material]:
        with self.session.begin():
            owner = self._get_or_create_owner()
            self._require_course(course_id, owner.id)
            ready_materials = [
                material
                for material in self.material_repository.list_for_course(course_id)
                if self._is_ready_material(material)
            ]
            if not ready_materials:
                raise CourseKnowledgeBuildError(
                    "KNOWLEDGE_MODEL_BUILD_NOT_READY",
                    "At least one successfully parsed course material is required before building a knowledge model.",
                )
            return ready_materials

    def _is_ready_material(self, material: Material) -> bool:
        if material.extraction_status not in {"SUCCESS", "EXTRACTED"}:
            return False
        content = self.content_repository.get_for_material(material.id)
        return content is not None and bool(content.plain_text.strip())

    def _capture_checkpoint(self, course_id: int) -> _CanonicalModelCheckpoint:
        with self.session.begin():
            current_run = self.canonicalization_run_repository.get_current_for_course(course_id)
            active_managed_node_ids = frozenset(
                node.id
                for node in self.node_repository.list_all_by_course(course_id)
                if node.managed_by_canonicalization and node.is_active
            )
            return _CanonicalModelCheckpoint(
                run_id=current_run.id if current_run is not None else None,
                active_managed_node_ids=active_managed_node_ids,
            )

    def _restore_checkpoint(self, course_id: int, checkpoint: _CanonicalModelCheckpoint) -> None:
        """Restore publication flags while retaining immutable run history."""

        with self.session.begin():
            self.canonicalization_run_repository.clear_current(course_id)
            if checkpoint.run_id is not None:
                previous_run = self.canonicalization_run_repository.get_by_id(checkpoint.run_id)
                if previous_run is not None:
                    previous_run.is_current = True
                    self.canonicalization_run_repository.save(previous_run)

            for node in self._managed_nodes(course_id):
                node.is_active = node.id in checkpoint.active_managed_node_ids
                self.node_repository.update(node)

    def _managed_nodes(self, course_id: int) -> Iterable[KnowledgeNode]:
        return (node for node in self.node_repository.list_all_by_course(course_id) if node.managed_by_canonicalization)

    @staticmethod
    def _stage_error(
        error: KnowledgeExtractionError | KnowledgeCanonicalizationError | KnowledgeRelationshipError,
    ) -> CourseKnowledgeBuildError:
        if error.code.endswith("_NOT_READY"):
            return CourseKnowledgeBuildError("KNOWLEDGE_MODEL_BUILD_NOT_READY", error.message)
        if error.code.endswith("_INVALID_OUTPUT"):
            return CourseKnowledgeBuildError("KNOWLEDGE_MODEL_BUILD_INVALID_OUTPUT", error.message)
        return CourseKnowledgeBuildError("KNOWLEDGE_MODEL_BUILD_FAILED", error.message)

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


def get_course_knowledge_build_service(
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> CourseKnowledgeBuildService:
    return CourseKnowledgeBuildService(
        session=session,
        course_repository=CourseRepository(session),
        material_repository=MaterialRepository(session),
        content_repository=MaterialContentRepository(session),
        canonicalization_run_repository=KnowledgeCanonicalizationRunRepository(session),
        node_repository=KnowledgeNodeRepository(session),
        user_repository=UserRepository(session),
        settings=settings,
        extraction_service=get_knowledge_extraction_service(session=session, settings=settings),
        canonicalization_service=get_knowledge_canonicalization_service(session=session, settings=settings),
        relationship_service=get_knowledge_relationship_service(session=session, settings=settings),
    )


__all__ = [
    "CourseKnowledgeBuildError",
    "CourseKnowledgeBuildResult",
    "CourseKnowledgeBuildService",
    "get_course_knowledge_build_service",
]
