from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Generator
from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.models import (
    Assessment,
    AssessmentQuestion,
    Course,
    KnowledgeNode,
    LearningEvidence,
    Response,
    StudentKnowledgeState,
    User,
)
from backend.app.models import (
    AssessmentStatus,
    AssessmentType,
    ConfidenceLevel,
    ConfidenceReasonCode,
    EvidenceSourceType,
    KnowledgeDifficulty,
    KnowledgeImportance,
    MasteryStatus,
    QuestionDifficulty,
)
from backend.app.schemas.mastery import MasteryEvidenceSchema
from backend.app.services.confidence_estimator import ConfidenceEstimator
from backend.app.services.evidence_fingerprint import calculate_evidence_fingerprint
from backend.app.services.mastery_calculator import MasteryCalculationError, MasteryCalculator
from backend.app.services.mastery_config import MASTERY_V1_CONFIG
from backend.app.services.mastery_service import MasteryService, MasteryServiceError

_USE_HISTORICAL_NODE = object()


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


def mastery_evidence(
    index: int,
    score: str | Decimal,
    *,
    assessment_id: int | None = None,
    difficulty: QuestionDifficulty = QuestionDifficulty.EASY,
    attribution_weight: str | Decimal = "1",
    version: str | None = "knowledge_v1",
) -> MasteryEvidenceSchema:
    return MasteryEvidenceSchema(
        user_id=1,
        course_id=1,
        source_type=EvidenceSourceType.DIAGNOSTIC,
        source_assessment_id=assessment_id or index,
        source_question_snapshot_id=index,
        source_response_id=index,
        historical_knowledge_node_ref=101,
        current_knowledge_node_id=101,
        knowledge_model_version=version,
        normalized_score=Decimal(score),
        difficulty=difficulty,
        attribution_weight=Decimal(attribution_weight),
        evidence_schema_version="learning_evidence_v1",
    )


@dataclass(frozen=True)
class Seed:
    owner_id: int
    other_owner_id: int
    course_id: int
    other_course_id: int
    node_id: int
    other_node_id: int


@pytest.fixture
def database(tmp_path: Path) -> Generator[tuple[sessionmaker[Session], Seed], None, None]:
    database_url = migrate_database(tmp_path / "m5c.sqlite3")
    engine = make_engine(database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session, session.begin():
        owner = User(email="m5c-owner@example.test", display_name="M5C Owner", is_active=True)
        other_owner = User(email="m5c-other@example.test", display_name="M5C Other", is_active=True)
        session.add_all([owner, other_owner])
        session.flush()
        course = Course(owner_id=owner.id, name="Mastery Course", description="")
        other_course = Course(owner_id=other_owner.id, name="Other Mastery Course", description="")
        session.add_all([course, other_course])
        session.flush()
        node = KnowledgeNode(
            id=101,
            course_id=course.id,
            name="Current Node",
            normalized_name="current node",
            description="",
            importance=KnowledgeImportance.HIGH,
            difficulty=KnowledgeDifficulty.INTERMEDIATE,
            is_active=True,
            managed_by_canonicalization=True,
        )
        other_node = KnowledgeNode(
            id=202,
            course_id=other_course.id,
            name="Other Node",
            normalized_name="other node",
            description="",
            importance=KnowledgeImportance.MEDIUM,
            difficulty=KnowledgeDifficulty.INTERMEDIATE,
            is_active=True,
            managed_by_canonicalization=True,
        )
        session.add_all([node, other_node])
        seed = Seed(owner.id, other_owner.id, course.id, other_course.id, node.id, other_node.id)
    yield factory, seed
    engine.dispose()


def add_assessment(session: Session, *, owner_id: int, course_id: int, offset: int = 0) -> Assessment:
    occurred_at = datetime(2026, 10, 20, 8, 0, tzinfo=timezone.utc) + timedelta(hours=offset)
    assessment = Assessment(
        course_id=course_id,
        owner_id=owner_id,
        assessment_type=AssessmentType.INITIAL_DIAGNOSTIC,
        status=AssessmentStatus.SUBMITTED,
        started_at=occurred_at,
        submitted_at=occurred_at,
        report_policy_version="diagnostic_node_performance_v1",
    )
    session.add(assessment)
    session.flush()
    return assessment


def add_database_evidence(
    session: Session,
    seed: Seed,
    *,
    score: str | Decimal,
    assessment: Assessment | None = None,
    difficulty: QuestionDifficulty = QuestionDifficulty.EASY,
    attribution_weight: str | Decimal = "1",
    version: str | None = "knowledge_v1",
    current_node_id: int | None | object = _USE_HISTORICAL_NODE,
    owner_id: int | None = None,
    course_id: int | None = None,
    node_id: int | None = None,
) -> LearningEvidence:
    actual_owner_id = owner_id or seed.owner_id
    actual_course_id = course_id or seed.course_id
    actual_node_id = node_id or seed.node_id
    if assessment is None:
        assessment = add_assessment(session, owner_id=actual_owner_id, course_id=actual_course_id)
    order_index = len(assessment.questions)
    occurred_at = assessment.submitted_at
    question = AssessmentQuestion(
        assessment_id=assessment.id,
        question_id=None,
        order_index=order_index,
        question_snapshot={"immutable": f"snapshot-{assessment.id}-{order_index}"},
    )
    session.add(question)
    session.flush()
    response = Response(
        assessment_id=assessment.id,
        assessment_question_id=question.id,
        answer_payload={"selected": ["A"]},
        answered_at=occurred_at,
        submitted_at=occurred_at,
        is_correct=Decimal(score) == Decimal("1"),
        points_awarded=Decimal(score),
    )
    session.add(response)
    session.flush()
    evidence = LearningEvidence(
        user_id=actual_owner_id,
        course_id=actual_course_id,
        source_type=EvidenceSourceType.DIAGNOSTIC,
        source_assessment_id=assessment.id,
        source_question_snapshot_id=question.id,
        source_response_id=response.id,
        historical_knowledge_node_ref=actual_node_id,
        current_knowledge_node_id=(actual_node_id if current_node_id is _USE_HISTORICAL_NODE else current_node_id),
        knowledge_model_version=version,
        normalized_score=Decimal(score),
        difficulty=difficulty,
        attribution_weight=Decimal(attribution_weight),
        source_scoring_version="objective_exact_match_v1",
        evidence_schema_version="learning_evidence_v1",
        occurred_at=occurred_at,
    )
    session.add(evidence)
    session.flush()
    return evidence


def test_t01_no_evidence_is_not_assessed_and_insufficient() -> None:
    mastery = MasteryCalculator().calculate([])
    confidence = ConfidenceEstimator().estimate([])
    assert mastery.mastery_score is None
    assert mastery.mastery_status == MasteryStatus.NOT_ASSESSED
    assert confidence.confidence_level == ConfidenceLevel.INSUFFICIENT


def test_t02_one_correct_evidence_does_not_publish_mastery() -> None:
    item = mastery_evidence(1, "1")
    result = MasteryCalculator().calculate([item])
    confidence = ConfidenceEstimator().estimate([item])
    assert result.mastery_score is None
    assert confidence.confidence_level == ConfidenceLevel.INSUFFICIENT


def test_t03_two_evidence_remain_insufficient() -> None:
    items = [mastery_evidence(1, "1"), mastery_evidence(2, "0")]
    assert MasteryCalculator().calculate(items).mastery_score is None
    assert ConfidenceEstimator().estimate(items).confidence_level == ConfidenceLevel.INSUFFICIENT


def test_t04_three_correct_evidence_publish_smoothed_mastery_with_low_confidence() -> None:
    items = [mastery_evidence(index, "1") for index in range(1, 4)]
    mastery = MasteryCalculator().calculate(items)
    confidence = ConfidenceEstimator().estimate(items)
    assert mastery.mastery_score == Decimal("80.00")
    assert mastery.mastery_status == MasteryStatus.GOOD_PERFORMANCE
    assert confidence.confidence_level == ConfidenceLevel.LOW


def test_t05_eight_of_ten_is_prior_smoothed_not_raw_eighty_percent() -> None:
    items = [mastery_evidence(index, "1" if index <= 8 else "0") for index in range(1, 11)]
    result = MasteryCalculator().calculate(items)
    assert result.mastery_score == Decimal("75.00")
    assert result.mastery_score != Decimal("80")


def test_t06_difficulty_weights_are_applied_once() -> None:
    items = [
        mastery_evidence(1, "0", difficulty=QuestionDifficulty.EASY),
        mastery_evidence(2, "1", difficulty=QuestionDifficulty.MEDIUM),
        mastery_evidence(3, "1", difficulty=QuestionDifficulty.HARD),
    ]
    assert MasteryCalculator().calculate(items).mastery_score == Decimal("64.29")


def test_t07_existing_multi_node_attribution_weight_is_not_reapplied() -> None:
    items = [mastery_evidence(index, "1", attribution_weight="0.5") for index in range(1, 4)]
    assert MasteryCalculator().calculate(items).mastery_score == Decimal("71.43")


def test_t08_many_questions_from_one_assessment_cannot_reach_high_confidence() -> None:
    items = [mastery_evidence(index, "0.8", assessment_id=1) for index in range(1, 11)]
    result = ConfidenceEstimator().estimate(items)
    assert result.confidence_level == ConfidenceLevel.MEDIUM
    assert ConfidenceReasonCode.SINGLE_ASSESSMENT in result.confidence_reason_codes


def test_t09_independent_assessments_and_difficulty_coverage_can_reach_high_confidence() -> None:
    items = [
        mastery_evidence(
            index,
            "0.8",
            assessment_id=1 if index <= 5 else 2,
            difficulty=QuestionDifficulty.EASY if index % 2 else QuestionDifficulty.HARD,
        )
        for index in range(1, 11)
    ]
    assert ConfidenceEstimator().estimate(items).confidence_level == ConfidenceLevel.HIGH


def test_t10_conflicting_assessment_performance_caps_confidence() -> None:
    items = [
        mastery_evidence(
            index,
            "1" if index <= 5 else "0",
            assessment_id=1 if index <= 5 else 2,
            difficulty=QuestionDifficulty.EASY if index % 2 else QuestionDifficulty.HARD,
        )
        for index in range(1, 11)
    ]
    result = ConfidenceEstimator().estimate(items)
    assert result.confidence_level == ConfidenceLevel.MEDIUM
    assert ConfidenceReasonCode.PERFORMANCE_VARIATION in result.confidence_reason_codes


def test_t11_exact_duplicate_evidence_does_not_change_result_or_counts() -> None:
    items = [mastery_evidence(index, "1") for index in range(1, 4)]
    original = MasteryCalculator().calculate(items)
    duplicated = MasteryCalculator().calculate([*items, items[0]])
    assert duplicated == original


def test_t12_evidence_order_and_decimal_scale_do_not_change_fingerprint() -> None:
    calculator = MasteryCalculator()
    first = [mastery_evidence(1, Decimal("1.0")), mastery_evidence(2, Decimal("0.50"))]
    second = [mastery_evidence(2, Decimal("0.50000")), mastery_evidence(1, Decimal("1.00000"))]
    assert calculate_evidence_fingerprint(calculator.prepare(first), calculator) == calculate_evidence_fingerprint(
        calculator.prepare(second), calculator
    )


def test_t13_identical_refresh_does_not_rewrite_current_state(database) -> None:
    factory, seed = database
    with factory() as session, session.begin():
        for score in ("1", "1", "0"):
            add_database_evidence(session, seed, score=score)
    first_time = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
    with factory() as session:
        service = MasteryService(session, clock=lambda: first_time)
        first = service.refresh_state(user_id=seed.owner_id, course_id=seed.course_id, knowledge_node_id=seed.node_id)
        second = service.refresh_state(user_id=seed.owner_id, course_id=seed.course_id, knowledge_node_id=seed.node_id)
        assert first.updated is True
        assert second.updated is False
        assert first.state.id == second.state.id
        assert second.state.calculated_at == first.state.calculated_at


def test_t14_new_evidence_changes_fingerprint_and_recalculates(database) -> None:
    factory, seed = database
    with factory() as session, session.begin():
        for score in ("1", "0", "1"):
            add_database_evidence(session, seed, score=score)
    times = iter(
        [
            datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc),
            datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc),
        ]
    )
    with factory() as session:
        service = MasteryService(session, clock=lambda: next(times))
        first = service.refresh_state(user_id=seed.owner_id, course_id=seed.course_id, knowledge_node_id=seed.node_id)
        with session.begin():
            add_database_evidence(session, seed, score="1")
        second = service.refresh_state(user_id=seed.owner_id, course_id=seed.course_id, knowledge_node_id=seed.node_id)
        assert second.updated is True
        assert second.state.id == first.state.id
        assert second.state.evidence_fingerprint != first.state.evidence_fingerprint
        assert second.state.calculated_at > first.state.calculated_at


def test_t15_algorithm_version_change_updates_state_without_changing_evidence(database) -> None:
    factory, seed = database
    with factory() as session, session.begin():
        for score in ("1", "1", "0"):
            add_database_evidence(session, seed, score=score)
    with factory() as session:
        first = MasteryService(session).refresh_state(
            user_id=seed.owner_id, course_id=seed.course_id, knowledge_node_id=seed.node_id
        )
        evidence_before = list(session.scalars(select(LearningEvidence.normalized_score).order_by(LearningEvidence.id)))
    with factory() as session:
        config_v2 = replace(MASTERY_V1_CONFIG, algorithm_version="mastery_v2")
        second = MasteryService(session, config=config_v2).refresh_state(
            user_id=seed.owner_id, course_id=seed.course_id, knowledge_node_id=seed.node_id
        )
        evidence_after = list(session.scalars(select(LearningEvidence.normalized_score).order_by(LearningEvidence.id)))
        assert second.updated is True
        assert second.state.id == first.state.id
        assert second.state.algorithm_version == "mastery_v2"
        assert second.state.evidence_fingerprint == first.state.evidence_fingerprint
        assert evidence_after == evidence_before


def test_t16_unmapped_history_is_excluded_and_mixed_versions_are_rejected(database) -> None:
    factory, seed = database
    with factory() as session, session.begin():
        add_database_evidence(session, seed, score="1", current_node_id=None, node_id=303)
    with factory() as session:
        empty = MasteryService(session).refresh_state(
            user_id=seed.owner_id, course_id=seed.course_id, knowledge_node_id=seed.node_id
        )
        assert empty.state.evidence_count == 0
        assert empty.state.mastery_score is None
        with session.begin():
            add_database_evidence(session, seed, score="1", version="knowledge_v1")
            add_database_evidence(session, seed, score="1", version="knowledge_v2")
        with pytest.raises(MasteryServiceError) as captured:
            MasteryService(session).refresh_state(
                user_id=seed.owner_id,
                course_id=seed.course_id,
                knowledge_node_id=seed.node_id,
            )
        assert captured.value.code == "INCOMPATIBLE_KNOWLEDGE_MODEL_VERSIONS"


def test_t17_user_and_course_evidence_are_isolated(database) -> None:
    factory, seed = database
    with factory() as session, session.begin():
        add_database_evidence(session, seed, score="1")
        add_database_evidence(
            session,
            seed,
            score="0",
            owner_id=seed.other_owner_id,
            course_id=seed.other_course_id,
            node_id=seed.other_node_id,
            current_node_id=seed.other_node_id,
        )
    with factory() as session:
        own = MasteryService(session).refresh_state(
            user_id=seed.owner_id, course_id=seed.course_id, knowledge_node_id=seed.node_id
        )
        assert own.state.evidence_count == 1
        with pytest.raises(MasteryServiceError) as captured:
            MasteryService(session).refresh_state(
                user_id=seed.owner_id,
                course_id=seed.other_course_id,
                knowledge_node_id=seed.other_node_id,
            )
        assert captured.value.code == "TARGET_OWNERSHIP_MISMATCH"


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"normalized_score": Decimal("1.1")}, "INVALID_NORMALIZED_SCORE"),
        ({"attribution_weight": Decimal("0")}, "INVALID_ATTRIBUTION_WEIGHT"),
        ({"difficulty": "unsupported"}, "UNSUPPORTED_DIFFICULTY"),
    ],
)
def test_t18_invalid_calculation_inputs_are_explicitly_rejected(changes: dict[str, object], code: str) -> None:
    values = mastery_evidence(1, "1").model_dump()
    values.update(changes)
    invalid = MasteryEvidenceSchema.model_construct(**values)
    with pytest.raises(MasteryCalculationError) as captured:
        MasteryCalculator().calculate([invalid])
    assert captured.value.code == code


def test_t19_state_write_failure_rolls_back_without_damaging_evidence(database, monkeypatch) -> None:
    factory, seed = database
    with factory() as session, session.begin():
        for score in ("1", "0", "1"):
            add_database_evidence(session, seed, score=score)
    with factory() as session:
        evidence_ids = list(session.scalars(select(LearningEvidence.id).order_by(LearningEvidence.id)))
        session.rollback()
        service = MasteryService(session)

        def fail_save(_state) -> None:
            raise RuntimeError("simulated state persistence failure")

        monkeypatch.setattr(service.state_repository, "save", fail_save)
        with pytest.raises(MasteryServiceError) as captured:
            service.refresh_state(user_id=seed.owner_id, course_id=seed.course_id, knowledge_node_id=seed.node_id)
        assert captured.value.code == "STATE_PERSISTENCE_FAILED"
    with factory() as session:
        assert session.scalar(select(StudentKnowledgeState)) is None
        assert list(session.scalars(select(LearningEvidence.id).order_by(LearningEvidence.id))) == evidence_ids


def test_t20_mastery_refresh_never_mutates_m4_records(database) -> None:
    factory, seed = database
    with factory() as session, session.begin():
        evidence = add_database_evidence(session, seed, score="1")
        assessment_id = evidence.source_assessment_id
        question_id = evidence.source_question_snapshot_id
        response_id = evidence.source_response_id
    with factory() as session:
        assessment = session.get(Assessment, assessment_id)
        question = session.get(AssessmentQuestion, question_id)
        response = session.get(Response, response_id)
        before = (
            assessment.status,
            assessment.submitted_at,
            deepcopy(question.question_snapshot),
            deepcopy(response.answer_payload),
            response.points_awarded,
            response.is_correct,
        )
        session.rollback()
        MasteryService(session).refresh_state(
            user_id=seed.owner_id, course_id=seed.course_id, knowledge_node_id=seed.node_id
        )
        session.expire_all()
        assessment = session.get(Assessment, assessment_id)
        question = session.get(AssessmentQuestion, question_id)
        response = session.get(Response, response_id)
        assert (
            assessment.status,
            assessment.submitted_at,
            question.question_snapshot,
            response.answer_payload,
            response.points_awarded,
            response.is_correct,
        ) == before


def test_m5c_migration_creates_state_table_and_constraints(tmp_path: Path) -> None:
    database_url = migrate_database(tmp_path / "migration.sqlite3", "0011_m5b_evidence_mapping")
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=environment,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    engine = make_engine(database_url)
    inspector = inspect(engine)
    assert "student_knowledge_states" in inspector.get_table_names()
    unique_constraints = inspector.get_unique_constraints("student_knowledge_states")
    assert any(item["name"] == "uq_student_knowledge_state_identity" for item in unique_constraints)
    foreign_keys = inspector.get_foreign_keys("student_knowledge_states")
    assert any(item["name"] == "fk_student_knowledge_state_course_node" for item in foreign_keys)
    engine.dispose()


def test_state_identity_unique_constraint_is_database_enforced(database) -> None:
    factory, seed = database
    values = {
        "user_id": seed.owner_id,
        "course_id": seed.course_id,
        "knowledge_node_id": seed.node_id,
        "knowledge_model_version": None,
        "mastery_score": None,
        "mastery_status": MasteryStatus.NOT_ASSESSED,
        "confidence_level": ConfidenceLevel.INSUFFICIENT,
        "confidence_reason_codes": [ConfidenceReasonCode.INSUFFICIENT_EVIDENCE.value],
        "evidence_count": 0,
        "independent_evidence_count": 0,
        "assessment_count": 0,
        "algorithm_version": "mastery_v1",
        "evidence_fingerprint": "0" * 64,
        "calculated_at": datetime(2026, 10, 20, tzinfo=timezone.utc),
    }
    with factory() as session:
        with pytest.raises(IntegrityError), session.begin():
            session.add_all([StudentKnowledgeState(**values), StudentKnowledgeState(**values)])
