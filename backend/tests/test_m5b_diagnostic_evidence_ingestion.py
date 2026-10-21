from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Generator
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.settings import Settings
from backend.app.db.models import (
    Assessment,
    AssessmentQuestion,
    Course,
    KnowledgeNode,
    LearningEvidence,
    Response,
    User,
)
from backend.app.models import (
    AssessmentStatus,
    AssessmentType,
    EvidenceSourceType,
    KnowledgeDifficulty,
    KnowledgeImportance,
)
from backend.app.repositories import LearningEvidenceRepository
from backend.app.services.diagnostic_evidence_ingestion import EvidenceIngestionError, EvidenceIngestionService
from backend.app.services.diagnostic_experience_service import DiagnosticExperienceService
from backend.scripts.backfill_diagnostic_evidence import backfill_diagnostic_evidence


def migrate_database(path: Path, revision: str = "head") -> str:
    database_url = f"sqlite+pysqlite:///{path}"
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


def question_snapshot(
    *,
    node_ids: tuple[int, ...] = (101,),
    max_points: int = 1,
    source_question_id: int = 77,
) -> dict[str, object]:
    return {
        "schema_version": "assessment_question_v1",
        "source_question_id": source_question_id,
        "source_question_version": 2,
        "question_type": "multiple_choice",
        "stem": "Which facts are persisted?",
        "options": [
            {"key": "A", "text": "Snapshot"},
            {"key": "B", "text": "Score"},
            {"key": "C", "text": "Live answer key"},
        ],
        "correct_answer": ["A", "B"],
        "explanation": "The immutable snapshot and deterministic score are persisted.",
        "difficulty": "medium",
        "knowledge_nodes": [
            {
                "id": node_id,
                "name": f"Historical node {node_id}",
                "role": "primary" if index == 0 else "secondary",
            }
            for index, node_id in enumerate(node_ids)
        ],
        "source_refs": [],
        "knowledge_model_version": None,
        "scoring_policy": {"version": "objective_exact_match_v1", "max_points": max_points},
    }


@dataclass
class Seed:
    database_url: str
    owner_id: int
    other_owner_id: int
    course_id: int
    other_course_id: int
    assessment_id: int
    snapshot_id: int
    response_id: int
    occurred_at: datetime


def add_assessment(
    session: Session,
    *,
    owner_id: int,
    course_id: int,
    status: AssessmentStatus,
    snapshot: dict[str, object] | None = None,
    points: Decimal | None = Decimal("1"),
    scored: bool = True,
) -> tuple[Assessment, AssessmentQuestion, Response | None]:
    occurred_at = datetime(2026, 10, 19, 9, 0, tzinfo=timezone.utc)
    assessment = Assessment(
        course_id=course_id,
        owner_id=owner_id,
        assessment_type=AssessmentType.INITIAL_DIAGNOSTIC,
        status=status,
        started_at=occurred_at,
        submitted_at=occurred_at if status == AssessmentStatus.SUBMITTED else None,
        report_policy_version="diagnostic_node_performance_v1" if status == AssessmentStatus.SUBMITTED else None,
    )
    session.add(assessment)
    session.flush()
    question = AssessmentQuestion(
        assessment_id=assessment.id,
        question_id=None,
        order_index=0,
        question_snapshot=snapshot or question_snapshot(),
    )
    session.add(question)
    session.flush()
    response: Response | None = None
    if status in {AssessmentStatus.IN_PROGRESS, AssessmentStatus.SUBMITTED}:
        response = Response(
            assessment_id=assessment.id,
            assessment_question_id=question.id,
            answer_payload={"schema_version": "objective_answer_v1", "selected_options": ["A", "B"]},
            answered_at=occurred_at,
            submitted_at=occurred_at if status == AssessmentStatus.SUBMITTED else None,
            is_correct=(points == Decimal("1")) if scored else None,
            points_awarded=points if scored else None,
        )
        session.add(response)
        session.flush()
    return assessment, question, response


def seed_database(session: Session, database_url: str) -> Seed:
    with session.begin():
        owner = User(email="m5b-owner@example.test", display_name="M5B Owner", is_active=True)
        other_owner = User(email="m5b-other@example.test", display_name="M5B Other", is_active=True)
        session.add_all([owner, other_owner])
        session.flush()
        course = Course(owner_id=owner.id, name="Evidence Ingestion", description="")
        other_course = Course(owner_id=other_owner.id, name="Other Evidence", description="")
        session.add_all([course, other_course])
        session.flush()
        for node_id in (101, 202):
            session.add(
                KnowledgeNode(
                    id=node_id,
                    course_id=course.id,
                    name=f"Current node {node_id}",
                    normalized_name=f"current node {node_id}",
                    description="Current exact-ID node.",
                    importance=KnowledgeImportance.HIGH,
                    difficulty=KnowledgeDifficulty.INTERMEDIATE,
                    is_active=True,
                    managed_by_canonicalization=True,
                )
            )
        assessment, snapshot_row, response = add_assessment(
            session,
            owner_id=owner.id,
            course_id=course.id,
            status=AssessmentStatus.SUBMITTED,
        )
        assert response is not None
        return Seed(
            database_url=database_url,
            owner_id=owner.id,
            other_owner_id=other_owner.id,
            course_id=course.id,
            other_course_id=other_course.id,
            assessment_id=assessment.id,
            snapshot_id=snapshot_row.id,
            response_id=response.id,
            occurred_at=response.submitted_at,
        )


@pytest.fixture
def database(tmp_path: Path) -> Generator[tuple[sessionmaker[Session], Seed], None, None]:
    database_url = migrate_database(tmp_path / "m5b.sqlite3")
    engine = make_engine(database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        seed = seed_database(session, database_url)
    yield factory, seed
    engine.dispose()


def test_b01_valid_submitted_diagnostic_creates_evidence(database) -> None:
    factory, seed = database
    with factory() as session:
        result = EvidenceIngestionService(session).ingest_assessment(seed.assessment_id)
        assert (result.candidates, result.created, result.skipped) == (1, 1, 0)
        evidence = session.scalar(select(LearningEvidence))
        assert evidence is not None
        assert evidence.normalized_score == Decimal("1.00000")
        assert evidence.source_response_id == seed.response_id
        assert evidence.current_knowledge_node_id == 101


@pytest.mark.parametrize(
    "status",
    [AssessmentStatus.DRAFT, AssessmentStatus.READY, AssessmentStatus.IN_PROGRESS],
)
def test_b02_non_submitted_diagnostic_is_rejected(database, status: AssessmentStatus) -> None:
    factory, seed = database
    with factory() as session, session.begin():
        assessment, _, _ = add_assessment(
            session,
            owner_id=seed.owner_id,
            course_id=seed.course_id,
            status=status,
            scored=False,
        )
        assessment_id = assessment.id
    with factory() as session:
        with pytest.raises(EvidenceIngestionError) as captured:
            EvidenceIngestionService(session).ingest_assessment(assessment_id)
        assert captured.value.code == "ASSESSMENT_NOT_SUBMITTED"
        assert LearningEvidenceRepository(session).list_by_source(EvidenceSourceType.DIAGNOSTIC, assessment_id) == []


def test_b03_repeated_ingestion_is_idempotent(database) -> None:
    factory, seed = database
    with factory() as session:
        service = EvidenceIngestionService(session)
        first = service.ingest_assessment(seed.assessment_id)
        second = service.ingest_assessment(seed.assessment_id)
        third = service.ingest_assessment(seed.assessment_id)
        assert (first.created, first.skipped) == (1, 0)
        assert (second.created, second.skipped) == (0, 1)
        assert (third.created, third.skipped) == (0, 1)
        assert second.skip_reasons == {"SKIPPED_ALREADY_EXISTS": 1}


def test_b04_database_unique_constraint_remains_the_concurrency_guard(database) -> None:
    factory, seed = database
    with factory() as session:
        service = EvidenceIngestionService(session)
        plan = service.extractor.extract_assessment(seed.assessment_id)
        service.ingest_assessment(seed.assessment_id)
    with factory() as session:
        with pytest.raises(IntegrityError), session.begin():
            LearningEvidenceRepository(session).create(LearningEvidence(**plan.candidates[0].model_dump()))
    with factory() as session:
        assert (
            len(LearningEvidenceRepository(session).list_by_source(EvidenceSourceType.DIAGNOSTIC, seed.assessment_id))
            == 1
        )


def test_b05_multiple_nodes_receive_equal_fractional_attribution(database) -> None:
    factory, seed = database
    with factory() as session, session.begin():
        row = session.get(AssessmentQuestion, seed.snapshot_id)
        row.question_snapshot = question_snapshot(node_ids=(101, 202))
    with factory() as session:
        result = EvidenceIngestionService(session).ingest_assessment(seed.assessment_id)
        rows = LearningEvidenceRepository(session).list_by_source(EvidenceSourceType.DIAGNOSTIC, seed.assessment_id)
        assert result.created == 2
        assert {row.historical_knowledge_node_ref for row in rows} == {101, 202}
        assert {row.attribution_weight for row in rows} == {Decimal("0.50000")}
        assert {row.normalized_score for row in rows} == {Decimal("1.00000")}


def test_b06_ingestion_never_mutates_m4_facts(database) -> None:
    factory, seed = database
    with factory() as session:
        assessment = session.get(Assessment, seed.assessment_id)
        question = session.get(AssessmentQuestion, seed.snapshot_id)
        response = session.get(Response, seed.response_id)
        before = (
            assessment.status,
            assessment.submitted_at,
            deepcopy(question.question_snapshot),
            deepcopy(response.answer_payload),
            response.is_correct,
            response.points_awarded,
        )
        session.rollback()
        EvidenceIngestionService(session).ingest_assessment(seed.assessment_id)
        session.expire_all()
        assessment = session.get(Assessment, seed.assessment_id)
        question = session.get(AssessmentQuestion, seed.snapshot_id)
        response = session.get(Response, seed.response_id)
        after = (
            assessment.status,
            assessment.submitted_at,
            question.question_snapshot,
            response.answer_payload,
            response.is_correct,
            response.points_awarded,
        )
        assert after == before


def test_b07_missing_current_node_preserves_unmapped_historical_evidence(database) -> None:
    factory, seed = database
    with factory() as session, session.begin():
        row = session.get(AssessmentQuestion, seed.snapshot_id)
        row.question_snapshot = question_snapshot(node_ids=(303,))
    with factory() as session:
        result = EvidenceIngestionService(session).ingest_assessment(seed.assessment_id)
        evidence = session.scalar(select(LearningEvidence))
        assert result.unavailable_historical_nodes == 1
        assert evidence.historical_knowledge_node_ref == 303
        assert evidence.current_knowledge_node_id is None


def test_b08_backfill_dry_run_plans_without_writing(database) -> None:
    factory, seed = database
    summary = backfill_diagnostic_evidence(database_url=seed.database_url, dry_run=True)
    assert summary.assessments_scanned == 1
    assert summary.assessments_eligible == 1
    assert summary.evidence_planned == 1
    assert summary.evidence_created == 0
    with factory() as session:
        assert session.scalar(select(LearningEvidence)) is None


def test_b09_historical_backfill_is_repeatably_idempotent(database) -> None:
    factory, seed = database
    first = backfill_diagnostic_evidence(database_url=seed.database_url)
    second = backfill_diagnostic_evidence(database_url=seed.database_url)
    assert (first.evidence_created, first.evidence_skipped) == (1, 0)
    assert (second.evidence_created, second.evidence_skipped) == (0, 1)
    with factory() as session:
        assert len(list(session.scalars(select(LearningEvidence)))) == 1


def test_b10_successful_diagnostic_submission_synchronizes_evidence(database) -> None:
    factory, seed = database
    with factory() as session, session.begin():
        assessment, _, _ = add_assessment(
            session,
            owner_id=seed.owner_id,
            course_id=seed.course_id,
            status=AssessmentStatus.IN_PROGRESS,
            scored=False,
        )
        assessment_id = assessment.id
    settings = Settings(
        legacy_bootstrap_user="m5b-owner@example.test",
        legacy_bootstrap_user_display_name="M5B Owner",
    )
    with factory() as session:
        DiagnosticExperienceService(session, settings).submit(assessment_id)
    with factory() as session:
        assessment = session.get(Assessment, assessment_id)
        evidence = LearningEvidenceRepository(session).list_by_source(EvidenceSourceType.DIAGNOSTIC, assessment_id)
        assert assessment.status == AssessmentStatus.SUBMITTED
        assert len(evidence) == 1


def test_b11_sync_failure_preserves_submission_and_idempotent_retry_recovers(
    database, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory, seed = database
    with factory() as session, session.begin():
        assessment, _, _ = add_assessment(
            session,
            owner_id=seed.owner_id,
            course_id=seed.course_id,
            status=AssessmentStatus.IN_PROGRESS,
            scored=False,
        )
        assessment_id = assessment.id
    settings = Settings(legacy_bootstrap_user="m5b-owner@example.test")
    original_create = LearningEvidenceRepository.create

    def fail_create(_repository, _evidence):
        raise RuntimeError("simulated evidence outage")

    monkeypatch.setattr(LearningEvidenceRepository, "create", fail_create)
    with factory() as session:
        DiagnosticExperienceService(session, settings).submit(assessment_id)
    with factory() as session:
        assert session.get(Assessment, assessment_id).status == AssessmentStatus.SUBMITTED
        assert LearningEvidenceRepository(session).list_by_source(EvidenceSourceType.DIAGNOSTIC, assessment_id) == []

    monkeypatch.setattr(LearningEvidenceRepository, "create", original_create)
    with factory() as session:
        recovered = EvidenceIngestionService(session).ingest_assessment(assessment_id)
        assert recovered.created == 1


@pytest.mark.parametrize("boundary", ["user", "course"])
def test_b12_expected_owner_and_course_are_isolated(database, boundary: str) -> None:
    factory, seed = database
    kwargs = (
        {"expected_user_id": seed.other_owner_id}
        if boundary == "user"
        else {"expected_course_id": seed.other_course_id}
    )
    with factory() as session:
        with pytest.raises(EvidenceIngestionError) as captured:
            EvidenceIngestionService(session).ingest_assessment(seed.assessment_id, **kwargs)
        assert captured.value.code == "SOURCE_OWNERSHIP_MISMATCH"


def test_b13_invalid_snapshot_is_reported_without_evidence(database) -> None:
    factory, seed = database
    with factory() as session, session.begin():
        row = session.get(AssessmentQuestion, seed.snapshot_id)
        row.question_snapshot = {"schema_version": "corrupt"}
    with factory() as session:
        result = EvidenceIngestionService(session).ingest_assessment(seed.assessment_id)
        assert result.created == 0
        assert [issue.code for issue in result.issues] == ["INVALID_QUESTION_SNAPSHOT"]
        assert session.scalar(select(LearningEvidence)) is None


@pytest.mark.parametrize(
    ("points", "maximum", "expected"),
    [
        (Decimal("0"), 2, Decimal("0.00000")),
        (Decimal("2"), 2, Decimal("1.00000")),
        (Decimal("0.5"), 2, Decimal("0.25000")),
    ],
)
def test_b14_valid_score_boundaries_and_partial_scores_are_normalized(database, points, maximum, expected) -> None:
    factory, seed = database
    with factory() as session, session.begin():
        question = session.get(AssessmentQuestion, seed.snapshot_id)
        response = session.get(Response, seed.response_id)
        question.question_snapshot = question_snapshot(max_points=maximum)
        response.points_awarded = points
        response.is_correct = points == Decimal(maximum)
    with factory() as session:
        EvidenceIngestionService(session).ingest_assessment(seed.assessment_id)
        evidence = session.scalar(select(LearningEvidence))
        assert evidence.normalized_score == expected


def test_b14_illegal_persisted_score_is_rejected(database) -> None:
    factory, seed = database
    with factory() as session, session.begin():
        response = session.get(Response, seed.response_id)
        response.points_awarded = Decimal("2")
    with factory() as session:
        result = EvidenceIngestionService(session).ingest_assessment(seed.assessment_id)
        assert result.created == 0
        assert [issue.code for issue in result.issues] == ["INVALID_NORMALIZED_SCORE"]


def test_m5b_migration_adds_nullable_current_node_mapping(tmp_path: Path) -> None:
    path = tmp_path / "m5a-to-m5b.sqlite3"
    database_url = migrate_database(path, "0010_m5a_learning_evidence")
    migrate_database(path)
    engine = make_engine(database_url)
    columns = {column["name"]: column for column in inspect(engine).get_columns("learning_evidence")}
    assert columns["current_knowledge_node_id"]["nullable"] is True
    foreign_keys = inspect(engine).get_foreign_keys("learning_evidence")
    assert any(
        item["referred_table"] == "knowledge_nodes" and item["constrained_columns"] == ["current_knowledge_node_id"]
        for item in foreign_keys
    )
    engine.dispose()
