from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from collections.abc import Callable, Generator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.ai import GeneratedStructuredOutput, LLMClient
from backend.app.api.knowledge import (
    generate_course_knowledge_relationships,
    get_course_knowledge_model,
    get_course_knowledge_relationships,
)
from backend.app.core.settings import Settings
from backend.app.db.models import (
    Course,
    KnowledgeCanonicalizationRun,
    KnowledgeEdge,
    KnowledgeEdgeEvidence,
    KnowledgeNode,
    KnowledgeRelationshipRun,
    KnowledgeSource,
    Material,
    MaterialContent,
    User,
)
from backend.app.models import (
    KnowledgeCanonicalizationStatus,
    KnowledgeDifficulty,
    KnowledgeEdgeEvidenceType,
    KnowledgeImportance,
    KnowledgeRelationshipStatus,
    KnowledgeRelationType,
    normalize_knowledge_name,
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
from backend.app.schemas.knowledge import KnowledgeModelResponse, KnowledgeRelationshipsResponse
from backend.app.services.knowledge_model_service import KnowledgeModelService
from backend.app.services.knowledge_relationship_service import (
    KnowledgeRelationshipError,
    KnowledgeRelationshipService,
)
from backend.app.services.knowledge_relationship_validation import (
    KnowledgeRelationshipValidationError,
    RelationshipEdgeSpec,
    validate_relationship_edges,
)


def migrate_database(tmp_path: Path, revision: str = "head", *, name: str = "m3d.sqlite3") -> str:
    database_url = f"sqlite+pysqlite:///{tmp_path / name}"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", revision],
        env=environment,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return database_url


def make_engine(database_url: str):
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def make_settings(database_url: str, tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "app_env": "test",
        "database_url": database_url,
        "upload_root": tmp_path / "uploads",
        "legacy_bootstrap_user": "relationship-owner@example.test",
        "legacy_bootstrap_user_display_name": "Relationship Owner",
        "llm_mode": "mock",
        "llm_max_attempts": 2,
        "knowledge_relationship_block_size": 12,
    }
    values.update(overrides)
    return Settings(**values)


@dataclass(frozen=True)
class Seed:
    course_id: int
    private_course_id: int
    material_id: int
    reference: str
    node_ids: list[int]


class ScriptedRelationshipClient(LLMClient):
    provider = "scripted"
    model = "m3d-test-model"

    def __init__(self, responses: list[dict[str, object] | Exception], session: Session | None = None) -> None:
        self.responses = responses
        self.session = session
        self.calls = 0
        self.transaction_states: list[bool] = []
        self.messages: list[list[dict[str, str]]] = []

    def generate_structured(self, *, operation, messages, schema):
        assert operation == "knowledge_relationships"
        self.messages.append(messages)
        if self.session is not None:
            self.transaction_states.append(self.session.in_transaction())
        index = min(self.calls, len(self.responses) - 1)
        response = self.responses[index]
        self.calls += 1
        if isinstance(response, Exception):
            raise response
        return GeneratedStructuredOutput(schema.model_validate(response), self.provider, self.model)


def seed_course(session: Session, settings: Settings, names: list[str]) -> Seed:
    with session.begin():
        owner = User(
            email=settings.legacy_bootstrap_user,
            display_name=settings.legacy_bootstrap_user_display_name,
            is_active=True,
        )
        other = User(email="other@example.test", display_name="Other", is_active=True)
        session.add_all([owner, other])
        session.flush()
        course = Course(owner_id=owner.id, name="Computer Architecture", description="")
        private = Course(owner_id=other.id, name="Private course", description="")
        session.add_all([course, private])
        session.flush()
        text = "\n".join(names) or "No canonical nodes"
        reference = "TXT segment 1"
        material = Material(
            course_id=course.id,
            title="Architecture notes",
            material_type="txt",
            summary="",
            storage_status="NOT_STORED",
            extraction_status="SUCCESS",
            text_extracted=True,
            text_length=len(text),
            text_preview=text,
        )
        session.add(material)
        session.flush()
        content_hash = hashlib.sha256(text.encode()).hexdigest()
        session.add(
            MaterialContent(
                material_id=material.id,
                plain_text=text,
                segments=[{"text": text, "source_reference": reference}],
                content_hash=content_hash,
                parser_name="test-parser",
                parser_version="1",
                page_count=1,
            )
        )
        run = KnowledgeCanonicalizationRun(
            course_id=course.id,
            candidate_snapshot_hash=content_hash,
            status=KnowledgeCanonicalizationStatus.SUCCESS,
            provider="seed",
            model="seed",
            prompt_version="knowledge_canonicalization_v1",
            configuration_version="canonicalization_config_v1",
            candidate_count=len(names),
            canonical_node_count=len(names),
            merged_candidate_count=0,
            unresolved_count=0,
            is_current=True,
        )
        session.add(run)
        session.flush()
        node_ids: list[int] = []
        for name in names:
            node = KnowledgeNode(
                course_id=course.id,
                name=name,
                normalized_name=normalize_knowledge_name(name),
                description=f"{name} is a canonical course concept.",
                importance=KnowledgeImportance.MEDIUM,
                difficulty=KnowledgeDifficulty.INTERMEDIATE,
                is_active=True,
                managed_by_canonicalization=True,
            )
            session.add(node)
            session.flush()
            session.add(
                KnowledgeSource(
                    knowledge_node_id=node.id,
                    material_id=material.id,
                    source_reference=reference,
                    excerpt=f"Evidence for {name}.",
                )
            )
            node_ids.append(node.id)
        return Seed(course.id, private.id, material.id, reference, node_ids)


def make_relationship_service(
    session: Session,
    settings: Settings,
    client_or_factory: LLMClient | Callable[[Settings], LLMClient],
) -> KnowledgeRelationshipService:
    factory = client_or_factory if callable(client_or_factory) else lambda _settings: client_or_factory
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
        llm_client_factory=factory,
    )


def make_model_service(session: Session, settings: Settings) -> KnowledgeModelService:
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


@pytest.fixture
def database(tmp_path: Path) -> Generator[tuple[sessionmaker[Session], Settings], None, None]:
    database_url = migrate_database(tmp_path)
    engine = make_engine(database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory, make_settings(database_url, tmp_path)
    engine.dispose()


def test_fresh_and_m3c_upgrade_create_relationship_schema(tmp_path: Path) -> None:
    database_url = migrate_database(tmp_path, name="fresh.sqlite3")
    engine = make_engine(database_url)
    inspector = inspect(engine)
    assert {"knowledge_relationship_runs", "knowledge_edge_evidences"}.issubset(inspector.get_table_names())
    run_checks = {item["name"] for item in inspector.get_check_constraints("knowledge_relationship_runs")}
    edge_columns = {item["name"] for item in inspector.get_columns("knowledge_edges")}
    evidence_fks = {item["name"] for item in inspector.get_foreign_keys("knowledge_edge_evidences")}
    assert "ck_knowledge_relationship_runs_contains_count" in run_checks
    assert "relationship_run_id" in edge_columns
    assert "fk_knowledge_edge_evidences_edge_course" in evidence_fks
    engine.dispose()

    database_url = migrate_database(tmp_path, "0005_m3c_canonicalization", name="upgrade.sqlite3")
    engine = make_engine(database_url)
    with sessionmaker(bind=engine)() as session, session.begin():
        owner = User(email="upgrade@example.test", display_name="Upgrade", is_active=True)
        session.add(owner)
        session.flush()
        course = Course(owner_id=owner.id, name="M3-C course", description="")
        session.add(course)
        session.flush()
        course_id = course.id
    engine.dispose()
    migrate_database(tmp_path, name="upgrade.sqlite3")
    engine = make_engine(database_url)
    with sessionmaker(bind=engine)() as session:
        assert session.get(Course, course_id).name == "M3-C course"
        assert inspect(engine).has_table("knowledge_relationship_runs")
    engine.dispose()


def test_contains_forest_and_prerequisite_dag_constraints_are_independent() -> None:
    nodes = {1, 2, 3, 4}
    validate_relationship_edges(
        node_ids=nodes,
        edges=[
            RelationshipEdgeSpec(1, 2, KnowledgeRelationType.CONTAINS),
            RelationshipEdgeSpec(1, 3, KnowledgeRelationType.CONTAINS),
            RelationshipEdgeSpec(2, 4, KnowledgeRelationType.PREREQUISITE),
        ],
    )
    with pytest.raises(KnowledgeRelationshipValidationError, match="at most one"):
        validate_relationship_edges(
            node_ids=nodes,
            edges=[
                RelationshipEdgeSpec(1, 3, KnowledgeRelationType.CONTAINS),
                RelationshipEdgeSpec(2, 3, KnowledgeRelationType.CONTAINS),
            ],
        )
    with pytest.raises(KnowledgeRelationshipValidationError, match="forest"):
        validate_relationship_edges(
            node_ids=nodes,
            edges=[
                RelationshipEdgeSpec(1, 2, KnowledgeRelationType.CONTAINS),
                RelationshipEdgeSpec(2, 1, KnowledgeRelationType.CONTAINS),
            ],
        )
    with pytest.raises(KnowledgeRelationshipValidationError, match="DAG"):
        validate_relationship_edges(
            node_ids=nodes,
            edges=[
                RelationshipEdgeSpec(1, 2, KnowledgeRelationType.PREREQUISITE),
                RelationshipEdgeSpec(2, 1, KnowledgeRelationType.PREREQUISITE),
            ],
        )
    with pytest.raises(KnowledgeRelationshipValidationError, match="itself"):
        validate_relationship_edges(
            node_ids=nodes,
            edges=[RelationshipEdgeSpec(1, 1, KnowledgeRelationType.PREREQUISITE)],
        )


def test_generation_persists_explicit_relations_and_traceable_evidence(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_course(session, settings, ["Cache", "Address Mapping", "Direct-Mapped Cache"])
        cache, mapping, direct = seed.node_ids
        client = ScriptedRelationshipClient(
            [
                {
                    "contains_edges": [
                        {
                            "source_node_id": cache,
                            "target_node_id": direct,
                            "reason": "Direct-mapped cache is a cache organization.",
                            "evidence": [{"material_id": seed.material_id, "source_reference": seed.reference}],
                        }
                    ],
                    "prerequisite_edges": [
                        {
                            "source_node_id": mapping,
                            "target_node_id": direct,
                            "reason": "Address mapping is needed to understand direct mapping.",
                            "evidence": [],
                        }
                    ],
                }
            ],
            session,
        )
        result = make_relationship_service(session, settings, client).generate_relationships(seed.course_id)
        assert result.run.status == KnowledgeRelationshipStatus.SUCCESS
        assert result.run.contains_edge_count == 1
        assert result.run.prerequisite_edge_count == 1
        assert client.transaction_states == [False]
        assert {(edge.source_node_id, edge.target_node_id, edge.relation_type) for edge in result.edges} == {
            (cache, direct, KnowledgeRelationType.CONTAINS),
            (mapping, direct, KnowledgeRelationType.PREREQUISITE),
        }
        evidence = [item for values in result.evidence_by_edge_id.values() for item in values]
        assert KnowledgeEdgeEvidenceType.MODEL_INFERENCE in {item.evidence_type for item in evidence}
        assert any(
            item.evidence_type == KnowledgeEdgeEvidenceType.MATERIAL
            and item.material_id == seed.material_id
            and item.source_reference == seed.reference
            for item in evidence
        )
        assert all(
            not (
                edge.source_node_id == cache
                and edge.target_node_id == direct
                and edge.relation_type == KnowledgeRelationType.PREREQUISITE
            )
            for edge in result.edges
        )


def test_invalid_unknown_node_retries_without_an_open_write_transaction(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_course(session, settings, ["Cache", "Cache Miss"])
        first, second = seed.node_ids
        client = ScriptedRelationshipClient(
            [
                {
                    "contains_edges": [
                        {
                            "source_node_id": first,
                            "target_node_id": 999_999,
                            "reason": "invalid",
                            "evidence": [],
                        }
                    ],
                    "prerequisite_edges": [],
                },
                {
                    "contains_edges": [
                        {
                            "source_node_id": first,
                            "target_node_id": second,
                            "reason": "A cache miss is a cache topic.",
                            "evidence": [],
                        }
                    ],
                    "prerequisite_edges": [],
                },
            ],
            session,
        )
        result = make_relationship_service(session, settings, client).generate_relationships(seed.course_id)
        assert client.calls == 2
        assert client.transaction_states == [False, False]
        assert result.run.status == KnowledgeRelationshipStatus.SUCCESS
        assert "Correct the previous invalid output" in client.messages[1][-1]["content"]


def test_invalid_fabricated_evidence_preserves_previous_current_model(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_course(session, settings, ["Cache", "Cache Miss"])
        first, second = seed.node_ids
        good_client = ScriptedRelationshipClient(
            [
                {
                    "contains_edges": [
                        {
                            "source_node_id": first,
                            "target_node_id": second,
                            "reason": "A cache miss is part of cache behavior.",
                            "evidence": [],
                        }
                    ],
                    "prerequisite_edges": [],
                }
            ]
        )
        service = make_relationship_service(session, settings, good_client)
        good = service.generate_relationships(seed.course_id)
        bad_client = ScriptedRelationshipClient(
            [
                {
                    "contains_edges": [
                        {
                            "source_node_id": first,
                            "target_node_id": second,
                            "reason": "invalid citation",
                            "evidence": [{"material_id": seed.material_id, "source_reference": "PDF page 999"}],
                        }
                    ],
                    "prerequisite_edges": [],
                }
            ]
        )
        with pytest.raises(KnowledgeRelationshipError) as error:
            make_relationship_service(session, settings, bad_client).generate_relationships(
                seed.course_id,
                regenerate=True,
            )
        assert error.value.code == "KNOWLEDGE_RELATIONSHIP_INVALID_OUTPUT"
        current = KnowledgeRelationshipRunRepository(session).get_current_for_course(seed.course_id)
        assert current is not None and current.id == good.run.id
        assert KnowledgeEdgeRepository(session).list_for_run(good.run.id)
        failed = KnowledgeRelationshipRunRepository(session).get_latest_for_course(seed.course_id)
        assert failed is not None and failed.status == KnowledgeRelationshipStatus.FAILED
        assert failed.rejected_edge_count == 1


def test_idempotency_and_snapshot_change_control_calls(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_course(session, settings, ["Cache", "Cache Miss"])
        first, second = seed.node_ids
        client = ScriptedRelationshipClient(
            [
                {
                    "contains_edges": [
                        {
                            "source_node_id": first,
                            "target_node_id": second,
                            "reason": "direct hierarchy",
                            "evidence": [],
                        }
                    ],
                    "prerequisite_edges": [],
                },
                {"contains_edges": [], "prerequisite_edges": []},
            ]
        )
        service = make_relationship_service(session, settings, client)
        first_result = service.generate_relationships(seed.course_id)
        repeated = service.generate_relationships(seed.course_id)
        assert repeated.reused is True
        assert repeated.run.id == first_result.run.id
        assert client.calls == 1
        with session.begin():
            node = session.get(KnowledgeNode, first)
            assert node is not None
            node.description = "Updated canonical concept description."
        changed = service.generate_relationships(seed.course_id)
        assert changed.reused is False
        assert changed.run.id != first_result.run.id
        assert client.calls == 2


def test_minimum_node_case_needs_no_llm_and_requires_current_canonicalization(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_course(session, settings, ["Cache"])

        def forbidden_factory(_settings: Settings) -> LLMClient:
            raise AssertionError("One canonical node must not initialize an LLM client.")

        result = make_relationship_service(session, settings, forbidden_factory).generate_relationships(seed.course_id)
        assert result.run.status == KnowledgeRelationshipStatus.SUCCESS
        assert result.edges == []
        with session.begin():
            current = KnowledgeCanonicalizationRunRepository(session).get_current_for_course(seed.course_id)
            assert current is not None
            current.is_current = False
        with pytest.raises(KnowledgeRelationshipError) as error:
            make_relationship_service(session, settings, forbidden_factory).generate_relationships(seed.course_id)
        assert error.value.code == "KNOWLEDGE_RELATIONSHIP_NOT_READY"


def test_only_active_canonical_nodes_are_input_and_related_nodes_can_have_no_edge(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_course(session, settings, ["Cache Hit", "Cache Miss"])
        with session.begin():
            session.add(
                KnowledgeNode(
                    course_id=seed.course_id,
                    name="Historical Cache Topic",
                    normalized_name="historical cache topic",
                    description="Inactive historical canonical node.",
                    importance=KnowledgeImportance.LOW,
                    difficulty=KnowledgeDifficulty.BASIC,
                    is_active=False,
                    managed_by_canonicalization=True,
                )
            )
        client = ScriptedRelationshipClient([{"contains_edges": [], "prerequisite_edges": []}])
        service = make_relationship_service(session, settings, client)
        result = service.generate_relationships(seed.course_id)
        assert result.run.node_count == 2
        assert result.edges == []
        assert client.calls == 1


def test_course_isolation_and_database_cascades_cover_relationship_records(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_course(session, settings, ["Cache", "Cache Miss"])
        first, second = seed.node_ids
        relationship_run = KnowledgeRelationshipRun(
            course_id=seed.course_id,
            knowledge_snapshot_hash="a" * 64,
            status=KnowledgeRelationshipStatus.SUCCESS,
            provider="test",
            model="test",
            prompt_version="knowledge_relationships_v1",
            node_count=2,
            contains_edge_count=1,
            prerequisite_edge_count=0,
            rejected_edge_count=0,
            is_current=True,
        )
        relationship_run_id: int
        with session.begin():
            session.add(relationship_run)
            session.flush()
            relationship_run_id = relationship_run.id
            edge = KnowledgeEdge(
                course_id=seed.course_id,
                source_node_id=first,
                target_node_id=second,
                relation_type=KnowledgeRelationType.CONTAINS,
                relationship_run_id=relationship_run.id,
            )
            session.add(edge)
            session.flush()
            edge_id = edge.id
            session.add(
                KnowledgeEdgeEvidence(
                    knowledge_edge_id=edge.id,
                    course_id=seed.course_id,
                    material_id=seed.material_id,
                    source_reference=seed.reference,
                    excerpt="Evidence",
                    evidence_type=KnowledgeEdgeEvidenceType.MATERIAL,
                    reason="Evidence",
                )
            )
            private_node = KnowledgeNode(
                course_id=seed.private_course_id,
                name="Private node",
                normalized_name="private node",
                description="Private concept.",
                importance=KnowledgeImportance.LOW,
                difficulty=KnowledgeDifficulty.BASIC,
            )
            session.add(private_node)
            session.flush()
            private_node_id = private_node.id
        with pytest.raises(IntegrityError):
            with session.begin():
                session.add(
                    KnowledgeEdge(
                        course_id=seed.course_id,
                        source_node_id=first,
                        target_node_id=private_node_id,
                        relation_type=KnowledgeRelationType.PREREQUISITE,
                    )
                )
        session.rollback()
        with pytest.raises(IntegrityError):
            with session.begin():
                session.add(
                    KnowledgeEdge(
                        course_id=seed.course_id,
                        source_node_id=first,
                        target_node_id=first,
                        relation_type=KnowledgeRelationType.CONTAINS,
                    )
                )
        session.rollback()
        with session.begin():
            session.delete(session.get(KnowledgeNode, first))
        assert session.get(KnowledgeEdge, edge_id) is None
        assert (
            session.scalar(select(KnowledgeEdgeEvidence).where(KnowledgeEdgeEvidence.knowledge_edge_id == edge_id))
            is None
        )
        session.commit()
        with session.begin():
            session.delete(session.get(Material, seed.material_id))
        assert session.scalar(select(KnowledgeSource).where(KnowledgeSource.material_id == seed.material_id)) is None
        assert (
            session.scalar(select(KnowledgeEdgeEvidence).where(KnowledgeEdgeEvidence.material_id == seed.material_id))
            is None
        )
        session.commit()
        with session.begin():
            session.delete(session.get(Course, seed.course_id))
        assert session.get(KnowledgeRelationshipRun, relationship_run_id) is None
        assert session.scalar(select(KnowledgeEdge).where(KnowledgeEdge.course_id == seed.course_id)) is None


def test_read_api_returns_current_relations_only_and_ownership_is_enforced(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_course(session, settings, ["Cache", "Cache Miss"])
        first, second = seed.node_ids
        client = ScriptedRelationshipClient(
            [
                {
                    "contains_edges": [
                        {
                            "source_node_id": first,
                            "target_node_id": second,
                            "reason": "direct hierarchy",
                            "evidence": [],
                        }
                    ],
                    "prerequisite_edges": [],
                }
            ]
        )
        service = make_relationship_service(session, settings, client)
        generated = generate_course_knowledge_relationships(seed.course_id, service=service)
        response = KnowledgeRelationshipsResponse.model_validate(generated)
        assert len(response.contains_edges) == 1
        assert response.prerequisite_edges == []
        fetched = get_course_knowledge_relationships(seed.course_id, service=service)
        assert KnowledgeRelationshipsResponse.model_validate(fetched).run.id == response.run.id
        model_response = KnowledgeModelResponse.model_validate(
            get_course_knowledge_model(seed.course_id, service=make_model_service(session, settings))
        )
        assert {(edge.source_node_id, edge.target_node_id) for edge in model_response.edges} == {(first, second)}
        with pytest.raises(HTTPException) as error:
            generate_course_knowledge_relationships(seed.private_course_id, service=service)
        assert error.value.status_code == 404
