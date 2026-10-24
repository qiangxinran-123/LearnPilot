from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from backend.app.api.knowledge import build_course_knowledge_model
from backend.app.core.errors import ApiError
from backend.app.core.settings import Settings
from backend.app.db.models import (
    Course,
    KnowledgeCanonicalizationRun,
    KnowledgeNode,
    KnowledgeSource,
    Material,
    MaterialContent,
    User,
)
from backend.app.models import (
    KnowledgeCanonicalizationStatus,
    KnowledgeDifficulty,
    KnowledgeImportance,
    KnowledgeRelationType,
)
from backend.app.repositories import (
    CourseRepository,
    KnowledgeCanonicalizationRunRepository,
    KnowledgeNodeRepository,
    MaterialContentRepository,
    MaterialRepository,
    UserRepository,
)
from backend.app.services.course_knowledge_build_service import (
    CourseKnowledgeBuildError,
    CourseKnowledgeBuildService,
)
from backend.app.services.knowledge_relationship_service import KnowledgeRelationshipError


def migrate_database(tmp_path: Path) -> str:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'm3e-build.sqlite3'}"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
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


def make_settings(database_url: str, tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=database_url,
        upload_root=tmp_path / "uploads",
        legacy_bootstrap_user="build-owner@example.test",
        legacy_bootstrap_user_display_name="Build Owner",
        llm_mode="mock",
    )


@pytest.fixture
def database(tmp_path: Path):
    database_url = migrate_database(tmp_path)
    engine = make_engine(database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory, make_settings(database_url, tmp_path)
    engine.dispose()


@dataclass(frozen=True)
class Seed:
    course_id: int
    private_course_id: int
    ready_material_id: int


def seed_course(session: Session, settings: Settings, *, include_ready_material: bool = True) -> Seed:
    with session.begin():
        owner = User(
            email=settings.legacy_bootstrap_user,
            display_name=settings.legacy_bootstrap_user_display_name,
            is_active=True,
        )
        other = User(email="other@example.test", display_name="Other", is_active=True)
        session.add_all([owner, other])
        session.flush()
        course = Course(owner_id=owner.id, name="Algorithms", description="")
        private_course = Course(owner_id=other.id, name="Private", description="")
        session.add_all([course, private_course])
        session.flush()

        text = "Graph traversal and shortest paths"
        material = Material(
            course_id=course.id,
            title="Lecture notes",
            material_type="txt",
            summary="",
            storage_status="NOT_STORED",
            extraction_status="SUCCESS" if include_ready_material else "PENDING",
            text_extracted=include_ready_material,
            text_length=len(text) if include_ready_material else 0,
            text_preview=text if include_ready_material else "",
        )
        session.add(material)
        session.flush()
        if include_ready_material:
            session.add(
                MaterialContent(
                    material_id=material.id,
                    plain_text=text,
                    segments=[{"text": text, "source_reference": "TXT segment 1"}],
                    content_hash=hashlib.sha256(text.encode()).hexdigest(),
                    parser_name="test-parser",
                    parser_version="1",
                    page_count=1,
                )
            )
        return Seed(course.id, private_course.id, material.id)


class RecordingExtractionService:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int, bool]] = []

    def extract(self, course_id: int, material_id: int, *, regenerate: bool):
        self.calls.append((course_id, material_id, regenerate))
        return SimpleNamespace(reused=True)


class RecordingCanonicalizationService:
    def __init__(self, nodes: list[object], *, reused: bool = True) -> None:
        self.nodes = nodes
        self.reused = reused
        self.calls: list[tuple[int, bool]] = []

    def canonicalize(self, course_id: int, *, regenerate: bool):
        self.calls.append((course_id, regenerate))
        return SimpleNamespace(nodes=self.nodes, reused=self.reused)


class RecordingRelationshipService:
    def __init__(self, edges: list[object], *, reused: bool = True) -> None:
        self.edges = edges
        self.reused = reused
        self.calls: list[tuple[int, bool]] = []

    def generate_relationships(self, course_id: int, *, regenerate: bool):
        self.calls.append((course_id, regenerate))
        return SimpleNamespace(edges=self.edges, reused=self.reused)


def make_service(
    session: Session,
    settings: Settings,
    extraction_service: object,
    canonicalization_service: object,
    relationship_service: object,
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
        extraction_service=extraction_service,  # type: ignore[arg-type]
        canonicalization_service=canonicalization_service,  # type: ignore[arg-type]
        relationship_service=relationship_service,  # type: ignore[arg-type]
    )


def test_build_reuses_stages_for_each_ready_material_and_returns_typed_payload(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_course(session, settings)
        extraction = RecordingExtractionService()
        canonicalization = RecordingCanonicalizationService([SimpleNamespace(id=1), SimpleNamespace(id=2)])
        relationship = RecordingRelationshipService(
            [
                SimpleNamespace(relation_type=KnowledgeRelationType.CONTAINS),
                SimpleNamespace(relation_type=KnowledgeRelationType.PREREQUISITE),
            ]
        )
        service = make_service(session, settings, extraction, canonicalization, relationship)

        payload = build_course_knowledge_model(seed.course_id, service)

        assert payload == {
            "course_id": seed.course_id,
            "material_count": 1,
            "node_count": 2,
            "contains_edge_count": 1,
            "prerequisite_edge_count": 1,
            "added_node_count": 2,
            "reused_node_count": 0,
            "reused": True,
        }
        assert extraction.calls == [(seed.course_id, seed.ready_material_id, False)]
        assert canonicalization.calls == [(seed.course_id, False)]
        assert relationship.calls == [(seed.course_id, False)]


def test_build_requires_an_owned_course_with_parsed_content(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_course(session, settings, include_ready_material=False)
        service = make_service(
            session,
            settings,
            RecordingExtractionService(),
            RecordingCanonicalizationService([]),
            RecordingRelationshipService([]),
        )

        with pytest.raises(CourseKnowledgeBuildError) as error:
            service.build(seed.course_id)
        assert error.value.code == "KNOWLEDGE_MODEL_BUILD_NOT_READY"

        with pytest.raises(ApiError) as api_error:
            build_course_knowledge_model(seed.course_id, service)
        assert api_error.value.status_code == 409
        assert api_error.value.code == "KNOWLEDGE_MODEL_BUILD_NOT_READY"


def test_build_hides_non_owned_course_as_not_found(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_course(session, settings)
        service = make_service(
            session,
            settings,
            RecordingExtractionService(),
            RecordingCanonicalizationService([]),
            RecordingRelationshipService([]),
        )

        with pytest.raises(HTTPException) as error:
            build_course_knowledge_model(seed.private_course_id, service)
        assert getattr(error.value, "status_code", None) == 404


def test_relationship_failure_restores_prior_active_canonical_model(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_course(session, settings)
        with session.begin():
            previous_run = KnowledgeCanonicalizationRun(
                course_id=seed.course_id,
                candidate_snapshot_hash="a" * 64,
                status=KnowledgeCanonicalizationStatus.SUCCESS,
                provider="seed",
                model="seed",
                prompt_version="knowledge_canonicalization_v1",
                configuration_version="canonicalization_config_v1",
                candidate_count=1,
                canonical_node_count=1,
                merged_candidate_count=0,
                unresolved_count=0,
                is_current=True,
            )
            previous_node = KnowledgeNode(
                course_id=seed.course_id,
                name="Previous concept",
                normalized_name="previous concept",
                description="Previously verified explanation.",
                importance=KnowledgeImportance.MEDIUM,
                difficulty=KnowledgeDifficulty.INTERMEDIATE,
                is_active=True,
                managed_by_canonicalization=True,
            )
            session.add_all([previous_run, previous_node])
            session.flush()
            session.add(
                KnowledgeSource(
                    knowledge_node_id=previous_node.id,
                    material_id=seed.ready_material_id,
                    source_reference="TXT segment 1",
                    excerpt="Previously verified source.",
                )
            )
            previous_run_id = previous_run.id
            previous_node_id = previous_node.id

        class PublishingCanonicalizationService:
            def canonicalize(self, course_id: int, *, regenerate: bool):
                assert course_id == seed.course_id
                assert regenerate is False
                with session.begin():
                    current = session.get(KnowledgeCanonicalizationRun, previous_run_id)
                    assert current is not None
                    current.is_current = False
                    published_run = KnowledgeCanonicalizationRun(
                        course_id=seed.course_id,
                        candidate_snapshot_hash="b" * 64,
                        status=KnowledgeCanonicalizationStatus.SUCCESS,
                        provider="seed",
                        model="seed",
                        prompt_version="knowledge_canonicalization_v1",
                        configuration_version="canonicalization_config_v1",
                        candidate_count=1,
                        canonical_node_count=1,
                        merged_candidate_count=0,
                        unresolved_count=0,
                        is_current=True,
                    )
                    previous = session.get(KnowledgeNode, previous_node_id)
                    assert previous is not None
                    previous.is_active = False
                    previous.description = "Unpublished replacement."
                    session.query(KnowledgeSource).filter_by(knowledge_node_id=previous_node_id).delete()
                    session.add(
                        KnowledgeSource(
                            knowledge_node_id=previous_node_id,
                            material_id=seed.ready_material_id,
                            source_reference="TXT segment 1",
                            excerpt="Unpublished replacement source.",
                        )
                    )
                    published_node = KnowledgeNode(
                        course_id=seed.course_id,
                        name="New concept",
                        normalized_name="new concept",
                        description="",
                        importance=KnowledgeImportance.HIGH,
                        difficulty=KnowledgeDifficulty.ADVANCED,
                        is_active=True,
                        managed_by_canonicalization=True,
                    )
                    session.add_all([published_run, published_node])
                    session.flush()
                    return SimpleNamespace(nodes=[published_node], reused=False)

        class FailingRelationshipService:
            def generate_relationships(self, course_id: int, *, regenerate: bool):
                assert course_id == seed.course_id
                assert regenerate is False
                raise KnowledgeRelationshipError(
                    "KNOWLEDGE_RELATIONSHIP_INVALID_OUTPUT",
                    "Relationship output is invalid.",
                )

        service = make_service(
            session,
            settings,
            RecordingExtractionService(),
            PublishingCanonicalizationService(),
            FailingRelationshipService(),
        )

        with pytest.raises(CourseKnowledgeBuildError) as error:
            service.build(seed.course_id)
        assert error.value.code == "KNOWLEDGE_MODEL_BUILD_INVALID_OUTPUT"

        with session.begin():
            restored_run = session.get(KnowledgeCanonicalizationRun, previous_run_id)
            restored_node = session.get(KnowledgeNode, previous_node_id)
            new_node = session.query(KnowledgeNode).filter_by(normalized_name="new concept").one()
            assert restored_run is not None and restored_run.is_current is True
            assert restored_node is not None and restored_node.is_active is True
            assert restored_node.description == "Previously verified explanation."
            restored_sources = session.query(KnowledgeSource).filter_by(knowledge_node_id=previous_node_id).all()
            assert [(source.source_reference, source.excerpt) for source in restored_sources] == [
                ("TXT segment 1", "Previously verified source.")
            ]
            assert new_node.is_active is False
