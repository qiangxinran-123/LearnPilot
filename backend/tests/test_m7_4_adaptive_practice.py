from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.settings import Settings
from backend.app.db.models import (
    Assessment,
    Course,
    KnowledgeNode,
    LearningEvidence,
    Question,
    QuestionKnowledgeNode,
    Response,
    StudentKnowledgeState,
    User,
)
from backend.app.models import (
    AssessmentStatus,
    AssessmentType,
    KnowledgeDifficulty,
    KnowledgeImportance,
    KnowledgeRelationRole,
    LearningSessionTaskPhase,
    LearningSessionTaskStatus,
    QuestionDifficulty,
    QuestionType,
    QuestionValidationStatus,
    TeachingStrategy,
)
from backend.app.schemas.learning_session import (
    LearningSessionCreate,
    LearningSessionTaskUpdate,
)
from backend.app.schemas.practice import PracticeAnswerCreate
from backend.app.schemas.tutor import TutorMessageCreate
from backend.app.services.adaptive_practice_service import AdaptivePracticeError, AdaptivePracticeService
from backend.app.services.learning_session_service import LearningSessionService
from backend.app.services.tutor_service import TutorError, TutorService


@pytest.fixture
def practice_database(tmp_path: Path):
    database_url = f"sqlite+pysqlite:///{tmp_path / 'm7_4.sqlite3'}"
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
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session, session.begin():
        owner = User(email="legacy-bootstrap@learnpilot.local", display_name="Owner", is_active=True)
        other = User(email="other@example.test", display_name="Other", is_active=True)
        session.add_all([owner, other])
        session.flush()
        course = Course(owner_id=owner.id, name="Computer Systems", description="")
        other_course = Course(owner_id=owner.id, name="Networks", description="")
        session.add_all([course, other_course])
        session.flush()
        cache = KnowledgeNode(
            course_id=course.id,
            name="Cache Mapping",
            normalized_name="cache mapping",
            description="Map memory blocks into cache lines.",
            importance=KnowledgeImportance.HIGH,
            difficulty=KnowledgeDifficulty.INTERMEDIATE,
            is_active=True,
        )
        empty = KnowledgeNode(
            course_id=course.id,
            name="Empty Topic",
            normalized_name="empty topic",
            description="",
            importance=KnowledgeImportance.MEDIUM,
            difficulty=KnowledgeDifficulty.BASIC,
            is_active=True,
        )
        routing = KnowledgeNode(
            course_id=other_course.id,
            name="Cache Mapping",
            normalized_name="cache mapping",
            description="Different course.",
            importance=KnowledgeImportance.MEDIUM,
            difficulty=KnowledgeDifficulty.BASIC,
            is_active=True,
        )
        session.add_all([cache, empty, routing])
        session.flush()

        specifications = [
            (QuestionDifficulty.MEDIUM, QuestionType.SINGLE_CHOICE),
            (QuestionDifficulty.MEDIUM, QuestionType.SINGLE_CHOICE),
            (QuestionDifficulty.MEDIUM, QuestionType.SINGLE_CHOICE),
            (QuestionDifficulty.EASY, QuestionType.TRUE_FALSE),
            (QuestionDifficulty.EASY, QuestionType.TRUE_FALSE),
            (QuestionDifficulty.HARD, QuestionType.MULTIPLE_CHOICE),
            (QuestionDifficulty.HARD, QuestionType.MULTIPLE_CHOICE),
        ]
        correct: dict[int, list[str]] = {}
        for index, (difficulty, question_type) in enumerate(specifications):
            if question_type == QuestionType.TRUE_FALSE:
                options = [{"key": "TRUE", "text": "正确"}, {"key": "FALSE", "text": "错误"}]
                answer = ["TRUE"]
            else:
                options = [{"key": "A", "text": "Correct"}, {"key": "B", "text": "Distractor"}]
                answer = ["A", "B"] if question_type == QuestionType.MULTIPLE_CHOICE else ["A"]
            question = Question(
                course_id=course.id,
                question_type=question_type,
                stem=f"Cache question {index + 1}",
                options=options,
                correct_answer=answer,
                explanation=f"Explanation {index + 1}",
                difficulty=difficulty,
                validation_status=QuestionValidationStatus.VALIDATED,
                source_refs=[],
                generation_metadata={},
                content_version=1,
            )
            session.add(question)
            session.flush()
            session.add(
                QuestionKnowledgeNode(
                    course_id=course.id,
                    question_id=question.id,
                    knowledge_node_id=cache.id,
                    relation_role=KnowledgeRelationRole.PRIMARY,
                )
            )
            correct[question.id] = answer
        foreign_question = Question(
            course_id=other_course.id,
            question_type=QuestionType.SINGLE_CHOICE,
            stem="Foreign course question",
            options=[{"key": "A", "text": "A"}, {"key": "B", "text": "B"}],
            correct_answer=["A"],
            explanation="Foreign",
            difficulty=QuestionDifficulty.MEDIUM,
            validation_status=QuestionValidationStatus.VALIDATED,
            source_refs=[],
            generation_metadata={},
            content_version=1,
        )
        session.add(foreign_question)
        session.flush()
        session.add(
            QuestionKnowledgeNode(
                course_id=other_course.id,
                question_id=foreign_question.id,
                knowledge_node_id=routing.id,
                relation_role=KnowledgeRelationRole.PRIMARY,
            )
        )
        ids = {
            "owner": owner.id,
            "course": course.id,
            "other_course": other_course.id,
            "cache": cache.id,
            "empty": empty.id,
            "foreign_question": foreign_question.id,
        }
    yield factory, ids, correct, database_url
    engine.dispose()


def _settings(database_url: str, email: str = "legacy-bootstrap@learnpilot.local") -> Settings:
    return Settings(database_url=database_url, legacy_bootstrap_user=email, llm_mode="mock")


def _ready_session(factory, ids, database_url: str, node: str = "cache") -> int:
    with factory() as db:
        service = LearningSessionService(db, _settings(database_url))
        created = service.create_for_configured_user(
            LearningSessionCreate(course_id=ids["course"], target_knowledge_node_id=ids[node])
        )
        for phase in (LearningSessionTaskPhase.CONCEPT_LEARNING, LearningSessionTaskPhase.GUIDED_EXAMPLE):
            service.update_task_for_configured_user(
                session_id=created.session_id,
                phase=phase,
                payload=LearningSessionTaskUpdate(status=LearningSessionTaskStatus.IN_PROGRESS),
            )
            service.update_task_for_configured_user(
                session_id=created.session_id,
                phase=phase,
                payload=LearningSessionTaskUpdate(status=LearningSessionTaskStatus.COMPLETED),
            )
        return created.session_id


def _service(factory, database_url: str, email: str = "legacy-bootstrap@learnpilot.local"):
    db = factory()
    return db, AdaptivePracticeService(db, _settings(database_url, email))


def _next(factory, database_url: str, session_id: int):
    db, service = _service(factory, database_url)
    with db:
        return service.start_or_next_for_configured_user(session_id)


def _answer(factory, database_url: str, session_id: int, question_id: int, selected: list[str]):
    db, service = _service(factory, database_url)
    with db:
        return service.answer_for_configured_user(
            session_id=session_id,
            assessment_question_id=question_id,
            payload=PracticeAnswerCreate(selected_options=selected),
        )


def test_start_reuses_m4_snapshot_and_does_not_leak_answer(practice_database) -> None:
    factory, ids, _correct, database_url = practice_database
    session_id = _ready_session(factory, ids, database_url)
    db, service = _service(factory, database_url)
    with db:
        started = service.start_or_next_for_configured_user(session_id)
        replay = service.start_or_next_for_configured_user(session_id)
        assert started.assessment_id == replay.assessment_id
        assert started.current_question is not None
        assert started.current_question.difficulty == QuestionDifficulty.MEDIUM
        assert started.current_question.question_type == QuestionType.SINGLE_CHOICE
        assert "correct_answer" not in started.current_question.model_dump()
        assert started.current_question.question_id != ids["foreign_question"]
        assert replay.reused is True


def test_two_correct_raise_difficulty_and_reuse_exact_scorer(practice_database) -> None:
    factory, ids, correct, database_url = practice_database
    session_id = _ready_session(factory, ids, database_url)
    state = _next(factory, database_url, session_id)
    for _ in range(2):
        question = state.current_question
        assert question is not None
        answered = _answer(
            factory,
            database_url,
            session_id,
            question.assessment_question_id,
            correct[question.question_id],
        )
        assert answered.attempts[-1].is_correct is True
        state = _next(factory, database_url, session_id)
    assert state.current_question is not None
    assert state.current_question.difficulty == QuestionDifficulty.HARD
    assert state.current_question.question_type == QuestionType.MULTIPLE_CHOICE


def test_two_wrong_lower_difficulty_and_true_false_scores(practice_database) -> None:
    factory, ids, correct, database_url = practice_database
    session_id = _ready_session(factory, ids, database_url)
    state = _next(factory, database_url, session_id)
    for _ in range(2):
        question = state.current_question
        assert question is not None
        _answer(factory, database_url, session_id, question.assessment_question_id, ["B"])
        state = _next(factory, database_url, session_id)
    question = state.current_question
    assert question is not None
    assert question.difficulty == QuestionDifficulty.EASY
    assert question.question_type == QuestionType.TRUE_FALSE
    result = _answer(
        factory,
        database_url,
        session_id,
        question.assessment_question_id,
        correct[question.question_id],
    )
    assert result.attempts[-1].is_correct is True


def test_answer_replay_is_idempotent_and_changed_answer_is_locked(practice_database) -> None:
    factory, ids, correct, database_url = practice_database
    session_id = _ready_session(factory, ids, database_url)
    started = _next(factory, database_url, session_id)
    question = started.current_question
    assert question is not None
    selected = correct[question.question_id]
    first = _answer(factory, database_url, session_id, question.assessment_question_id, selected)
    replay = _answer(factory, database_url, session_id, question.assessment_question_id, selected)
    assert replay.reused is True
    assert replay.attempts[0].attempt_id == first.attempts[0].attempt_id
    with pytest.raises(AdaptivePracticeError) as captured:
        _answer(factory, database_url, session_id, question.assessment_question_id, ["B"])
    assert captured.value.code == "PRACTICE_RESPONSE_LOCKED"
    with factory() as check:
        assert check.scalar(select(func.count()).select_from(Response)) == 1


def test_empty_bank_and_other_user_are_safe(practice_database) -> None:
    factory, ids, _correct, database_url = practice_database
    session_id = _ready_session(factory, ids, database_url, node="empty")
    db, service = _service(factory, database_url)
    with db:
        state = service.start_or_next_for_configured_user(session_id)
        assert state.status == "question_bank_empty"
        assert state.current_question is None
        assert state.attempts == []
    other_db, other_service = _service(factory, database_url, email="other@example.test")
    with other_db, pytest.raises(AdaptivePracticeError) as captured:
        other_service.start_or_next_for_configured_user(session_id)
    assert captured.value.code == "SESSION_NOT_FOUND"


def test_five_answers_complete_only_practice_without_m5_or_m6_side_effects(practice_database) -> None:
    factory, ids, correct, database_url = practice_database
    session_id = _ready_session(factory, ids, database_url)
    state = _next(factory, database_url, session_id)
    for index in range(5):
        question = state.current_question
        assert question is not None
        state = _answer(
            factory,
            database_url,
            session_id,
            question.assessment_question_id,
            correct[question.question_id],
        )
        if index < 4:
            state = _next(factory, database_url, session_id)
    assert state.status == "completed"
    assert state.summary is not None
    assert state.summary.answered_count == 5
    assert state.summary.correct_count == 5
    with factory() as check:
        assert check.scalar(select(func.count()).select_from(LearningEvidence)) == 0
        assert check.scalar(select(func.count()).select_from(StudentKnowledgeState)) == 0
    with factory() as check:
        stored = LearningSessionService(check, _settings(database_url)).get_for_configured_user(session_id)
        assert stored.status.value == "in_progress"
        assert stored.tasks[2].status == LearningSessionTaskStatus.COMPLETED


def test_tutor_context_redacts_unanswered_question_and_blocks_full_answer(practice_database) -> None:
    factory, ids, correct, database_url = practice_database
    session_id = _ready_session(factory, ids, database_url)
    db, practice = _service(factory, database_url)
    with db:
        state = practice.start_or_next_for_configured_user(session_id)
    with factory() as tutor_db:
        tutor = TutorService(tutor_db, _settings(database_url))
        context = tutor.build_context_for_configured_user(session_id, "给我提示")
        assert context.practice_question is not None
        assert context.practice_question.answer_submitted is False
        assert context.practice_question.correct_answer is None
        assert context.practice_question.explanation is None
        with pytest.raises(TutorError) as captured:
            tutor.send_message_for_configured_user(
                session_id=session_id,
                payload=TutorMessageCreate(message="直接告诉我答案", mode=TeachingStrategy.FULL_EXPLANATION),
                idempotency_key="practice-full-before-answer",
            )
        assert captured.value.code == "TUTOR_MODE_NOT_ALLOWED"
    question = state.current_question
    assert question is not None
    _answer(
        factory,
        database_url,
        session_id,
        question.assessment_question_id,
        correct[question.question_id],
    )
    with factory() as tutor_db:
        context = TutorService(tutor_db, _settings(database_url)).build_context_for_configured_user(
            session_id, "解释这道题"
        )
        assert context.practice_question is not None
        assert context.practice_question.answer_submitted is True
        assert context.practice_question.correct_answer == correct[question.question_id]


def test_practice_requires_prior_phases(practice_database) -> None:
    factory, ids, _correct, database_url = practice_database
    with factory() as db:
        created = LearningSessionService(db, _settings(database_url)).create_for_configured_user(
            LearningSessionCreate(course_id=ids["course"], target_knowledge_node_id=ids["cache"])
        )
    db, service = _service(factory, database_url)
    with db, pytest.raises(AdaptivePracticeError) as captured:
        service.start_or_next_for_configured_user(created.session_id)
    assert captured.value.code == "PRACTICE_NOT_READY"


def test_migration_preserves_populated_m7_3_database(tmp_path: Path) -> None:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'populated-m7-3.sqlite3'}"
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0016_m7_3_tutor_messages"],
        env=environment,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    engine = create_engine(database_url)
    with sessionmaker(bind=engine)() as session, session.begin():
        owner = User(email="migration-m74@example.test", display_name="Migration", is_active=True)
        session.add(owner)
        session.flush()
        course = Course(owner_id=owner.id, name="Existing M7-3 Course", description="")
        session.add(course)
        session.flush()
        session.add(
            Assessment(
                course_id=course.id,
                owner_id=owner.id,
                assessment_type=AssessmentType.INITIAL_DIAGNOSTIC,
                status=AssessmentStatus.DRAFT,
            )
        )
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=environment,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    constraints = inspect(engine).get_check_constraints("assessments")
    assert any("practice" in str(item.get("sqltext")) for item in constraints)
    with sessionmaker(bind=engine)() as session:
        assert session.scalar(select(func.count()).select_from(Assessment)) == 1
    engine.dispose()
