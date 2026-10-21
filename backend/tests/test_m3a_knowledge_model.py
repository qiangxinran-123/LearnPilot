from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.api.knowledge import get_course_knowledge_model, get_knowledge_node_detail
from backend.app.core.errors import ApiError
from backend.app.core.settings import Settings
from backend.app.db.models import (
    Course,
    KnowledgeEdge,
    KnowledgeNode,
    KnowledgeSource,
    Material,
    MaterialContent,
    User,
)
from backend.app.models import KnowledgeDifficulty, KnowledgeImportance, KnowledgeRelationType
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
    KnowledgeModelResponse,
    KnowledgeNodeCreate,
    KnowledgeNodeDetailResponse,
    KnowledgeNodeUpdate,
    KnowledgeSourceCreate,
)
from backend.app.services.course_service import ResourceNotFoundError
from backend.app.services.knowledge_model_service import (
    KnowledgeModelError,
    KnowledgeModelService,
    KnowledgeNodeNotFoundError,
)


def migrate_database(tmp_path: Path, revision: str = "head", *, name: str = "m3a.sqlite3") -> str:
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


def make_settings(database_url: str, tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=database_url,
        upload_root=tmp_path / "uploads",
        legacy_bootstrap_user="knowledge-owner@example.test",
        legacy_bootstrap_user_display_name="Knowledge Owner",
        llm_mode="mock",
    )


def make_service(session: Session, settings: Settings) -> KnowledgeModelService:
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


@dataclass(frozen=True)
class Seed:
    course_id: int
    second_course_id: int
    private_course_id: int
    material_id: int
    second_material_id: int
    source_reference: str


def seed_courses(session: Session, settings: Settings) -> Seed:
    source_reference = "PDF 第 12 页"
    text = "A cache stores recently used data."
    with session.begin():
        owner = User(
            email=settings.legacy_bootstrap_user,
            display_name=settings.legacy_bootstrap_user_display_name,
            is_active=True,
        )
        other_owner = User(email="private-owner@example.test", display_name="Private", is_active=True)
        session.add_all([owner, other_owner])
        session.flush()
        course = Course(owner_id=owner.id, name="Computer Systems", description="")
        second_course = Course(owner_id=owner.id, name="Algorithms", description="")
        private_course = Course(owner_id=other_owner.id, name="Private Course", description="")
        session.add_all([course, second_course, private_course])
        session.flush()
        material = Material(
            course_id=course.id,
            title="Cache notes",
            material_type="pdf",
            summary="",
            storage_status="NOT_STORED",
            extraction_status="SUCCESS",
            text_extracted=True,
            text_length=len(text),
            text_preview=text,
        )
        second_material = Material(
            course_id=second_course.id,
            title="Graph notes",
            material_type="txt",
            summary="",
            storage_status="NOT_STORED",
            extraction_status="SUCCESS",
            text_extracted=True,
            text_length=15,
            text_preview="Graph traversal",
        )
        session.add_all([material, second_material])
        session.flush()
        session.add_all(
            [
                MaterialContent(
                    material_id=material.id,
                    plain_text=text,
                    segments=[{"text": text, "source_reference": source_reference}],
                    content_hash=hashlib.sha256(text.encode()).hexdigest(),
                    parser_name="test-parser",
                    parser_version="1",
                    page_count=12,
                ),
                MaterialContent(
                    material_id=second_material.id,
                    plain_text="Graph traversal",
                    segments=[{"text": "Graph traversal", "source_reference": "TXT segment 1"}],
                    content_hash=hashlib.sha256(b"Graph traversal").hexdigest(),
                    parser_name="test-parser",
                    parser_version="1",
                    page_count=0,
                ),
            ]
        )
        session.flush()
        return Seed(
            course.id,
            second_course.id,
            private_course.id,
            material.id,
            second_material.id,
            source_reference,
        )


@pytest.fixture
def database(tmp_path: Path) -> Generator[tuple[sessionmaker[Session], Settings], None, None]:
    database_url = migrate_database(tmp_path)
    engine = make_engine(database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield factory, make_settings(database_url, tmp_path)
    engine.dispose()


def create_node(
    service: KnowledgeModelService,
    course_id: int,
    name: str,
    *,
    importance: KnowledgeImportance = KnowledgeImportance.MEDIUM,
    difficulty: KnowledgeDifficulty = KnowledgeDifficulty.INTERMEDIATE,
) -> KnowledgeNode:
    return service.create_node(
        course_id,
        KnowledgeNodeCreate(
            name=name,
            description=f"{name} description",
            importance=importance,
            difficulty=difficulty,
        ),
    )


def test_fresh_migration_creates_knowledge_schema_and_constraints(tmp_path: Path) -> None:
    database_url = migrate_database(tmp_path, name="fresh.sqlite3")
    engine = make_engine(database_url)
    inspector = inspect(engine)
    assert {"knowledge_nodes", "knowledge_edges", "knowledge_sources"}.issubset(inspector.get_table_names())
    node_checks = {item["name"] for item in inspector.get_check_constraints("knowledge_nodes")}
    edge_checks = {item["name"] for item in inspector.get_check_constraints("knowledge_edges")}
    assert {"knowledge_importance", "knowledge_difficulty"}.issubset(node_checks)
    assert "knowledge_relation_type" in edge_checks
    assert {item["name"] for item in inspector.get_check_constraints("knowledge_edges")} >= {
        "ck_knowledge_edges_no_self_edge"
    }
    edge_unique = {item["name"] for item in inspector.get_unique_constraints("knowledge_edges")}
    source_unique = {item["name"] for item in inspector.get_unique_constraints("knowledge_sources")}
    assert "uq_knowledge_edges_course_source_target_relation" in edge_unique
    assert "uq_knowledge_sources_node_material_reference" in source_unique
    # M3-D adds a generated-edge ownership foreign key while preserving the M3-A constraints.
    assert len(inspector.get_foreign_keys("knowledge_edges")) >= 3
    engine.dispose()


def test_populated_m2_database_upgrades_to_m3a_without_data_loss(tmp_path: Path) -> None:
    database_url = migrate_database(tmp_path, "0002_m2_course_material_ai", name="upgrade.sqlite3")
    engine = make_engine(database_url)
    with sessionmaker(bind=engine)() as session, session.begin():
        owner = User(email="upgrade@example.test", display_name="Upgrade", is_active=True)
        session.add(owner)
        session.flush()
        course = Course(owner_id=owner.id, name="Existing M2 Course", description="")
        session.add(course)
        session.flush()
        course_id = course.id
    assert "knowledge_nodes" not in inspect(engine).get_table_names()
    engine.dispose()

    migrate_database(tmp_path, name="upgrade.sqlite3")
    engine = make_engine(database_url)
    with sessionmaker(bind=engine)() as session:
        assert session.get(Course, course_id).name == "Existing M2 Course"
    assert {"knowledge_nodes", "knowledge_edges", "knowledge_sources"}.issubset(inspect(engine).get_table_names())
    engine.dispose()


def test_node_crud_list_and_deterministic_normalization(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_courses(session, settings)
        service = make_service(session, settings)
        first = create_node(
            service,
            seed.course_id,
            "  Cache   MEMORY  ",
            importance=KnowledgeImportance.HIGH,
            difficulty=KnowledgeDifficulty.BASIC,
        )
        second = create_node(service, seed.course_id, "Virtual Memory")

        nodes, edges = service.get_knowledge_model(seed.course_id)
        assert [node.id for node in nodes] == [first.id, second.id]
        assert edges == []
        assert first.normalized_name == "cache memory"
        assert KnowledgeNodeRepository(session).find_by_normalized_name(seed.course_id, "cache memory").id == first.id
        session.commit()

        updated = service.update_node(
            seed.course_id,
            first.id,
            KnowledgeNodeUpdate(name="Cache Hierarchy", difficulty=KnowledgeDifficulty.ADVANCED),
        )
        assert updated.name == "Cache Hierarchy"
        assert updated.normalized_name == "cache hierarchy"
        assert updated.difficulty == KnowledgeDifficulty.ADVANCED
        detail, sources, related_edges = service.get_node_detail(seed.course_id, first.id)
        assert detail.id == first.id
        assert sources == [] and related_edges == []

        service.delete_node(seed.course_id, first.id)
        with pytest.raises(KnowledgeNodeNotFoundError):
            service.get_node_detail(seed.course_id, first.id)


def test_course_ownership_and_node_read_isolation(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_courses(session, settings)
        service = make_service(session, settings)
        second_node = create_node(service, seed.second_course_id, "Sorting")
        second_node_id = second_node.id
        with pytest.raises(ResourceNotFoundError):
            service.get_knowledge_model(seed.private_course_id)
        with pytest.raises(KnowledgeNodeNotFoundError):
            service.get_node_detail(seed.course_id, second_node_id)


def test_edge_create_list_and_relation_semantics(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_courses(session, settings)
        service = make_service(session, settings)
        parent = create_node(service, seed.course_id, "Memory Hierarchy")
        child = create_node(service, seed.course_id, "Cache")
        edge = service.create_edge(
            seed.course_id,
            KnowledgeEdgeCreate(
                source_node_id=parent.id,
                target_node_id=child.id,
                relation_type=KnowledgeRelationType.CONTAINS,
            ),
        )
        assert edge.source_node_id == parent.id
        assert edge.target_node_id == child.id
        assert KnowledgeEdgeRepository(session).exists(
            seed.course_id, parent.id, child.id, KnowledgeRelationType.CONTAINS
        )
        assert KnowledgeEdgeRepository(session).list_for_node(child.id) == [edge]


def test_self_duplicate_and_cross_course_edges_are_rejected(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_courses(session, settings)
        service = make_service(session, settings)
        first = create_node(service, seed.course_id, "Cache")
        second = create_node(service, seed.course_id, "Latency")
        foreign = create_node(service, seed.second_course_id, "Graph")
        first_id, second_id, foreign_id = first.id, second.id, foreign.id

        with pytest.raises(KnowledgeModelError) as self_error:
            service.create_edge(
                seed.course_id,
                KnowledgeEdgeCreate(
                    source_node_id=first_id,
                    target_node_id=first_id,
                    relation_type=KnowledgeRelationType.PREREQUISITE,
                ),
            )
        assert self_error.value.code == "KNOWLEDGE_SELF_EDGE"

        payload = KnowledgeEdgeCreate(
            source_node_id=first_id,
            target_node_id=second_id,
            relation_type=KnowledgeRelationType.PREREQUISITE,
        )
        service.create_edge(seed.course_id, payload)
        with pytest.raises(KnowledgeModelError) as duplicate_error:
            service.create_edge(seed.course_id, payload)
        assert duplicate_error.value.code == "KNOWLEDGE_DUPLICATE_EDGE"

        with pytest.raises(KnowledgeModelError) as course_error:
            service.create_edge(
                seed.course_id,
                KnowledgeEdgeCreate(
                    source_node_id=first_id,
                    target_node_id=foreign_id,
                    relation_type=KnowledgeRelationType.CONTAINS,
                ),
            )
        assert course_error.value.code == "KNOWLEDGE_COURSE_MISMATCH"


def test_source_create_traceability_and_duplicate_handling(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_courses(session, settings)
        service = make_service(session, settings)
        node = create_node(service, seed.course_id, "Cache")
        node_id = node.id
        payload = KnowledgeSourceCreate(
            material_id=seed.material_id,
            source_reference=seed.source_reference,
            excerpt="A cache stores recently used data.",
        )
        source = service.create_source(seed.course_id, node_id, payload)
        assert source.material_id == seed.material_id
        assert source.source_reference == seed.source_reference
        assert len(source.excerpt) <= 1000
        assert KnowledgeSourceRepository(session).exists(node_id, seed.material_id, seed.source_reference)
        session.rollback()
        with pytest.raises(KnowledgeModelError) as error:
            service.create_source(seed.course_id, node_id, payload)
        assert error.value.code == "KNOWLEDGE_SOURCE_INVALID"


def test_source_rejects_cross_course_material_and_unknown_reference(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_courses(session, settings)
        service = make_service(session, settings)
        node = create_node(service, seed.course_id, "Cache")
        node_id = node.id
        with pytest.raises(KnowledgeModelError) as course_error:
            service.create_source(
                seed.course_id,
                node_id,
                KnowledgeSourceCreate(
                    material_id=seed.second_material_id,
                    source_reference="TXT segment 1",
                ),
            )
        assert course_error.value.code == "KNOWLEDGE_COURSE_MISMATCH"

        with pytest.raises(KnowledgeModelError) as reference_error:
            service.create_source(
                seed.course_id,
                node_id,
                KnowledgeSourceCreate(
                    material_id=seed.material_id,
                    source_reference="PDF 第 99 页",
                ),
            )
        assert reference_error.value.code == "KNOWLEDGE_SOURCE_INVALID"


def test_material_delete_cascades_sources_but_preserves_node(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_courses(session, settings)
        service = make_service(session, settings)
        node = create_node(service, seed.course_id, "Cache")
        service.create_source(
            seed.course_id,
            node.id,
            KnowledgeSourceCreate(material_id=seed.material_id, source_reference=seed.source_reference),
        )
        with session.begin():
            session.delete(session.get(Material, seed.material_id))
        assert session.get(KnowledgeSource, 1) is None
        assert session.get(KnowledgeNode, node.id) is not None


def test_node_delete_cascades_sources_and_related_edges(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_courses(session, settings)
        service = make_service(session, settings)
        first = create_node(service, seed.course_id, "Cache")
        second = create_node(service, seed.course_id, "Latency")
        edge = service.create_edge(
            seed.course_id,
            KnowledgeEdgeCreate(
                source_node_id=first.id,
                target_node_id=second.id,
                relation_type=KnowledgeRelationType.PREREQUISITE,
            ),
        )
        source = service.create_source(
            seed.course_id,
            first.id,
            KnowledgeSourceCreate(material_id=seed.material_id, source_reference=seed.source_reference),
        )
        edge_id, source_id, second_id = edge.id, source.id, second.id
        service.delete_node(seed.course_id, first.id)
        session.expire_all()
        assert session.get(KnowledgeEdge, edge_id) is None
        assert session.get(KnowledgeSource, source_id) is None
        assert session.get(KnowledgeNode, second_id) is not None


def test_course_delete_cascades_full_knowledge_model(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_courses(session, settings)
        service = make_service(session, settings)
        first = create_node(service, seed.course_id, "Cache")
        second = create_node(service, seed.course_id, "Latency")
        edge = service.create_edge(
            seed.course_id,
            KnowledgeEdgeCreate(
                source_node_id=first.id,
                target_node_id=second.id,
                relation_type=KnowledgeRelationType.PREREQUISITE,
            ),
        )
        source = service.create_source(
            seed.course_id,
            first.id,
            KnowledgeSourceCreate(material_id=seed.material_id, source_reference=seed.source_reference),
        )
        first_id, edge_id, source_id = first.id, edge.id, source.id
        with session.begin():
            CourseRepository(session).delete(session.get(Course, seed.course_id))
        session.expire_all()
        assert session.get(KnowledgeNode, first_id) is None
        assert session.get(KnowledgeEdge, edge_id) is None
        assert session.get(KnowledgeSource, source_id) is None


def test_repository_delete_sources_by_material(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_courses(session, settings)
        service = make_service(session, settings)
        node = create_node(service, seed.course_id, "Cache")
        service.create_source(
            seed.course_id,
            node.id,
            KnowledgeSourceCreate(material_id=seed.material_id, source_reference=seed.source_reference),
        )
        with session.begin():
            deleted = KnowledgeSourceRepository(session).delete_by_material(seed.material_id)
        assert deleted == 1
        assert KnowledgeSourceRepository(session).list_for_node(node.id) == []


def test_database_constraints_reject_self_cross_course_and_duplicate_records(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_courses(session, settings)
        service = make_service(session, settings)
        first = create_node(service, seed.course_id, "Cache")
        second = create_node(service, seed.course_id, "Latency")
        foreign = create_node(service, seed.second_course_id, "Graph")
        node_ids = first.id, second.id, foreign.id

    first_id, second_id, foreign_id = node_ids
    with factory() as session, pytest.raises(IntegrityError):
        with session.begin():
            session.add(
                KnowledgeEdge(
                    course_id=seed.course_id,
                    source_node_id=first_id,
                    target_node_id=first_id,
                    relation_type=KnowledgeRelationType.CONTAINS,
                )
            )
    with factory() as session, pytest.raises(IntegrityError):
        with session.begin():
            session.add(
                KnowledgeEdge(
                    course_id=seed.course_id,
                    source_node_id=first_id,
                    target_node_id=foreign_id,
                    relation_type=KnowledgeRelationType.CONTAINS,
                )
            )
    with factory() as session:
        with session.begin():
            session.add(
                KnowledgeEdge(
                    course_id=seed.course_id,
                    source_node_id=first_id,
                    target_node_id=second_id,
                    relation_type=KnowledgeRelationType.CONTAINS,
                )
            )
        with pytest.raises(IntegrityError):
            with session.begin():
                session.add(
                    KnowledgeEdge(
                        course_id=seed.course_id,
                        source_node_id=first_id,
                        target_node_id=second_id,
                        relation_type=KnowledgeRelationType.CONTAINS,
                    )
                )
    with factory() as session:
        with session.begin():
            session.add(
                KnowledgeSource(
                    knowledge_node_id=first_id,
                    material_id=seed.material_id,
                    source_reference=seed.source_reference,
                )
            )
        with pytest.raises(IntegrityError):
            with session.begin():
                session.add(
                    KnowledgeSource(
                        knowledge_node_id=first_id,
                        material_id=seed.material_id,
                        source_reference=seed.source_reference,
                    )
                )


def test_knowledge_model_and_node_detail_read_api(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_courses(session, settings)
        service = make_service(session, settings)
        parent = create_node(service, seed.course_id, "Memory Hierarchy")
        child = create_node(service, seed.course_id, "Cache")
        service.create_edge(
            seed.course_id,
            KnowledgeEdgeCreate(
                source_node_id=parent.id,
                target_node_id=child.id,
                relation_type=KnowledgeRelationType.CONTAINS,
            ),
        )
        service.create_source(
            seed.course_id,
            child.id,
            KnowledgeSourceCreate(
                material_id=seed.material_id,
                source_reference=seed.source_reference,
                excerpt="A cache stores recently used data.",
            ),
        )
        model = KnowledgeModelResponse.model_validate(get_course_knowledge_model(seed.course_id, service)).model_dump(
            mode="json"
        )
        detail = KnowledgeNodeDetailResponse.model_validate(
            get_knowledge_node_detail(seed.course_id, child.id, service)
        ).model_dump(mode="json")
    assert model["course_id"] == seed.course_id
    assert len(model["nodes"]) == 2 and len(model["edges"]) == 1
    assert not {"mastery", "progress", "confidence", "student_status"} & set(json.dumps(model).split('"'))
    assert detail["node"]["id"] == child.id
    assert detail["sources"][0]["source_reference"] == seed.source_reference
    assert detail["sources"][0]["material_title"] == "Cache notes"
    assert detail["sources"][0]["original_text_excerpt"] == "A cache stores recently used data."
    assert detail["sources"][0]["original_text_truncated"] is False
    assert len(detail["related_edges"]) == 1


def test_node_source_preview_never_falls_back_to_an_unverified_reference(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_courses(session, settings)
        service = make_service(session, settings)
        node = create_node(service, seed.course_id, "Cache")
        service.create_source(
            seed.course_id,
            node.id,
            KnowledgeSourceCreate(material_id=seed.material_id, source_reference=seed.source_reference),
        )
        # Simulate a legacy invalid relation: the read API must not disclose text
        # from a material outside the requested course.
        with session.begin():
            session.add_all(
                [
                    KnowledgeSource(
                        knowledge_node_id=node.id,
                        material_id=seed.second_material_id,
                        source_reference="TXT segment 1",
                        excerpt="Do not present this as a source quote.",
                    ),
                    KnowledgeSource(
                        knowledge_node_id=node.id,
                        material_id=seed.material_id,
                        source_reference="PDF 第 99 页",
                        excerpt="Do not invent a page preview.",
                    ),
                ]
            )

        detail = KnowledgeNodeDetailResponse.model_validate(
            get_knowledge_node_detail(seed.course_id, node.id, service)
        ).model_dump(mode="json")

    verified = next(item for item in detail["sources"] if item["source_reference"] == seed.source_reference)
    invalid = next(item for item in detail["sources"] if item["material_id"] == seed.second_material_id)
    invalid_reference = next(item for item in detail["sources"] if item["source_reference"] == "PDF 第 99 页")
    assert verified["original_text_excerpt"] == "A cache stores recently used data."
    assert invalid["material_title"] is None
    assert invalid["original_text_excerpt"] is None
    assert invalid_reference["material_title"] == "Cache notes"
    assert invalid_reference["original_text_excerpt"] is None


def test_knowledge_read_api_404_contract(database) -> None:
    factory, settings = database
    with factory() as session:
        seed = seed_courses(session, settings)
        service = make_service(session, settings)
        with pytest.raises(HTTPException) as missing_course:
            get_course_knowledge_model(999999, service)
        assert missing_course.value.status_code == 404
        with pytest.raises(ApiError) as missing_node:
            get_knowledge_node_detail(seed.course_id, 999999, service)
        assert missing_node.value.status_code == 404
        assert missing_node.value.code == "KNOWLEDGE_NODE_NOT_FOUND"
