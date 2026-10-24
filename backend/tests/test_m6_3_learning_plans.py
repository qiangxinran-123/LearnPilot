from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from threading import Barrier

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.core.settings import Settings
from backend.app.db.models import (
    Assessment,
    AssessmentQuestion,
    Course,
    KnowledgeEdge,
    KnowledgeNode,
    LearningEvidence,
    LearningPlan,
    LearningTask,
    Response,
    StudentKnowledgeState,
    User,
)
from backend.app.models import (
    AssessmentStatus,
    AssessmentType,
    EvidenceSourceType,
    KnowledgeDifficulty,
    KnowledgeImportance,
    KnowledgeRelationType,
    LearningPlanAvailability,
    LearningPlanLevel,
    LearningPlanStatus,
    LearningTaskType,
    QuestionDifficulty,
    RecommendationAvailabilityStatus,
)
from backend.app.repositories import LearningPlanRepository
from backend.app.services.learning_plan_service import LearningPlanError, LearningPlanService
from backend.app.services.mastery_service import MasteryService
from backend.app.services.recommendation_engine import RecommendationEngine


@dataclass(frozen=True)
class Seed:
    owner_id: int
    other_owner_id: int
    course_id: int
    other_course_id: int
    node_ids: tuple[int, int, int]


def _migrate(path: Path) -> str:
    url = f"sqlite+pysqlite:///{path}"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = url
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=environment,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return url


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
    url = _migrate(tmp_path / "m6_3.sqlite3")
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 10})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record) -> None:
        connection.execute("PRAGMA foreign_keys=ON")

    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session, session.begin():
        owner = User(email="legacy-bootstrap@learnpilot.local", display_name="M6 Owner", is_active=True)
        other = User(email="other-m6@example.test", display_name="Other", is_active=True)
        session.add_all([owner, other])
        session.flush()
        course = Course(owner_id=owner.id, name="M6-3", description="")
        private_course = Course(owner_id=other.id, name="Private", description="")
        session.add_all([course, private_course])
        session.flush()
        nodes = [_node(course.id, name) for name in ("向量基础", "线性映射", "特征值")]
        session.add_all(nodes)
        session.flush()
        seed = Seed(owner.id, other.id, course.id, private_course.id, tuple(node.id for node in nodes))

    with factory() as session, session.begin():
        for offset in range(6):
            _add_evidence(session, seed, node_id=seed.node_ids[0], score="0", offset=offset)
            _add_evidence(session, seed, node_id=seed.node_ids[1], score="1", offset=100 + offset)
    with factory() as session:
        for node_id in seed.node_ids[:2]:
            MasteryService(session).refresh_state(
                user_id=seed.owner_id,
                course_id=seed.course_id,
                knowledge_node_id=node_id,
            )
    yield factory, seed, engine, url
    engine.dispose()


def _add_evidence(
    session: Session,
    seed: Seed,
    *,
    node_id: int,
    score: str,
    offset: int,
) -> LearningEvidence:
    occurred_at = datetime(2026, 10, 22, tzinfo=timezone.utc) + timedelta(minutes=offset)
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
        question_snapshot={"kind": "m6-3-test"},
    )
    session.add(question)
    session.flush()
    response = Response(
        assessment_id=assessment.id,
        assessment_question_id=question.id,
        answer_payload={"selected_options": ["A"]},
        answered_at=occurred_at,
        submitted_at=occurred_at,
        is_correct=score == "1",
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
        difficulty=QuestionDifficulty.MEDIUM,
        attribution_weight=Decimal("1"),
        source_scoring_version="objective_exact_match_v1",
        evidence_schema_version="learning_evidence_v1",
        occurred_at=occurred_at,
    )
    session.add(evidence)
    session.flush()
    return evidence


def _service(session: Session) -> LearningPlanService:
    return LearningPlanService(session, Settings(database_url="sqlite+pysqlite://"))


def test_plan_generation_persists_real_recommendation_and_ordered_templates(database) -> None:
    factory, seed, _engine, _url = database
    with factory() as session:
        before_mastery = session.scalar(select(func.count()).select_from(StudentKnowledgeState))
        before_evidence = session.scalar(select(func.count()).select_from(LearningEvidence))
        session.rollback()
        result = _service(session).generate(user_id=seed.owner_id, course_id=seed.course_id)

    assert result.availability == LearningPlanAvailability.AVAILABLE
    assert result.recommendation_status == RecommendationAvailabilityStatus.AVAILABLE
    assert result.plan_level == LearningPlanLevel.PERSONALIZED
    assert result.plan is not None
    assert result.plan.target_node_id == seed.node_ids[0]
    assert result.plan.priority_score == result.plan.priority_breakdown.total_priority
    assert len(result.plan.tasks) == 3
    assert [task.order_index for task in result.plan.tasks] == [0, 1, 2]
    assert [task.task_type for task in result.plan.tasks] == [
        LearningTaskType.CONCEPT_REVIEW,
        LearningTaskType.EXAMPLE_WALKTHROUGH,
        LearningTaskType.TARGETED_PRACTICE,
    ]
    assert all(task.knowledge_node_id == result.plan.target_node_id for task in result.plan.tasks)
    assert "知识" not in {code.value for code in result.plan.reason_codes}

    with factory() as session:
        stored = LearningPlanRepository(session).get_current(user_id=seed.owner_id, course_id=seed.course_id)
        assert stored is not None
        assert stored.id == result.plan.plan_id
        assert len(stored.tasks) == 3
        assert session.scalar(select(func.count()).select_from(StudentKnowledgeState)) == before_mastery
        assert session.scalar(select(func.count()).select_from(LearningEvidence)) == before_evidence


def test_same_input_reuses_plan_and_unrelated_course_change_does_not_invalidate(database) -> None:
    factory, seed, _engine, _url = database
    with factory() as session:
        first = _service(session).generate(user_id=seed.owner_id, course_id=seed.course_id)
        second = _service(session).generate(user_id=seed.owner_id, course_id=seed.course_id)
        assert first.plan is not None and second.plan is not None
        assert second.reused is True
        assert second.plan.plan_id == first.plan.plan_id
    with factory() as session, session.begin():
        course = session.get(Course, seed.course_id)
        assert course is not None
        course.description = "This field is not a recommendation input."
    with factory() as session:
        third = _service(session).generate(user_id=seed.owner_id, course_id=seed.course_id)
        assert third.reused is True
        assert third.plan is not None and third.plan.plan_id == first.plan.plan_id
        assert session.scalar(select(func.count()).select_from(LearningPlan)) == 1


def test_mastery_or_prerequisite_change_supersedes_current_plan(database) -> None:
    factory, seed, _engine, _url = database
    with factory() as session:
        first = _service(session).generate(user_id=seed.owner_id, course_id=seed.course_id)
        assert first.plan is not None
        first_id = first.plan.plan_id
    with factory() as session, session.begin():
        _add_evidence(session, seed, node_id=seed.node_ids[0], score="1", offset=300)
    with factory() as session:
        MasteryService(session).refresh_state(
            user_id=seed.owner_id,
            course_id=seed.course_id,
            knowledge_node_id=seed.node_ids[0],
        )
    with factory() as session:
        second = _service(session).generate(user_id=seed.owner_id, course_id=seed.course_id)
        assert second.plan is not None and second.plan.plan_id != first_id
        second_id = second.plan.plan_id
        old = session.get(LearningPlan, first_id)
        assert old is not None and old.status == LearningPlanStatus.SUPERSEDED
    with factory() as session, session.begin():
        session.add(
            KnowledgeEdge(
                course_id=seed.course_id,
                source_node_id=seed.node_ids[0],
                target_node_id=seed.node_ids[1],
                relation_type=KnowledgeRelationType.PREREQUISITE,
            )
        )
    with factory() as session:
        third = _service(session).generate(user_id=seed.owner_id, course_id=seed.course_id)
        assert third.plan is not None and third.plan.plan_id != second_id
        plans = list(session.scalars(select(LearningPlan).order_by(LearningPlan.id)))
        assert [plan.status for plan in plans] == [
            LearningPlanStatus.SUPERSEDED,
            LearningPlanStatus.SUPERSEDED,
            LearningPlanStatus.AVAILABLE,
        ]


def test_get_is_read_only_and_reports_stale_without_replacing_plan(database) -> None:
    factory, seed, engine, _url = database
    with factory() as session:
        generated = _service(session).generate(user_id=seed.owner_id, course_id=seed.course_id)
        assert generated.plan is not None
    with factory() as session, session.begin():
        node = session.get(KnowledgeNode, seed.node_ids[0])
        assert node is not None
        node.name = "向量空间基础"
    writes: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def track_writes(_conn, _cursor, statement, _parameters, _context, _executemany) -> None:
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            writes.append(statement)

    with factory() as session:
        result = _service(session).get_current(user_id=seed.owner_id, course_id=seed.course_id)
    event.remove(engine, "before_cursor_execute", track_writes)
    assert result.availability == LearningPlanAvailability.STALE
    assert result.plan is not None and result.plan.plan_id == generated.plan.plan_id
    assert writes == []


def test_foundational_plan_and_cross_owner_isolation(database) -> None:
    factory, seed, _engine, _url = database
    with factory() as session, session.begin():
        course = Course(owner_id=seed.owner_id, name="Foundation route", description="")
        session.add(course)
        session.flush()
        first = _node(course.id, "基础概念")
        second = _node(course.id, "后续概念")
        session.add_all([first, second])
        session.flush()
        session.add(
            KnowledgeEdge(
                course_id=course.id,
                source_node_id=first.id,
                target_node_id=second.id,
                relation_type=KnowledgeRelationType.PREREQUISITE,
            )
        )
        unassessed_course_id = course.id
    with factory() as session:
        result = _service(session).generate(user_id=seed.owner_id, course_id=unassessed_course_id)
        assert result.availability == LearningPlanAvailability.AVAILABLE
        assert result.plan_level == LearningPlanLevel.FOUNDATIONAL
        assert result.plan is not None
        assert result.plan.target_node_id == first.id
        assert len(result.plan.tasks) == 2
        assert session.scalar(select(func.count()).select_from(LearningEvidence)) == 12
        assert session.scalar(select(func.count()).select_from(StudentKnowledgeState)) == 2
        session.rollback()
        with pytest.raises(LearningPlanError) as captured:
            _service(session).generate(user_id=seed.other_owner_id, course_id=seed.course_id)
        assert captured.value.code == "COURSE_NOT_FOUND"


def test_small_course_with_low_confidence_evidence_generates_preliminary_plan(database) -> None:
    factory, seed, _engine, _url = database
    with factory() as session, session.begin():
        course = Course(owner_id=seed.owner_id, name="Small course", description="")
        session.add(course)
        session.flush()
        nodes = [_node(course.id, name) for name in ("概念一", "概念二", "概念三")]
        session.add_all(nodes)
        session.flush()
        small_seed = Seed(
            seed.owner_id,
            seed.other_owner_id,
            course.id,
            seed.other_course_id,
            tuple(node.id for node in nodes),
        )
        for node_index, node in enumerate(nodes):
            for offset in range(3):
                _add_evidence(
                    session,
                    small_seed,
                    node_id=node.id,
                    score="0" if node_index == 0 else "1",
                    offset=500 + node_index * 10 + offset,
                )
    with factory() as session:
        for node in nodes:
            MasteryService(session).refresh_state(
                user_id=seed.owner_id,
                course_id=course.id,
                knowledge_node_id=node.id,
            )
    with factory() as session:
        before_evidence = session.scalar(select(func.count()).select_from(LearningEvidence))
        before_states = session.scalar(select(func.count()).select_from(StudentKnowledgeState))
        session.rollback()
        result = _service(session).generate(user_id=seed.owner_id, course_id=course.id)
        assert result.availability == LearningPlanAvailability.AVAILABLE
        assert result.plan_level == LearningPlanLevel.PRELIMINARY
        assert result.plan is not None and result.plan.target_node_id == nodes[0].id
        assert len(result.plan.tasks) == 2
        repeated = _service(session).generate(user_id=seed.owner_id, course_id=course.id)
        assert repeated.reused is True
        assert repeated.plan is not None and repeated.plan.plan_id == result.plan.plan_id
        assert session.scalar(select(func.count()).select_from(LearningEvidence)) == before_evidence
        assert session.scalar(select(func.count()).select_from(StudentKnowledgeState)) == before_states


def test_course_without_knowledge_model_does_not_generate_foundational_plan(database) -> None:
    factory, seed, _engine, _url = database
    with factory() as session, session.begin():
        course = Course(owner_id=seed.owner_id, name="No knowledge model", description="")
        session.add(course)
        session.flush()
        course_id = course.id
    with factory() as session:
        with pytest.raises(LearningPlanError) as captured:
            _service(session).generate(user_id=seed.owner_id, course_id=course_id)
        assert captured.value.code == "KNOWLEDGE_MODEL_NOT_FOUND"
        assert (
            session.scalar(select(func.count()).select_from(LearningPlan).where(LearningPlan.course_id == course_id))
            == 0
        )


def test_invalidated_target_supersedes_old_plan_with_safe_replacement(database) -> None:
    factory, seed, _engine, _url = database
    with factory() as session:
        generated = _service(session).generate(user_id=seed.owner_id, course_id=seed.course_id)
        assert generated.plan is not None
        plan_id = generated.plan.plan_id
    with factory() as session, session.begin():
        target = session.get(KnowledgeNode, seed.node_ids[0])
        assert target is not None
        target.is_active = False
    with factory() as session:
        result = _service(session).generate(user_id=seed.owner_id, course_id=seed.course_id)
        assert result.availability == LearningPlanAvailability.AVAILABLE
        assert result.plan is not None and result.plan.target_node_id != seed.node_ids[0]
        old = session.get(LearningPlan, plan_id)
        assert old is not None and old.status == LearningPlanStatus.SUPERSEDED
        assert (
            session.scalar(
                select(func.count())
                .select_from(LearningPlan)
                .where(LearningPlan.status == LearningPlanStatus.AVAILABLE)
            )
            == 1
        )


def test_failed_transaction_leaves_no_plan_or_orphan_task(database) -> None:
    factory, seed, _engine, _url = database

    class FailingRepository(LearningPlanRepository):
        def add(self, plan: LearningPlan) -> LearningPlan:
            super().add(plan)
            raise RuntimeError("simulated write failure")

    with factory() as session:
        service = _service(session)
        service.plans = FailingRepository(session)
        with pytest.raises(RuntimeError, match="simulated write failure"):
            service.generate(user_id=seed.owner_id, course_id=seed.course_id)
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(LearningPlan)) == 0
        assert session.scalar(select(func.count()).select_from(LearningTask)) == 0


def test_concurrent_generation_has_one_active_plan(database) -> None:
    factory, seed, _engine, _url = database
    barrier = Barrier(2)

    class SynchronizedEngine(RecommendationEngine):
        def recommend(self, context):
            result = super().recommend(context)
            barrier.wait(timeout=10)
            return result

    def generate() -> int:
        with factory() as session:
            result = LearningPlanService(
                session,
                Settings(database_url="sqlite+pysqlite://"),
                recommendation_engine=SynchronizedEngine(),
            ).generate(user_id=seed.owner_id, course_id=seed.course_id)
            assert result.plan is not None
            return result.plan.plan_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        plan_ids = list(pool.map(lambda _index: generate(), range(2)))
    assert plan_ids[0] == plan_ids[1]
    with factory() as session:
        active_count = session.scalar(
            select(func.count()).select_from(LearningPlan).where(LearningPlan.status == LearningPlanStatus.AVAILABLE)
        )
        assert active_count == 1
        assert session.scalar(select(func.count()).select_from(LearningPlan)) == 1


def test_plan_survives_new_session_and_api_routes_are_registered(database) -> None:
    factory, seed, _engine, _url = database
    with factory() as session:
        generated = _service(session).generate(user_id=seed.owner_id, course_id=seed.course_id)
        assert generated.plan is not None
        plan_id = generated.plan.plan_id
    with factory() as restarted_session:
        restored = _service(restarted_session).get_current(user_id=seed.owner_id, course_id=seed.course_id)
        assert restored.availability == LearningPlanAvailability.AVAILABLE
        assert restored.plan is not None and restored.plan.plan_id == plan_id

    from backend.main import app

    paths = app.openapi()["paths"]
    assert "get" in paths["/api/courses/{course_id}/learning-plan"]
    assert "post" in paths["/api/courses/{course_id}/learning-plan/generate"]
