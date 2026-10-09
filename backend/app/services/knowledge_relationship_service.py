from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.ai import AIServiceError, LLMClient, get_llm_client
from backend.app.ai.models import KnowledgeRelationshipEdgeDraft, KnowledgeRelationshipOutput
from backend.app.ai.prompts import knowledge_relationships as relationship_prompt
from backend.app.core.settings import Settings, get_settings
from backend.app.db.models import (
    KnowledgeEdge,
    KnowledgeEdgeEvidence,
    KnowledgeNode,
    KnowledgeRelationshipRun,
    User,
)
from backend.app.db.session import get_db
from backend.app.models import (
    KnowledgeEdgeEvidenceType,
    KnowledgeRelationshipStatus,
    KnowledgeRelationType,
)
from backend.app.repositories import (
    CourseRepository,
    KnowledgeCanonicalizationRunRepository,
    KnowledgeEdgeEvidenceRepository,
    KnowledgeEdgeRepository,
    KnowledgeNodeRepository,
    KnowledgeRelationshipRunRepository,
    KnowledgeSourceRepository,
    MaterialContentRepository,
    MaterialRepository,
    UserRepository,
)
from backend.app.services.course_service import ResourceNotFoundError
from backend.app.services.knowledge_relationship_validation import (
    KnowledgeRelationshipValidationError,
    RelationshipEdgeSpec,
    validate_relationship_edges,
)

logger = logging.getLogger(__name__)


class KnowledgeRelationshipError(ValueError):
    def __init__(self, code: str, message: str, *, rejected_edge_count: int = 0) -> None:
        self.code = code
        self.message = message
        self.rejected_edge_count = rejected_edge_count
        super().__init__(message)


@dataclass(frozen=True)
class RelationshipSource:
    material_id: int
    source_reference: str
    excerpt: str | None


@dataclass(frozen=True)
class RelationshipSnapshotNode:
    node: KnowledgeNode
    sources: list[RelationshipSource]


@dataclass(frozen=True)
class KnowledgeRelationshipSnapshot:
    course_id: int
    canonicalization_run_id: int
    nodes: list[RelationshipSnapshotNode]
    snapshot_hash: str


@dataclass(frozen=True)
class RelationshipPlan:
    source_node_id: int
    target_node_id: int
    relation_type: KnowledgeRelationType
    reason: str
    evidence: list[RelationshipSource]

    def as_spec(self) -> RelationshipEdgeSpec:
        return RelationshipEdgeSpec(
            source_node_id=self.source_node_id,
            target_node_id=self.target_node_id,
            relation_type=self.relation_type,
        )


@dataclass(frozen=True)
class KnowledgeRelationshipResult:
    run: KnowledgeRelationshipRun
    edges: list[KnowledgeEdge]
    evidence_by_edge_id: dict[int, list[KnowledgeEdgeEvidence]]
    reused: bool


class KnowledgeRelationshipService:
    def __init__(
        self,
        session: Session,
        course_repository: CourseRepository,
        canonicalization_run_repository: KnowledgeCanonicalizationRunRepository,
        node_repository: KnowledgeNodeRepository,
        source_repository: KnowledgeSourceRepository,
        material_repository: MaterialRepository,
        content_repository: MaterialContentRepository,
        run_repository: KnowledgeRelationshipRunRepository,
        edge_repository: KnowledgeEdgeRepository,
        evidence_repository: KnowledgeEdgeEvidenceRepository,
        user_repository: UserRepository,
        settings: Settings,
        llm_client_factory: Callable[[Settings], LLMClient] = get_llm_client,
    ) -> None:
        self.session = session
        self.course_repository = course_repository
        self.canonicalization_run_repository = canonicalization_run_repository
        self.node_repository = node_repository
        self.source_repository = source_repository
        self.material_repository = material_repository
        self.content_repository = content_repository
        self.run_repository = run_repository
        self.edge_repository = edge_repository
        self.evidence_repository = evidence_repository
        self.user_repository = user_repository
        self.settings = settings
        self.llm_client_factory = llm_client_factory

    def get_relationships(self, course_id: int) -> KnowledgeRelationshipResult:
        with self.session.begin():
            owner = self._get_or_create_owner()
            self._require_course(course_id, owner.id)
            run = self.run_repository.get_current_for_course(course_id)
            if run is None:
                run = self.run_repository.get_latest_for_course(course_id)
            if run is None:
                raise KnowledgeRelationshipError(
                    "KNOWLEDGE_RELATIONSHIP_NOT_READY",
                    "Knowledge relationships have not been generated for this course.",
                )
            if run.status != KnowledgeRelationshipStatus.SUCCESS:
                return KnowledgeRelationshipResult(run, [], {}, True)
            edges = self.edge_repository.list_for_run(run.id)
            return KnowledgeRelationshipResult(
                run,
                edges,
                self._evidence_by_edge_id(edges),
                True,
            )

    def generate_relationships(
        self,
        course_id: int,
        *,
        regenerate: bool = False,
    ) -> KnowledgeRelationshipResult:
        snapshot = self._load_snapshot(course_id)
        client: LLMClient | None = None
        if len(snapshot.nodes) >= 2:
            try:
                client = self.llm_client_factory(self.settings)
            except AIServiceError as error:
                raise self._map_ai_error(error) from error
            provider, model = self._client_identity(client)
        else:
            provider, model = "deterministic", "no-relationship-inference-v1"

        with self.session.begin():
            if not regenerate:
                current = self.run_repository.find_current_by_key(
                    course_id,
                    snapshot.snapshot_hash,
                    relationship_prompt.PROMPT_VERSION,
                    model,
                )
                if current is not None:
                    edges = self.edge_repository.list_for_run(current.id)
                    return KnowledgeRelationshipResult(
                        current,
                        edges,
                        self._evidence_by_edge_id(edges),
                        True,
                    )
            run = self.run_repository.create(
                KnowledgeRelationshipRun(
                    course_id=course_id,
                    knowledge_snapshot_hash=snapshot.snapshot_hash,
                    status=KnowledgeRelationshipStatus.RUNNING,
                    provider=provider,
                    model=model,
                    prompt_version=relationship_prompt.PROMPT_VERSION,
                    node_count=len(snapshot.nodes),
                    contains_edge_count=0,
                    prerequisite_edge_count=0,
                    rejected_edge_count=0,
                    is_current=False,
                )
            )
            run_id = run.id

        try:
            plans = self._infer_relationships(snapshot, client)
            with self.session.begin():
                current_snapshot = self._collect_snapshot(course_id)
                if current_snapshot.snapshot_hash != snapshot.snapshot_hash:
                    raise KnowledgeRelationshipError(
                        "KNOWLEDGE_RELATIONSHIP_NOT_READY",
                        "Canonical knowledge nodes changed during relationship generation; no model was replaced.",
                    )
                run = self.run_repository.get_by_id(run_id)
                if run is None:
                    raise KnowledgeRelationshipError(
                        "KNOWLEDGE_RELATIONSHIP_FAILED",
                        "Knowledge relationship run no longer exists.",
                    )
                self._validate_with_manual_edges(snapshot, plans)
                self.edge_repository.delete_generated_by_course(course_id)
                edges = self._persist_plans(run, plans)
                self.run_repository.clear_current(course_id)
                run.status = KnowledgeRelationshipStatus.SUCCESS
                run.contains_edge_count = sum(plan.relation_type == KnowledgeRelationType.CONTAINS for plan in plans)
                run.prerequisite_edge_count = sum(
                    plan.relation_type == KnowledgeRelationType.PREREQUISITE for plan in plans
                )
                run.rejected_edge_count = 0
                run.error_code = None
                run.error_message = None
                run.is_current = True
                run.completed_at = datetime.now(timezone.utc)
                self.run_repository.save(run)
                return KnowledgeRelationshipResult(
                    run,
                    edges,
                    self._evidence_by_edge_id(edges),
                    False,
                )
        except KnowledgeRelationshipError as error:
            self._mark_failed(run_id, error.code, error.message, error.rejected_edge_count)
            raise
        except AIServiceError as error:
            mapped = self._map_ai_error(error)
            self._mark_failed(run_id, mapped.code, mapped.message, mapped.rejected_edge_count)
            raise mapped from error
        except Exception as error:
            logger.exception("knowledge_relationship_generation_failed run_id=%s", run_id)
            mapped = KnowledgeRelationshipError(
                "KNOWLEDGE_RELATIONSHIP_FAILED",
                "Knowledge relationship generation failed before a valid model could be saved.",
            )
            self._mark_failed(run_id, mapped.code, mapped.message, mapped.rejected_edge_count)
            raise mapped from error

    def _load_snapshot(self, course_id: int) -> KnowledgeRelationshipSnapshot:
        with self.session.begin():
            owner = self._get_or_create_owner()
            self._require_course(course_id, owner.id)
            return self._collect_snapshot(course_id)

    def _collect_snapshot(self, course_id: int) -> KnowledgeRelationshipSnapshot:
        canonicalization_run = self.canonicalization_run_repository.get_current_for_course(course_id)
        if canonicalization_run is None:
            raise KnowledgeRelationshipError(
                "KNOWLEDGE_RELATIONSHIP_NOT_READY",
                "The course requires a current successful knowledge canonicalization before relationships can run.",
            )
        nodes = self.node_repository.list_by_course(course_id)
        if len(nodes) > self.settings.knowledge_relationship_max_nodes:
            raise KnowledgeRelationshipError(
                "KNOWLEDGE_RELATIONSHIP_NOT_READY",
                "The course exceeds the configured relationship-generation node limit.",
            )

        content_by_material: dict[int, object] = {}
        snapshot_nodes: list[RelationshipSnapshotNode] = []
        payload_nodes: list[dict[str, object]] = []
        for node in nodes:
            sources: list[RelationshipSource] = []
            for source in self.source_repository.list_for_node(node.id):
                material = self.material_repository.get_by_id(source.material_id)
                if material is None or material.course_id != course_id:
                    raise KnowledgeRelationshipError(
                        "KNOWLEDGE_RELATIONSHIP_NOT_READY",
                        "A canonical node has a source outside this course.",
                    )
                content = content_by_material.get(source.material_id)
                if content is None:
                    content = self.content_repository.get_for_material(source.material_id)
                    content_by_material[source.material_id] = content
                if content is None or not self._has_reference(content.segments, source.source_reference):
                    raise KnowledgeRelationshipError(
                        "KNOWLEDGE_RELATIONSHIP_NOT_READY",
                        "A canonical node has a stale material source reference.",
                    )
                sources.append(RelationshipSource(source.material_id, source.source_reference, source.excerpt))
            sources.sort(key=lambda item: (item.material_id, item.source_reference))
            snapshot_nodes.append(RelationshipSnapshotNode(node, sources))
            payload_nodes.append(
                {
                    "id": node.id,
                    "name": node.name,
                    "normalized_name": node.normalized_name,
                    "description": node.description,
                    "importance": node.importance.value,
                    "difficulty": node.difficulty.value,
                    "sources": [
                        {
                            "material_id": source.material_id,
                            "source_reference": source.source_reference,
                            "excerpt": source.excerpt or "",
                        }
                        for source in sources
                    ],
                }
            )
        encoded = json.dumps(
            {
                "course_id": course_id,
                "canonicalization_run_id": canonicalization_run.id,
                "nodes": payload_nodes,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        return KnowledgeRelationshipSnapshot(
            course_id=course_id,
            canonicalization_run_id=canonicalization_run.id,
            nodes=snapshot_nodes,
            snapshot_hash=hashlib.sha256(encoded).hexdigest(),
        )

    @staticmethod
    def _has_reference(segments: object, source_reference: str) -> bool:
        return any(
            isinstance(segment, dict) and segment.get("source_reference") == source_reference for segment in segments
        )

    def _infer_relationships(
        self,
        snapshot: KnowledgeRelationshipSnapshot,
        client: LLMClient | None,
    ) -> list[RelationshipPlan]:
        if len(snapshot.nodes) < 2:
            return []
        if client is None:
            raise KnowledgeRelationshipError(
                "KNOWLEDGE_RELATIONSHIP_FAILED",
                "Relationship inference requires a configured AI provider.",
            )

        last_error: KnowledgeRelationshipError | None = None
        feedback: str | None = None
        for attempt in range(self.settings.llm_max_attempts):
            try:
                plans: list[RelationshipPlan] = []
                for block in self._build_blocks(snapshot.nodes):
                    output = client.generate_structured(
                        operation="knowledge_relationships",
                        messages=relationship_prompt.messages(self._render_block(block), feedback),
                        schema=KnowledgeRelationshipOutput,
                    )
                    data = output.data
                    if not isinstance(data, KnowledgeRelationshipOutput):
                        raise KnowledgeRelationshipError(
                            "KNOWLEDGE_RELATIONSHIP_INVALID_OUTPUT",
                            "AI returned an invalid relationship structure.",
                        )
                    plans.extend(self._plans_from_output(data, block))
                self._validate_plans(snapshot.nodes, plans)
                return plans
            except KnowledgeRelationshipError as error:
                last_error = error
                if attempt + 1 >= self.settings.llm_max_attempts:
                    break
                feedback = error.message
        if last_error is None:
            raise KnowledgeRelationshipError(
                "KNOWLEDGE_RELATIONSHIP_INVALID_OUTPUT",
                "AI did not return a valid relationship model.",
            )
        raise last_error

    def _build_blocks(
        self,
        nodes: list[RelationshipSnapshotNode],
    ) -> list[list[RelationshipSnapshotNode]]:
        size = self.settings.knowledge_relationship_block_size
        ordered = sorted(nodes, key=lambda item: item.node.id)
        return [ordered[index : index + size] for index in range(0, len(ordered), size)]

    @staticmethod
    def _render_block(block: list[RelationshipSnapshotNode]) -> str:
        payload: list[dict[str, object]] = []
        for item in block:
            payload.append(
                {
                    "node_id": item.node.id,
                    "name": item.node.name,
                    "description": item.node.description[:500],
                    "importance": item.node.importance.value,
                    "difficulty": item.node.difficulty.value,
                    "source_evidence": [
                        {
                            "material_id": source.material_id,
                            "source_reference": source.source_reference,
                            "excerpt": (source.excerpt or "")[:180],
                        }
                        for source in item.sources[:3]
                    ],
                }
            )
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    def _plans_from_output(
        self,
        data: KnowledgeRelationshipOutput,
        block: list[RelationshipSnapshotNode],
    ) -> list[RelationshipPlan]:
        nodes_by_id = {item.node.id: item for item in block}
        plans: list[RelationshipPlan] = []
        for relation_type, drafts in (
            (KnowledgeRelationType.CONTAINS, data.contains_edges),
            (KnowledgeRelationType.PREREQUISITE, data.prerequisite_edges),
        ):
            for draft in drafts:
                plans.append(self._plan_from_draft(draft, relation_type, nodes_by_id))
        return plans

    @staticmethod
    def _plan_from_draft(
        draft: KnowledgeRelationshipEdgeDraft,
        relation_type: KnowledgeRelationType,
        nodes_by_id: dict[int, RelationshipSnapshotNode],
    ) -> RelationshipPlan:
        if draft.source_node_id not in nodes_by_id or draft.target_node_id not in nodes_by_id:
            raise KnowledgeRelationshipError(
                "KNOWLEDGE_RELATIONSHIP_INVALID_OUTPUT",
                "AI referenced a node outside the supplied canonical-node block.",
                rejected_edge_count=1,
            )
        supported_sources = {
            (source.material_id, source.source_reference): source
            for item in (nodes_by_id[draft.source_node_id], nodes_by_id[draft.target_node_id])
            for source in item.sources
        }
        evidence: list[RelationshipSource] = []
        for citation in draft.evidence:
            if citation.material_id is None or citation.source_reference is None:
                raise KnowledgeRelationshipError(
                    "KNOWLEDGE_RELATIONSHIP_INVALID_OUTPUT",
                    "AI returned incomplete material evidence.",
                    rejected_edge_count=1,
                )
            source = supported_sources.get((citation.material_id, citation.source_reference))
            if source is None:
                raise KnowledgeRelationshipError(
                    "KNOWLEDGE_RELATIONSHIP_INVALID_OUTPUT",
                    "AI cited material evidence that is not attached to either relationship endpoint.",
                    rejected_edge_count=1,
                )
            if source not in evidence:
                evidence.append(source)
        return RelationshipPlan(
            source_node_id=draft.source_node_id,
            target_node_id=draft.target_node_id,
            relation_type=relation_type,
            reason=draft.reason,
            evidence=evidence,
        )

    @staticmethod
    def _validate_plans(
        nodes: list[RelationshipSnapshotNode],
        plans: list[RelationshipPlan],
    ) -> None:
        try:
            validate_relationship_edges(
                node_ids={item.node.id for item in nodes},
                edges=[plan.as_spec() for plan in plans],
            )
        except KnowledgeRelationshipValidationError as error:
            raise KnowledgeRelationshipError(
                "KNOWLEDGE_RELATIONSHIP_INVALID_OUTPUT",
                error.args[0],
                rejected_edge_count=max(1, len(plans)),
            ) from error

    def _validate_with_manual_edges(
        self,
        snapshot: KnowledgeRelationshipSnapshot,
        plans: list[RelationshipPlan],
    ) -> None:
        manual_specs = [
            RelationshipEdgeSpec(edge.source_node_id, edge.target_node_id, edge.relation_type)
            for edge in self.edge_repository.list_manual_by_course(snapshot.course_id)
        ]
        try:
            validate_relationship_edges(
                node_ids={item.node.id for item in snapshot.nodes},
                edges=[*manual_specs, *(plan.as_spec() for plan in plans)],
            )
        except KnowledgeRelationshipValidationError as error:
            raise KnowledgeRelationshipError(
                "KNOWLEDGE_RELATIONSHIP_INVALID_OUTPUT",
                f"Relationship model conflicts with existing manual edges: {error}",
                rejected_edge_count=max(1, len(plans)),
            ) from error

    def _persist_plans(
        self,
        run: KnowledgeRelationshipRun,
        plans: list[RelationshipPlan],
    ) -> list[KnowledgeEdge]:
        edges: list[KnowledgeEdge] = []
        for plan in plans:
            edge = self.edge_repository.create(
                KnowledgeEdge(
                    course_id=run.course_id,
                    source_node_id=plan.source_node_id,
                    target_node_id=plan.target_node_id,
                    relation_type=plan.relation_type,
                    relationship_run_id=run.id,
                )
            )
            self.evidence_repository.create(
                KnowledgeEdgeEvidence(
                    knowledge_edge_id=edge.id,
                    course_id=run.course_id,
                    material_id=None,
                    source_reference=None,
                    excerpt=None,
                    evidence_type=KnowledgeEdgeEvidenceType.MODEL_INFERENCE,
                    reason=plan.reason,
                )
            )
            for source in plan.evidence:
                self.evidence_repository.create(
                    KnowledgeEdgeEvidence(
                        knowledge_edge_id=edge.id,
                        course_id=run.course_id,
                        material_id=source.material_id,
                        source_reference=source.source_reference,
                        excerpt=(source.excerpt or "")[:1000] or None,
                        evidence_type=KnowledgeEdgeEvidenceType.MATERIAL,
                        reason=plan.reason,
                    )
                )
            edges.append(edge)
        return edges

    def _evidence_by_edge_id(
        self,
        edges: list[KnowledgeEdge],
    ) -> dict[int, list[KnowledgeEdgeEvidence]]:
        grouped: dict[int, list[KnowledgeEdgeEvidence]] = defaultdict(list)
        for evidence in self.evidence_repository.list_for_edges([edge.id for edge in edges]):
            grouped[evidence.knowledge_edge_id].append(evidence)
        return dict(grouped)

    def _mark_failed(self, run_id: int, code: str, message: str, rejected_edge_count: int) -> None:
        with self.session.begin():
            run = self.run_repository.get_by_id(run_id)
            if run is None:
                return
            run.status = KnowledgeRelationshipStatus.FAILED
            run.contains_edge_count = 0
            run.prerequisite_edge_count = 0
            run.rejected_edge_count = max(0, rejected_edge_count)
            run.error_code = code[:64]
            run.error_message = message[:255]
            run.is_current = False
            run.completed_at = datetime.now(timezone.utc)
            self.run_repository.save(run)

    @staticmethod
    def _map_ai_error(error: AIServiceError) -> KnowledgeRelationshipError:
        if error.code == "AI_INVALID_OUTPUT":
            return KnowledgeRelationshipError(
                "KNOWLEDGE_RELATIONSHIP_INVALID_OUTPUT",
                "AI returned output that did not match the required relationship schema.",
            )
        return KnowledgeRelationshipError(
            "KNOWLEDGE_RELATIONSHIP_FAILED",
            "The AI provider could not complete knowledge relationship generation.",
        )

    @staticmethod
    def _client_identity(client: LLMClient) -> tuple[str, str]:
        provider = str(getattr(client, "provider", "")).strip()
        model = str(getattr(client, "model", "")).strip()
        if not provider or not model:
            raise KnowledgeRelationshipError(
                "KNOWLEDGE_RELATIONSHIP_FAILED",
                "The configured AI provider did not expose traceable provider and model identifiers.",
            )
        return provider[:80], model[:160]

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


def get_knowledge_relationship_service(
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> KnowledgeRelationshipService:
    return KnowledgeRelationshipService(
        session=session,
        course_repository=CourseRepository(session),
        canonicalization_run_repository=KnowledgeCanonicalizationRunRepository(session),
        node_repository=KnowledgeNodeRepository(session),
        source_repository=KnowledgeSourceRepository(session),
        material_repository=MaterialRepository(session),
        content_repository=MaterialContentRepository(session),
        run_repository=KnowledgeRelationshipRunRepository(session),
        edge_repository=KnowledgeEdgeRepository(session),
        evidence_repository=KnowledgeEdgeEvidenceRepository(session),
        user_repository=UserRepository(session),
        settings=settings,
    )


__all__ = [
    "KnowledgeRelationshipError",
    "KnowledgeRelationshipResult",
    "KnowledgeRelationshipService",
    "get_knowledge_relationship_service",
]
