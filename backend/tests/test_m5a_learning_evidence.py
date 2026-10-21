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
from pydantic import ValidationError
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.models import Assessment, AssessmentQuestion, Course, LearningEvidence, Response, User
from backend.app.models import AssessmentStatus, AssessmentType, EvidenceSourceType, QuestionDifficulty
from backend.app.repositories import LearningEvidenceRepository
from backend.app.schemas.learning_evidence import LearningEvidenceCreateSchema
from backend.app.services.learning_evidence_service import LearningEvidenceError, LearningEvidenceService


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


def snapshot(*, source_question_id: int = 77) -> dict[str, object]:
    return {
        "schema_version": "assessment_question_v1",
        "source_question_id": source_question_id,
        "source_question_version": 3,
        "question_type": "single_choice",
        "stem": "Which policy is deterministic?",
        "options": [{"key": "A", "text": "Exact match"}, {"key": "B", "text": "LLM judgment"}],
        "correct_answer": ["A"],
        "explanation": "The saved policy uses exact match.",
        "difficulty": "medium",
        "knowledge_nodes": [
            {"id": 101, "name": "Determinism", "role": "primary"},
            {"id": 202, "name": "Historical identity", "role": "secondary"},
        ],
        "source_refs": [],
        "knowledge_model_version": "knowledge-model-v3",
        "scoring_policy": {"version": "objective_exact_match_v1", "max_points": 1},
    }


@dataclass
class Seed:
    owner_id: int
    other_owner_id: int
    course_id: int
    other_course_id: int
    assessment_id: int
    snapshot_id: int
    response_id: int
    other_assessment_id: int
    other_snapshot_id: int
    other_response_id: int
    occurred_at: datetime


def seed_sources(session: Session) -> Seed:
    occurred_at = datetime(2026, 10, 19, 8, 30, tzinfo=timezone.utc)
    with session.begin():
        owner = User(email="evidence-owner@example.test", display_name="Evidence Owner", is_active=True)
        other_owner = User(email="evidence-other@example.test", display_name="Other Owner", is_active=True)
        session.add_all([owner, other_owner])
        session.flush()
        course = Course(owner_id=owner.id, name="Evidence Course", description="")
        other_course = Course(owner_id=other_owner.id, name="Other Course", description="")
        session.add_all([course, other_course])
        session.flush()

        first = Assessment(
            course_id=course.id,
            owner_id=owner.id,
            assessment_type=AssessmentType.INITIAL_DIAGNOSTIC,
            status=AssessmentStatus.SUBMITTED,
            submitted_at=occurred_at,
        )
        second = Assessment(
            course_id=course.id,
            owner_id=owner.id,
            assessment_type=AssessmentType.INITIAL_DIAGNOSTIC,
            status=AssessmentStatus.SUBMITTED,
            submitted_at=occurred_at,
        )
        session.add_all([first, second])
        session.flush()
        first_snapshot = AssessmentQuestion(
            assessment_id=first.id,
            question_id=None,
            order_index=0,
            question_snapshot=snapshot(),
        )
        second_snapshot = AssessmentQuestion(
            assessment_id=second.id,
            question_id=None,
            order_index=0,
            question_snapshot=snapshot(),
        )
        session.add_all([first_snapshot, second_snapshot])
        session.flush()
        first_response = Response(
            assessment_id=first.id,
            assessment_question_id=first_snapshot.id,
            answer_payload={"schema_version": "objective_answer_v1", "selected_options": ["A"]},
            answered_at=occurred_at,
            submitted_at=occurred_at,
            is_correct=True,
            points_awarded=Decimal("1"),
        )
        second_response = Response(
            assessment_id=second.id,
            assessment_question_id=second_snapshot.id,
            answer_payload={"schema_version": "objective_answer_v1", "selected_options": ["A"]},
            answered_at=occurred_at,
            submitted_at=occurred_at,
            is_correct=True,
            points_awarded=Decimal("1"),
        )
        session.add_all([first_response, second_response])
        session.flush()
        return Seed(
            owner_id=owner.id,
            other_owner_id=other_owner.id,
            course_id=course.id,
            other_course_id=other_course.id,
            assessment_id=first.id,
            snapshot_id=first_snapshot.id,
            response_id=first_response.id,
            other_assessment_id=second.id,
            other_snapshot_id=second_snapshot.id,
            other_response_id=second_response.id,
            occurred_at=occurred_at,
        )


@pytest.fixture
def database(tmp_path: Path) -> Generator[tuple[sessionmaker[Session], Seed], None, None]:
    database_url = migrate_database(tmp_path / "m5a.sqlite3")
    engine = make_engine(database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        seed = seed_sources(session)
    yield factory, seed
    engine.dispose()


def evidence_payload(seed: Seed, **overrides: object) -> LearningEvidenceCreateSchema:
    values: dict[str, object] = {
        "user_id": seed.owner_id,
        "course_id": seed.course_id,
        "source_type": EvidenceSourceType.DIAGNOSTIC,
        "source_assessment_id": seed.assessment_id,
        "source_question_snapshot_id": seed.snapshot_id,
        "source_response_id": seed.response_id,
        "historical_knowledge_node_ref": 101,
        "knowledge_model_version": "knowledge-model-v3",
        "normalized_score": Decimal("1"),
        "difficulty": QuestionDifficulty.MEDIUM,
        "attribution_weight": Decimal("1"),
        "source_scoring_version": "objective_exact_match_v1",
        "evidence_schema_version": "learning_evidence_v1",
        "occurred_at": seed.occurred_at,
    }
    values.update(overrides)
    return LearningEvidenceCreateSchema.model_validate(values)


def test_t01_migration_upgrades_m4_schema_without_changing_existing_data(tmp_path: Path) -> None:
    path = tmp_path / "m4-to-m5a.sqlite3"
    database_url = migrate_database(path, "0009_m4e_diagnostic_report_policy")
    engine = make_engine(database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session, session.begin():
        owner = User(email="migration@example.test", display_name="Migration", is_active=True)
        session.add(owner)
        session.flush()
        course = Course(owner_id=owner.id, name="Preserved", description="M4 data")
        session.add(course)
        session.flush()
        preserved_ids = (owner.id, course.id)
    engine.dispose()

    migrate_database(path)
    migrated_engine = make_engine(database_url)
    migrated_factory = sessionmaker(bind=migrated_engine)
    assert "learning_evidence" in inspect(migrated_engine).get_table_names()
    with migrated_factory() as session:
        assert session.get(User, preserved_ids[0]).email == "migration@example.test"
        assert session.get(Course, preserved_ids[1]).description == "M4 data"
    migrated_engine.dispose()


def test_t02_evidence_persistence_and_readback(database) -> None:
    factory, seed = database
    with factory() as session:
        created = LearningEvidenceService(session).create(evidence_payload(seed))
        evidence_id = created.id
    with factory() as session:
        stored = LearningEvidenceRepository(session).get_by_id(evidence_id)
        assert stored is not None
        assert stored.normalized_score == Decimal("1.00000")
        assert stored.historical_knowledge_node_ref == 101
        assert LearningEvidenceRepository(session).list_by_source(
            EvidenceSourceType.DIAGNOSTIC, seed.assessment_id
        ) == [stored]


def test_t03_database_unique_constraint_rejects_duplicate_evidence(database) -> None:
    factory, seed = database
    with factory() as session:
        LearningEvidenceService(session).create(evidence_payload(seed))
        with pytest.raises(IntegrityError):
            LearningEvidenceService(session).create(evidence_payload(seed))
        assert len(LearningEvidenceRepository(session).list_by_course_and_user(seed.course_id, seed.owner_id)) == 1


def test_t04_same_question_in_distinct_assessments_is_not_deduplicated(database) -> None:
    factory, seed = database
    with factory() as session:
        LearningEvidenceService(session).create(evidence_payload(seed))
        LearningEvidenceService(session).create(
            evidence_payload(
                seed,
                source_assessment_id=seed.other_assessment_id,
                source_question_snapshot_id=seed.other_snapshot_id,
                source_response_id=seed.other_response_id,
            )
        )
        assert len(LearningEvidenceRepository(session).list_by_course_and_user(seed.course_id, seed.owner_id)) == 2


def test_t05_one_snapshot_can_store_distinct_historical_nodes(database) -> None:
    factory, seed = database
    with factory() as session:
        LearningEvidenceService(session).create(
            evidence_payload(seed, historical_knowledge_node_ref=101, attribution_weight=Decimal("0.7"))
        )
        LearningEvidenceService(session).create(
            evidence_payload(seed, historical_knowledge_node_ref=202, attribution_weight=Decimal("0.3"))
        )
        assert [
            row.historical_knowledge_node_ref
            for row in LearningEvidenceRepository(session).list_by_source(
                EvidenceSourceType.DIAGNOSTIC, seed.assessment_id
            )
        ] == [101, 202]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("normalized_score", Decimal("-0.00001")),
        ("normalized_score", Decimal("1.00001")),
        ("attribution_weight", Decimal("0")),
        ("attribution_weight", Decimal("1.00001")),
    ],
)
def test_t06_score_and_weight_ranges_are_enforced(database, field: str, value: Decimal) -> None:
    factory, seed = database
    valid = evidence_payload(seed).model_dump()
    values = {**valid, field: value}
    with pytest.raises(ValidationError):
        LearningEvidenceCreateSchema.model_validate(values)
    with factory() as session:
        with pytest.raises(IntegrityError), session.begin():
            LearningEvidenceRepository(session).create(LearningEvidence(**values))


def test_t07_invalid_source_reference_is_rejected(database) -> None:
    factory, seed = database
    with factory() as session:
        with pytest.raises(LearningEvidenceError) as captured:
            LearningEvidenceService(session).create(evidence_payload(seed, source_response_id=999_999))
        assert captured.value.code == "SOURCE_RESPONSE_MISMATCH"
        assert LearningEvidenceRepository(session).list_by_course_and_user(seed.course_id, seed.owner_id) == []


@pytest.mark.parametrize("field", ["user_id", "course_id"])
def test_t08_cross_owner_or_course_source_is_rejected(database, field: str) -> None:
    factory, seed = database
    invalid = seed.other_owner_id if field == "user_id" else seed.other_course_id
    with factory() as session:
        with pytest.raises(LearningEvidenceError) as captured:
            LearningEvidenceService(session).create(evidence_payload(seed, **{field: invalid}))
        assert captured.value.code == "SOURCE_OWNERSHIP_MISMATCH"


def test_t09_evidence_creation_does_not_mutate_m4_sources(database) -> None:
    factory, seed = database
    with factory() as session:
        assessment = session.get(Assessment, seed.assessment_id)
        snapshot_row = session.get(AssessmentQuestion, seed.snapshot_id)
        response = session.get(Response, seed.response_id)
        before = (
            assessment.status,
            assessment.submitted_at,
            deepcopy(snapshot_row.question_snapshot),
            deepcopy(response.answer_payload),
            response.is_correct,
            response.points_awarded,
        )
        session.rollback()
        LearningEvidenceService(session).create(evidence_payload(seed))
        session.expire_all()
        assessment = session.get(Assessment, seed.assessment_id)
        snapshot_row = session.get(AssessmentQuestion, seed.snapshot_id)
        response = session.get(Response, seed.response_id)
        after = (
            assessment.status,
            assessment.submitted_at,
            snapshot_row.question_snapshot,
            response.answer_payload,
            response.is_correct,
            response.points_awarded,
        )
        assert after == before


def test_t10_failed_transaction_leaves_no_partial_evidence(database) -> None:
    factory, seed = database
    payload = evidence_payload(seed)
    with factory() as session:
        repository = LearningEvidenceRepository(session)
        with pytest.raises(IntegrityError), session.begin():
            repository.create(LearningEvidence(**payload.model_dump()))
            repository.create(LearningEvidence(**payload.model_dump()))
    with factory() as session:
        assert LearningEvidenceRepository(session).list_by_course_and_user(seed.course_id, seed.owner_id) == []


def test_t11_schema_version_participates_in_evidence_identity(database) -> None:
    factory, seed = database
    with factory() as session:
        LearningEvidenceService(session).create(evidence_payload(seed, evidence_schema_version="learning_evidence_v1"))
        LearningEvidenceService(session).create(evidence_payload(seed, evidence_schema_version="learning_evidence_v2"))
        versions = {
            row.evidence_schema_version
            for row in LearningEvidenceRepository(session).list_by_course_and_user(seed.course_id, seed.owner_id)
        }
        assert versions == {"learning_evidence_v1", "learning_evidence_v2"}


def test_t12_empty_queries_are_read_only(database) -> None:
    factory, seed = database
    with factory() as session:
        repository = LearningEvidenceRepository(session)
        assert repository.get_by_id(999_999) is None
        assert repository.list_by_source(EvidenceSourceType.DIAGNOSTIC, seed.assessment_id) == []
        assert repository.list_by_course_and_user(seed.course_id, seed.owner_id) == []
        assert session.scalar(select(LearningEvidence).limit(1)) is None
