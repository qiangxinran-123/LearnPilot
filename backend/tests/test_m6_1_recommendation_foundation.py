from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.models import (
    Assessment,
    AssessmentQuestion,
    Course,
    KnowledgeEdge,
    KnowledgeNode,
    LearningEvidence,
    Response,
    User,
)
from backend.app.models import (
    AssessmentStatus,
    AssessmentType,
    CandidateEligibilityStatus,
    CandidateExclusionReason,
    ConfidenceLevel,
    ConfidenceReasonCode,
    DataAvailability,
    EvidenceSourceType,
    KnowledgeDifficulty,
    KnowledgeImportance,
    KnowledgeRelationType,
    LearningPlanLevel,
    MasteryStatus,
    PrerequisiteEvaluationStatus,
    QuestionDifficulty,
    RecommendationAvailabilityStatus,
)
from backend.app.schemas.mastery_api import KnowledgeStateAvailability
from backend.app.schemas.recommendation import (
    CandidateNode,
    PriorityBreakdown,
    RecommendationKnowledgeNode,
    RecommendationMasteryState,
    RecommendationResult,
)
from backend.app.services.mastery_service import MasteryService
from backend.app.services.recommendation_context_service import (
    RecommendationContextError,
    RecommendationContextService,
    classify_candidate,
    prepare_prerequisite_edges,
)


@dataclass(frozen=True)
class Seed:
    owner_id: int
    other_owner_id: int
    course_id: int
    other_course_id: int
    node_ids: tuple[int, int, int, int]
    other_node_id: int


def _migrate(path: Path) -> str:
    database_url = f"sqlite+pysqlite:///{path}"
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


def _node(course_id: int, name: str) -> KnowledgeNode:
    return KnowledgeNode(
        course_id=course_id,
        name=name,
        normalized_name=name.casefold(),
        description="",
        importance=KnowledgeImportance.MEDIUM,
        difficulty=KnowledgeDifficulty.INTERMEDIATE,
        is_active=True,
        managed_by_canonicalization=True,
    )


@pytest.fixture
def database(tmp_path: Path):
    engine = create_engine(
        _migrate(tmp_path / "m6_1.sqlite3"),
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session, session.begin():
        owner = User(email="m6-owner@example.test", display_name="M6 Owner", is_active=True)
        other_owner = User(email="m6-other@example.test", display_name="Other", is_active=True)
        session.add_all([owner, other_owner])
        session.flush()
        course = Course(owner_id=owner.id, name="Recommendation course", description="")
        other_course = Course(owner_id=other_owner.id, name="Private course", description="")
        session.add_all([course, other_course])
        session.flush()
        nodes = [_node(course.id, name) for name in ("A", "B", "C", "D")]
        other_node = _node(other_course.id, "Private node")
        session.add_all([*nodes, other_node])
        session.flush()
        session.add_all(
            [
                KnowledgeEdge(
                    course_id=course.id,
                    source_node_id=nodes[0].id,
                    target_node_id=nodes[1].id,
                    relation_type=KnowledgeRelationType.PREREQUISITE,
                ),
                KnowledgeEdge(
                    course_id=course.id,
                    source_node_id=nodes[0].id,
                    target_node_id=nodes[2].id,
                    relation_type=KnowledgeRelationType.CONTAINS,
                ),
            ]
        )
        seed = Seed(
            owner_id=owner.id,
            other_owner_id=other_owner.id,
            course_id=course.id,
            other_course_id=other_course.id,
            node_ids=tuple(node.id for node in nodes),
            other_node_id=other_node.id,
        )
    yield factory, seed, engine
    engine.dispose()


def _add_evidence(
    session: Session,
    seed: Seed,
    *,
    node_id: int,
    score: str,
    offset: int,
) -> LearningEvidence:
    occurred_at = datetime(2026, 10, 21, 1, tzinfo=timezone.utc) + timedelta(minutes=offset)
    assessment = Assessment(
        course_id=seed.course_id,
        owner_id=seed.owner_id,
        assessment_type=AssessmentType.INITIAL_DIAGNOSTIC,
        status=AssessmentStatus.SUBMITTED,
        submitted_at=occurred_at,
    )
    session.add(assessment)
    session.flush()
    question = AssessmentQuestion(
        assessment_id=assessment.id,
        question_id=None,
        order_index=0,
        question_snapshot={"kind": "m6-test"},
    )
    session.add(question)
    session.flush()
    response = Response(
        assessment_id=assessment.id,
        assessment_question_id=question.id,
        answer_payload={"selected_options": ["A"]},
        answered_at=occurred_at,
        submitted_at=occurred_at,
        is_correct=Decimal(score) == Decimal("1"),
        points_awarded=Decimal(score),
    )
    session.add(response)
    session.flush()
    evidence = LearningEvidence(
        user_id=seed.owner_id,
        course_id=seed.course_id,
        source_type=EvidenceSourceType.DIAGNOSTIC,
        source_assessment_id=assessment.id,
        source_question_snapshot_id=question.id,
        source_response_id=response.id,
        historical_knowledge_node_ref=node_id,
        current_knowledge_node_id=node_id,
        knowledge_model_version="knowledge_v1",
        normalized_score=Decimal(score),
        difficulty=QuestionDifficulty.EASY if offset % 2 else QuestionDifficulty.HARD,
        attribution_weight=Decimal("1"),
        source_scoring_version="objective_exact_match_v1",
        evidence_schema_version="learning_evidence_v1",
        occurred_at=occurred_at,
    )
    session.add(evidence)
    session.flush()
    return evidence


def _state(
    node_id: int,
    *,
    score: Decimal | None,
    mastery: MasteryStatus,
    confidence: ConfidenceLevel,
    availability: KnowledgeStateAvailability = KnowledgeStateAvailability.CALCULATED,
) -> RecommendationMasteryState:
    return RecommendationMasteryState(
        knowledge_node_id=node_id,
        mastery_score=score,
        mastery_status=mastery,
        confidence_level=confidence,
        confidence_reason_codes=[ConfidenceReasonCode.SUFFICIENT_EVIDENCE],
        evidence_count=6,
        independent_evidence_count=6,
        assessment_count=6,
        calculation_state=availability,
    )


def test_context_is_owned_course_scoped_and_only_uses_prerequisites(database) -> None:
    factory, seed, _engine = database
    with factory() as session:
        context = RecommendationContextService(session).build_recommendation_context(
            user_id=seed.owner_id,
            course_id=seed.course_id,
        )
        assert {node.knowledge_node_id for node in context.knowledge_nodes} == set(seed.node_ids)
        assert seed.other_node_id not in {node.knowledge_node_id for node in context.knowledge_nodes}
        assert [(edge.source_node_id, edge.target_node_id) for edge in context.prerequisite_edges] == [
            (seed.node_ids[0], seed.node_ids[1])
        ]
        assert context.candidates[1].prerequisite_ids == [seed.node_ids[0]]
        assert context.needs_initial_diagnostic is True
        assert context.knowledge_importance_availability == DataAvailability.AVAILABLE
        assert context.course_importance_availability == DataAvailability.UNAVAILABLE
        assert context.review_risk_availability == DataAvailability.UNAVAILABLE
        assert all(item.mastery_score is None for item in context.mastery_states)
        assert all(item.eligibility_status == CandidateEligibilityStatus.UNASSESSED for item in context.candidates)

        with pytest.raises(RecommendationContextError) as private_error:
            RecommendationContextService(session).build_recommendation_context(
                user_id=seed.owner_id,
                course_id=seed.other_course_id,
            )
        assert private_error.value.code == "COURSE_NOT_FOUND"
        with pytest.raises(RecommendationContextError) as missing_error:
            RecommendationContextService(session).build_recommendation_context(
                user_id=seed.owner_id,
                course_id=999_999,
            )
        assert missing_error.value.code == "COURSE_NOT_FOUND"


def test_context_reads_verified_mastery_and_keeps_missing_distinct_from_zero(database) -> None:
    factory, seed, _engine = database
    mastered, low_confidence, unassessed, eligible = seed.node_ids
    with factory() as session, session.begin():
        for offset in range(6):
            _add_evidence(session, seed, node_id=mastered, score="1", offset=offset)
        for offset, score in enumerate(("1", "0", "0"), start=10):
            _add_evidence(session, seed, node_id=low_confidence, score=score, offset=offset)
        for offset, score in enumerate(("1", "0", "1", "0", "1", "0"), start=20):
            _add_evidence(session, seed, node_id=eligible, score=score, offset=offset)
    for node_id in (mastered, low_confidence, eligible):
        with factory() as session:
            MasteryService(session).refresh_state(
                user_id=seed.owner_id,
                course_id=seed.course_id,
                knowledge_node_id=node_id,
            )

    with factory() as session:
        context = RecommendationContextService(session).build_recommendation_context(
            user_id=seed.owner_id,
            course_id=seed.course_id,
        )
        states = {item.knowledge_node_id: item for item in context.mastery_states}
        candidates = {item.knowledge_node_id: item for item in context.candidates}
        assert states[mastered].mastery_status == MasteryStatus.GOOD_PERFORMANCE
        assert candidates[mastered].eligibility_status == CandidateEligibilityStatus.MASTERED
        assert candidates[low_confidence].eligibility_status == CandidateEligibilityStatus.LOW_CONFIDENCE
        assert states[unassessed].mastery_score is None
        assert states[unassessed].calculation_state == KnowledgeStateAvailability.NOT_CALCULATED
        assert candidates[unassessed].eligibility_status == CandidateEligibilityStatus.UNASSESSED
        assert candidates[eligible].eligibility_status == CandidateEligibilityStatus.ELIGIBLE
        assert context.needs_initial_diagnostic is False
        assert context.latest_valid_assessment_at is not None


def test_context_assembly_is_repeatable_and_emits_no_writes(database) -> None:
    factory, seed, engine = database
    with factory() as session:
        writes: list[str] = []

        @event.listens_for(engine, "before_cursor_execute")
        def track_writes(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
            if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                writes.append(statement)

        service = RecommendationContextService(session)
        first = service.build_recommendation_context(user_id=seed.owner_id, course_id=seed.course_id)
        second = service.build_recommendation_context(user_id=seed.owner_id, course_id=seed.course_id)
        event.remove(engine, "before_cursor_execute", track_writes)
        assert first == second
        assert writes == []


def test_course_without_active_nodes_has_explicit_error(database) -> None:
    factory, seed, _engine = database
    with factory() as session, session.begin():
        empty_course = Course(owner_id=seed.owner_id, name="Empty", description="")
        session.add(empty_course)
        session.flush()
        empty_course_id = empty_course.id
    with factory() as session, pytest.raises(RecommendationContextError) as captured:
        RecommendationContextService(session).build_recommendation_context(
            user_id=seed.owner_id,
            course_id=empty_course_id,
        )
    assert captured.value.code == "KNOWLEDGE_MODEL_NOT_FOUND"


def test_candidate_rules_keep_mastery_and_confidence_semantics_separate() -> None:
    node = RecommendationKnowledgeNode(
        knowledge_node_id=1,
        course_id=7,
        name="Vectors",
        importance=KnowledgeImportance.HIGH,
        difficulty=KnowledgeDifficulty.INTERMEDIATE,
    )
    low = classify_candidate(
        course_id=7,
        node=node,
        state=_state(
            1,
            score=Decimal("85"),
            mastery=MasteryStatus.GOOD_PERFORMANCE,
            confidence=ConfidenceLevel.LOW,
        ),
        prerequisite_ids=[],
    )
    assert low.mastery_state == MasteryStatus.GOOD_PERFORMANCE
    assert low.eligibility_status == CandidateEligibilityStatus.LOW_CONFIDENCE
    mastered = classify_candidate(
        course_id=7,
        node=node,
        state=_state(
            1,
            score=Decimal("85"),
            mastery=MasteryStatus.GOOD_PERFORMANCE,
            confidence=ConfidenceLevel.MEDIUM,
        ),
        prerequisite_ids=[],
    )
    assert mastered.eligibility_status == CandidateEligibilityStatus.MASTERED
    assert mastered.exclusion_reason == CandidateExclusionReason.ALREADY_MASTERED


def test_prerequisite_filtering_deduplication_and_direction() -> None:
    edges = [
        KnowledgeEdge(
            course_id=7,
            source_node_id=1,
            target_node_id=2,
            relation_type=KnowledgeRelationType.PREREQUISITE,
        ),
        KnowledgeEdge(
            course_id=7,
            source_node_id=1,
            target_node_id=2,
            relation_type=KnowledgeRelationType.PREREQUISITE,
        ),
        KnowledgeEdge(
            course_id=7,
            source_node_id=2,
            target_node_id=3,
            relation_type=KnowledgeRelationType.CONTAINS,
        ),
    ]
    prepared = prepare_prerequisite_edges(course_id=7, node_ids={1, 2, 3}, edges=edges)
    assert [(edge.source_node_id, edge.target_node_id) for edge in prepared] == [(1, 2)]


@pytest.mark.parametrize(
    ("edge", "code"),
    [
        (
            KnowledgeEdge(
                course_id=7,
                source_node_id=1,
                target_node_id=1,
                relation_type=KnowledgeRelationType.PREREQUISITE,
            ),
            "INVALID_PREREQUISITE_EDGE",
        ),
        (
            KnowledgeEdge(
                course_id=7,
                source_node_id=1,
                target_node_id=99,
                relation_type=KnowledgeRelationType.PREREQUISITE,
            ),
            "INVALID_PREREQUISITE_EDGE",
        ),
        (
            KnowledgeEdge(
                course_id=8,
                source_node_id=1,
                target_node_id=2,
                relation_type=KnowledgeRelationType.PREREQUISITE,
            ),
            "INVALID_PREREQUISITE_EDGE",
        ),
    ],
)
def test_invalid_prerequisite_edges_are_reported(edge: KnowledgeEdge, code: str) -> None:
    with pytest.raises(RecommendationContextError) as captured:
        prepare_prerequisite_edges(course_id=7, node_ids={1, 2}, edges=[edge])
    assert captured.value.code == code
    assert captured.value.details


def test_prerequisite_cycle_is_rejected_without_recursive_search() -> None:
    edges = [
        KnowledgeEdge(
            course_id=7,
            source_node_id=1,
            target_node_id=2,
            relation_type=KnowledgeRelationType.PREREQUISITE,
        ),
        KnowledgeEdge(
            course_id=7,
            source_node_id=2,
            target_node_id=1,
            relation_type=KnowledgeRelationType.PREREQUISITE,
        ),
    ]
    with pytest.raises(RecommendationContextError) as captured:
        prepare_prerequisite_edges(course_id=7, node_ids={1, 2}, edges=edges)
    assert captured.value.code == "KNOWLEDGE_PREREQUISITE_CYCLE"


def test_contracts_validate_statuses_and_leave_priority_uncomputed() -> None:
    breakdown = PriorityBreakdown()
    assert all(value is None for value in breakdown.model_dump().values())
    with pytest.raises(ValidationError):
        CandidateNode(
            knowledge_node_id=1,
            course_id=7,
            mastery_state=MasteryStatus.NOT_ASSESSED,
            mastery_score=None,
            confidence_state=ConfidenceLevel.INSUFFICIENT,
            eligibility_status=CandidateEligibilityStatus.UNASSESSED,
            exclusion_reason=None,
        )
    result = RecommendationResult(
        user_id=1,
        course_id=7,
        recommended_node_id=2,
        priority_breakdown=PriorityBreakdown(
            knowledge_gap=Decimal("0.8"),
            dependency_importance=Decimal("0.2"),
            course_importance=Decimal("0.5"),
            review_risk=Decimal("0.5"),
            total_priority=Decimal("1.0"),
        ),
        reason_codes=["knowledge_gap"],
        prerequisite_status=PrerequisiteEvaluationStatus.NOT_EVALUATED,
        availability_status=RecommendationAvailabilityStatus.AVAILABLE,
        plan_level=LearningPlanLevel.PERSONALIZED,
    )
    assert result.priority_breakdown.review_risk == Decimal("0.5")
