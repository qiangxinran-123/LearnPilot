from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from backend.app.api.knowledge import (
    browse_course_knowledge_nodes,
    get_course_knowledge_build_status,
    get_course_knowledge_model,
    start_course_knowledge_build_job,
)
from backend.app.core.settings import Settings
from backend.app.db.models import (
    Course,
    CourseKnowledgeBuildState,
    KnowledgeCandidate,
    KnowledgeCandidateResolution,
    KnowledgeCanonicalizationRun,
    KnowledgeEdge,
    KnowledgeExtractionRun,
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
    KnowledgeExtractionStatus,
    KnowledgeImportance,
    KnowledgeRelationshipStatus,
    KnowledgeRelationType,
    KnowledgeResolutionType,
)
from backend.app.services import course_knowledge_build_job_service as job_module
from backend.app.services.course_knowledge_build_job_service import CourseKnowledgeBuildJobService
from backend.app.services.course_knowledge_build_service import CourseKnowledgeBuildError
from backend.app.services.course_service import ResourceNotFoundError
from backend.app.services.knowledge_model_service import get_knowledge_model_service


@pytest.fixture
def database(tmp_path: Path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'm3e-workspace.sqlite3'}"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=environment,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=database_url,
        upload_root=tmp_path / "uploads",
        legacy_bootstrap_user="workspace-owner@example.test",
        legacy_bootstrap_user_display_name="Workspace Owner",
        llm_mode="mock",
    )
    yield factory, settings
    engine.dispose()


def seed_course(session: Session, settings: Settings) -> tuple[int, int, int, list[int], int]:
    with session.begin():
        owner = User(email=settings.legacy_bootstrap_user, display_name="Owner", is_active=True)
        outsider = User(email="outsider@example.test", display_name="Outsider", is_active=True)
        session.add_all([owner, outsider])
        session.flush()
        course = Course(owner_id=owner.id, name="Linear Algebra", description="")
        private = Course(owner_id=outsider.id, name="Private", description="")
        empty = Course(owner_id=owner.id, name="Empty", description="")
        session.add_all([course, private, empty])
        session.flush()
        text = "Vector, Basis and Dimension"
        material = Material(
            course_id=course.id,
            title="Lecture",
            material_type="txt",
            summary="",
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
                segments=[{"text": text, "source_reference": "TXT segment 1"}],
                content_hash=content_hash,
                parser_name="test-parser",
                parser_version="1",
                page_count=1,
            )
        )
        extraction = KnowledgeExtractionRun(
            course_id=course.id,
            material_id=material.id,
            material_content_hash=content_hash,
            status=KnowledgeExtractionStatus.SUCCESS,
            provider="mock",
            model="mock",
            prompt_version="test",
            candidate_count=3,
            is_current=True,
        )
        canonicalization = KnowledgeCanonicalizationRun(
            course_id=course.id,
            candidate_snapshot_hash="a" * 64,
            status=KnowledgeCanonicalizationStatus.SUCCESS,
            provider="mock",
            model="mock",
            prompt_version="test",
            configuration_version="test",
            candidate_count=3,
            canonical_node_count=3,
            merged_candidate_count=0,
            unresolved_count=0,
            is_current=True,
        )
        relationships = KnowledgeRelationshipRun(
            course_id=course.id,
            knowledge_snapshot_hash="b" * 64,
            status=KnowledgeRelationshipStatus.SUCCESS,
            provider="mock",
            model="mock",
            prompt_version="test",
            node_count=3,
            contains_edge_count=1,
            prerequisite_edge_count=1,
            rejected_edge_count=0,
            is_current=True,
        )
        session.add_all([extraction, canonicalization, relationships])
        session.flush()
        node_ids = []
        for name in ("Vector", "Basis", "Dimension"):
            node = KnowledgeNode(
                course_id=course.id,
                name=name,
                normalized_name=name.casefold(),
                description=f"Verified {name}.",
                importance=KnowledgeImportance.MEDIUM,
                difficulty=KnowledgeDifficulty.BASIC,
                is_active=True,
                managed_by_canonicalization=False,
            )
            candidate = KnowledgeCandidate(
                extraction_run_id=extraction.id,
                course_id=course.id,
                material_id=material.id,
                name=name,
                normalized_name=name.casefold(),
                description=name,
                importance=KnowledgeImportance.MEDIUM,
                difficulty=KnowledgeDifficulty.BASIC,
            )
            session.add_all([node, candidate])
            session.flush()
            session.add(
                KnowledgeCandidateResolution(
                    canonicalization_run_id=canonicalization.id,
                    course_id=course.id,
                    candidate_id=candidate.id,
                    knowledge_node_id=node.id,
                    resolution_type=KnowledgeResolutionType.NEW_NODE,
                )
            )
            node_ids.append(node.id)
        session.add(
            KnowledgeSource(
                knowledge_node_id=node_ids[0],
                material_id=material.id,
                source_reference="TXT segment 1",
                excerpt="Verified source.",
            )
        )
        manual = KnowledgeNode(
            course_id=course.id,
            name="Unconfirmed Manual Node",
            normalized_name="unconfirmed manual node",
            description="",
            importance=KnowledgeImportance.LOW,
            difficulty=KnowledgeDifficulty.BASIC,
            is_active=True,
            managed_by_canonicalization=False,
        )
        session.add(manual)
        session.flush()
        session.add_all(
            [
                KnowledgeEdge(
                    course_id=course.id,
                    source_node_id=node_ids[0],
                    target_node_id=node_ids[1],
                    relation_type=KnowledgeRelationType.CONTAINS,
                ),
                KnowledgeEdge(
                    course_id=course.id,
                    source_node_id=node_ids[1],
                    target_node_id=node_ids[2],
                    relation_type=KnowledgeRelationType.PREREQUISITE,
                ),
                KnowledgeEdge(
                    course_id=course.id,
                    source_node_id=node_ids[0],
                    target_node_id=manual.id,
                    relation_type=KnowledgeRelationType.PREREQUISITE,
                ),
            ]
        )
        return course.id, private.id, empty.id, node_ids, manual.id


def test_canonical_browse_is_bounded_searchable_and_course_scoped(database) -> None:
    factory, settings = database
    with factory() as session:
        course_id, private_id, _, node_ids, manual_id = seed_course(session, settings)
        service = get_knowledge_model_service(session=session, settings=settings)
        first = browse_course_knowledge_nodes(course_id, q="", offset=0, limit=2, service=service)
        second = browse_course_knowledge_nodes(course_id, q="", offset=2, limit=2, service=service)
        assert first["total"] == second["total"] == 3
        assert [node.name for node in first["nodes"]] == ["Basis", "Dimension"]
        assert [node.name for node in second["nodes"]] == ["Vector"]
        assert [node.id for node in browse_course_knowledge_nodes(course_id, q="basis", service=service)["nodes"]] == [
            node_ids[1]
        ]
        assert browse_course_knowledge_nodes(course_id, q="missing", service=service)["total"] == 0
        model = get_course_knowledge_model(course_id, service=service, canonical_only=True)
        assert {node.id for node in model["nodes"]} == set(node_ids)
        assert manual_id not in {edge.target_node_id for edge in model["edges"]}
        assert len(model["edges"]) == 2
        with pytest.raises(HTTPException) as error:
            browse_course_knowledge_nodes(private_id, service=service)
        assert error.value.status_code == 404


def test_build_status_claim_and_content_snapshot_detect_new_material(database) -> None:
    factory, settings = database
    with factory() as session:
        course_id, private_id, empty_id, _, _ = seed_course(session, settings)
        service = CourseKnowledgeBuildJobService(session, settings)
        empty = service.get_status(empty_id)
        assert empty.state == "no_materials"
        assert empty.can_build is False
        with pytest.raises(ResourceNotFoundError) as error:
            service.get_status(private_id)
        assert error.value.resource == "Course"

        initial = service.get_status(course_id)
        assert initial.state == "ready"
        assert (initial.material_count, initial.ready_material_count, initial.node_count) == (1, 1, 3)
        assert (initial.contains_edge_count, initial.prerequisite_edge_count) == (1, 1)
        first = service.start(course_id)
        repeated = service.start(course_id)
        assert first.job_id == repeated.job_id == 1
        assert first.should_schedule is True
        assert repeated.should_schedule is False
        assert service.get_status(course_id).state == "running"
        with session.begin():
            state = session.get(CourseKnowledgeBuildState, course_id)
            assert state is not None
            state.status = "success"
            state.stage = "complete"
            state.success_material_snapshot_hash = state.requested_material_snapshot_hash
            state.checkpoint_json = None
        assert service.get_status(course_id).state == "ready"
        assert service.start(course_id).reused is True

        with session.begin():
            text = "New lecture material"
            material = Material(
                course_id=course_id,
                title="New Lecture",
                material_type="txt",
                summary="",
                extraction_status="SUCCESS",
                text_extracted=True,
                text_length=len(text),
                text_preview=text,
            )
            session.add(material)
            session.flush()
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
        updated = service.get_status(course_id)
        assert updated.state == "update_available"
        assert updated.needs_update is True
        assert updated.node_count == 3
        assert updated.ready_material_count == 2
        assert service.start(course_id).job_id == 2


def test_preexisting_m3d_model_detects_new_material_without_m3e_snapshot(database) -> None:
    factory, settings = database
    with factory() as session:
        course_id, _, _, _, _ = seed_course(session, settings)
        service = CourseKnowledgeBuildJobService(session, settings)
        assert service.get_status(course_id).state == "ready"
        with session.begin():
            text = "Fresh note without an extraction run"
            material = Material(
                course_id=course_id,
                title="Fresh Note",
                material_type="txt",
                summary="",
                extraction_status="SUCCESS",
                text_extracted=True,
                text_length=len(text),
                text_preview=text,
            )
            session.add(material)
            session.flush()
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
        result = service.get_status(course_id)
        assert result.state == "update_available"
        assert result.needs_update is True
        assert result.node_count == 3


def test_expired_build_restores_description_and_provenance(database) -> None:
    factory, settings = database
    with factory() as session:
        course_id, _, _, node_ids, _ = seed_course(session, settings)
        service = CourseKnowledgeBuildJobService(session, settings)
        service.start(course_id)
        with session.begin():
            node = session.get(KnowledgeNode, node_ids[0])
            assert node is not None
            node.description = "Unpublished replacement."
            source = session.query(KnowledgeSource).filter_by(knowledge_node_id=node.id).one()
            source.excerpt = "Unpublished source."
            state = session.get(CourseKnowledgeBuildState, course_id)
            assert state is not None
            state.stage = "canonicalizing"
            state.heartbeat_at = datetime.now(timezone.utc) - timedelta(minutes=31)
        recovered = service.get_status(course_id)
        assert recovered.state == "update_failed"
        assert recovered.error_code == "KNOWLEDGE_MODEL_BUILD_INTERRUPTED"
        with session.begin():
            node = session.get(KnowledgeNode, node_ids[0])
            source = session.query(KnowledgeSource).filter_by(knowledge_node_id=node_ids[0]).one()
            assert node is not None and node.description == "Verified Vector."
            assert source.excerpt == "Verified source."


def test_background_job_uses_independent_session_and_persists_success(database, monkeypatch) -> None:
    factory, settings = database
    with factory() as session:
        course_id, _, _, _, _ = seed_course(session, settings)
        job = CourseKnowledgeBuildJobService(session, settings).start(course_id)

    observed_stages: list[str] = []

    class SuccessfulBuild:
        def build(self, requested_course_id: int, *, on_stage):
            assert requested_course_id == course_id
            for stage in ("extracting", "canonicalizing", "relationships"):
                on_stage(stage)
                with factory() as status_session:
                    observed = CourseKnowledgeBuildJobService(status_session, settings).get_status(course_id)
                    assert observed.state == "running"
                    observed_stages.append(observed.stage)
            return SimpleNamespace(node_count=3, contains_edge_count=1, prerequisite_edge_count=1)

    monkeypatch.setattr(job_module, "get_session_factory", lambda: factory)
    monkeypatch.setattr(job_module, "get_course_knowledge_build_service", lambda session, settings: SuccessfulBuild())
    job_module.run_course_knowledge_build_job(course_id, job.job_id, settings)

    with factory() as session:
        status = CourseKnowledgeBuildJobService(session, settings).get_status(course_id)
        assert status.state == "ready"
        assert status.stage is None
        assert status.needs_update is False
        assert observed_stages == ["extracting", "canonicalizing", "relationships"]
        repeated = CourseKnowledgeBuildJobService(session, settings).start(course_id)
        assert repeated.reused is True and repeated.should_schedule is False


def test_background_update_failure_restores_existing_model(database, monkeypatch) -> None:
    factory, settings = database
    with factory() as session:
        course_id, _, _, node_ids, _ = seed_course(session, settings)
        job = CourseKnowledgeBuildJobService(session, settings).start(course_id)

    class FailingBuild:
        def __init__(self, build_session: Session) -> None:
            self.session = build_session

        def build(self, requested_course_id: int, *, on_stage):
            assert requested_course_id == course_id
            on_stage("canonicalizing")
            with self.session.begin():
                node = self.session.get(KnowledgeNode, node_ids[0])
                assert node is not None
                node.description = "Unpublished update."
                source = self.session.query(KnowledgeSource).filter_by(knowledge_node_id=node.id).one()
                source.excerpt = "Unpublished source."
            raise CourseKnowledgeBuildError("KNOWLEDGE_MODEL_BUILD_FAILED", "Safe build failure.")

    monkeypatch.setattr(job_module, "get_session_factory", lambda: factory)
    monkeypatch.setattr(
        job_module,
        "get_course_knowledge_build_service",
        lambda session, settings: FailingBuild(session),
    )
    job_module.run_course_knowledge_build_job(course_id, job.job_id, settings)

    with factory() as session:
        status = CourseKnowledgeBuildJobService(session, settings).get_status(course_id)
        assert status.state == "update_failed"
        assert status.error_code == "KNOWLEDGE_MODEL_BUILD_FAILED"
        with session.begin():
            node = session.get(KnowledgeNode, node_ids[0])
            source = session.query(KnowledgeSource).filter_by(knowledge_node_id=node_ids[0]).one()
            assert node is not None and node.description == "Verified Vector."
            assert source.excerpt == "Verified source."


def test_build_job_api_contract_reuses_claim_and_enforces_course_ownership(database) -> None:
    factory, settings = database
    with factory() as session:
        course_id, private_id, _, _, _ = seed_course(session, settings)
        service = CourseKnowledgeBuildJobService(session, settings)
        initial = get_course_knowledge_build_status(course_id, service)
        assert initial["state"] == "ready"
        with pytest.raises(HTTPException) as status_error:
            get_course_knowledge_build_status(private_id, service)
        assert status_error.value.status_code == 404
        with pytest.raises(HTTPException) as build_error:
            start_course_knowledge_build_job(private_id, BackgroundTasks(), service)
        assert build_error.value.status_code == 404

        first_tasks = BackgroundTasks()
        first = start_course_knowledge_build_job(course_id, first_tasks, service)
        repeated_tasks = BackgroundTasks()
        repeated = start_course_knowledge_build_job(course_id, repeated_tasks, service)
        assert first["job_id"] == repeated["job_id"] == 1
        assert first["reused"] is False
        assert repeated["reused"] is True
        assert len(first_tasks.tasks) == 1
        assert repeated_tasks.tasks == []
        running = get_course_knowledge_build_status(course_id, service)
        assert running["state"] == "running"
        assert running["stage"] == "queued"
        assert running["can_build"] is False
