from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Generator
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.models import (
    Assessment,
    AssessmentQuestion,
    Course,
    KnowledgeNode,
    Question,
    QuestionKnowledgeNode,
    Response,
    User,
)
from backend.app.models import (
    AssessmentStatus,
    KnowledgeDifficulty,
    KnowledgeImportance,
    KnowledgeRelationRole,
    QuestionDifficulty,
    QuestionType,
    QuestionValidationStatus,
)
from backend.app.repositories import AssessmentRepository
from backend.app.schemas.diagnostic import AssessmentQuestionSnapshotSchema, ObjectiveAnswerSchema
from backend.app.services.assessment_assembly_service import (
    AssessmentAssemblyError,
    AssessmentAssemblyService,
)
from backend.app.services.deterministic_objective_scorer import (
    DeterministicObjectiveScorer,
    DeterministicScoringError,
)
from backend.app.services.diagnostic_domain_service import DiagnosticDomainError, DiagnosticDomainService


def migrate_database(path: Path) -> str:
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


class Seed:
    owner_id: int
    other_owner_id: int
    course_id: int
    other_course_id: int
    node_ids: list[int]
    low_node_id: int
    pending_question_id: int
    rejected_question_id: int
    no_source_question_id: int
    foreign_question_id: int


def _options(question_type: QuestionType) -> tuple[list[dict[str, str]], list[str]]:
    if question_type == QuestionType.TRUE_FALSE:
        return ([{"key": "TRUE", "text": "True"}, {"key": "FALSE", "text": "False"}], ["TRUE"])
    if question_type == QuestionType.MULTIPLE_CHOICE:
        return (
            [
                {"key": "A", "text": "First valid statement"},
                {"key": "B", "text": "Distractor statement"},
                {"key": "C", "text": "Second valid statement"},
                {"key": "D", "text": "Another distractor"},
            ],
            ["A", "C"],
        )
    return (
        [
            {"key": "A", "text": "Correct concept"},
            {"key": "B", "text": "Distractor one"},
            {"key": "C", "text": "Distractor two"},
            {"key": "D", "text": "Distractor three"},
        ],
        ["A"],
    )


def add_question(
    session: Session,
    *,
    course_id: int,
    node_id: int,
    index: int,
    question_type: QuestionType = QuestionType.SINGLE_CHOICE,
    difficulty: QuestionDifficulty = QuestionDifficulty.MEDIUM,
    status: QuestionValidationStatus = QuestionValidationStatus.VALIDATED,
    with_source: bool = True,
    stem: str | None = None,
) -> Question:
    options, correct = _options(question_type)
    question = Question(
        course_id=course_id,
        question_type=question_type,
        stem=stem or f"Validated diagnostic question {index} for node {node_id}?",
        options=options,
        correct_answer=correct,
        explanation=f"Deterministic explanation for question {index}.",
        difficulty=difficulty,
        validation_status=status,
        source_refs=(
            [
                {
                    "material_id": 1,
                    "material_title": "Verified course source",
                    "source_reference": f"TXT segment {index}",
                    "excerpt": "Verified source evidence.",
                }
            ]
            if with_source
            else []
        ),
        generation_metadata={"validation": "automated", "prompt_version": "diagnostic_questions_v1"},
        content_version=1,
    )
    session.add(question)
    session.flush()
    session.add(
        QuestionKnowledgeNode(
            course_id=course_id,
            question_id=question.id,
            knowledge_node_id=node_id,
            relation_role=KnowledgeRelationRole.PRIMARY,
        )
    )
    session.flush()
    return question


def add_course_bank(
    session: Session,
    *,
    owner_id: int,
    name: str,
    node_count: int,
    questions_per_node: int,
    all_easy_single: bool = False,
) -> tuple[Course, list[KnowledgeNode]]:
    course = Course(owner_id=owner_id, name=name, description="")
    session.add(course)
    session.flush()
    nodes: list[KnowledgeNode] = []
    index = 1
    question_types = [QuestionType.SINGLE_CHOICE, QuestionType.TRUE_FALSE, QuestionType.MULTIPLE_CHOICE]
    difficulties = [QuestionDifficulty.EASY, QuestionDifficulty.MEDIUM, QuestionDifficulty.HARD]
    for node_index in range(node_count):
        node = KnowledgeNode(
            course_id=course.id,
            name=f"Core node {node_index + 1}",
            normalized_name=f"core node {node_index + 1}",
            description="Core diagnostic knowledge.",
            importance=KnowledgeImportance.HIGH if node_index < 2 else KnowledgeImportance.MEDIUM,
            difficulty=KnowledgeDifficulty.INTERMEDIATE,
            is_active=True,
            managed_by_canonicalization=True,
        )
        session.add(node)
        session.flush()
        nodes.append(node)
        for _ in range(questions_per_node):
            add_question(
                session,
                course_id=course.id,
                node_id=node.id,
                index=index,
                question_type=(QuestionType.SINGLE_CHOICE if all_easy_single else question_types[(index - 1) % 3]),
                difficulty=QuestionDifficulty.EASY if all_easy_single else difficulties[(index - 1) % 3],
            )
            index += 1
    return course, nodes


def seed_foundation(session: Session) -> Seed:
    seed = Seed()
    with session.begin():
        owner = User(email="m4c-owner@example.test", display_name="M4C Owner", is_active=True)
        other = User(email="m4c-other@example.test", display_name="Other Owner", is_active=True)
        session.add_all([owner, other])
        session.flush()
        course, nodes = add_course_bank(
            session,
            owner_id=owner.id,
            name="M4C Main Course",
            node_count=5,
            questions_per_node=3,
        )
        low_node = KnowledgeNode(
            course_id=course.id,
            name="Optional low node",
            normalized_name="optional low node",
            description="Not part of the default core scope.",
            importance=KnowledgeImportance.LOW,
            difficulty=KnowledgeDifficulty.BASIC,
            is_active=True,
            managed_by_canonicalization=True,
        )
        session.add(low_node)
        session.flush()
        pending = add_question(
            session,
            course_id=course.id,
            node_id=nodes[0].id,
            index=100,
            status=QuestionValidationStatus.PENDING,
        )
        rejected = add_question(
            session,
            course_id=course.id,
            node_id=nodes[0].id,
            index=101,
            status=QuestionValidationStatus.REJECTED,
        )
        no_source = add_question(
            session,
            course_id=course.id,
            node_id=nodes[0].id,
            index=102,
            with_source=False,
        )
        other_course, other_nodes = add_course_bank(
            session,
            owner_id=other.id,
            name="Foreign Course",
            node_count=1,
            questions_per_node=8,
            all_easy_single=True,
        )
        foreign_question = session.scalar(
            select(Question).where(Question.course_id == other_course.id).order_by(Question.id)
        )
        assert foreign_question is not None
        seed.owner_id = owner.id
        seed.other_owner_id = other.id
        seed.course_id = course.id
        seed.other_course_id = other_course.id
        seed.node_ids = [node.id for node in nodes]
        seed.low_node_id = low_node.id
        seed.pending_question_id = pending.id
        seed.rejected_question_id = rejected.id
        seed.no_source_question_id = no_source.id
        seed.foreign_question_id = foreign_question.id
    return seed


@pytest.fixture
def database(tmp_path: Path) -> Generator[tuple[sessionmaker[Session], Seed], None, None]:
    database_url = migrate_database(tmp_path / "m4c.sqlite3")
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        seed = seed_foundation(session)
    yield factory, seed
    engine.dispose()


def source_question_ids(rows: tuple[AssessmentQuestion, ...]) -> list[int]:
    return [AssessmentQuestionSnapshotSchema.model_validate(row.question_snapshot).source_question_id for row in rows]


def test_assembly_uses_only_eligible_bank_and_is_deterministic(database) -> None:
    factory, seed = database
    with factory() as session:
        first = AssessmentAssemblyService(session).assemble_initial_diagnostic(seed.owner_id, seed.course_id)
        first_ids = source_question_ids(first.questions)
        assert first.assessment.status == AssessmentStatus.READY
        assert len(first_ids) == 10
        assert len(first_ids) == len(set(first_ids))
        assert set(first_ids).isdisjoint(
            {
                seed.pending_question_id,
                seed.rejected_question_id,
                seed.no_source_question_id,
                seed.foreign_question_id,
            }
        )
        assert first.metadata.eligible_knowledge_nodes == 5
        assert first.metadata.covered_knowledge_nodes == 5
        assert sum(first.metadata.question_type_distribution.values()) == 10
        assert sum(first.metadata.difficulty_distribution.values()) == 10
    with factory() as session:
        second = AssessmentAssemblyService(session).assemble_initial_diagnostic(seed.owner_id, seed.course_id)
        assert source_question_ids(second.questions) == first_ids


def test_dynamic_question_count_has_eight_and_twenty_boundaries(database) -> None:
    factory, seed = database
    with factory() as session, session.begin():
        small, _ = add_course_bank(
            session,
            owner_id=seed.owner_id,
            name="Small Core Course",
            node_count=1,
            questions_per_node=10,
        )
        large, _ = add_course_bank(
            session,
            owner_id=seed.owner_id,
            name="Large Core Course",
            node_count=20,
            questions_per_node=1,
        )
        small_id = small.id
        large_id = large.id
    with factory() as session:
        small_result = AssessmentAssemblyService(session).assemble_initial_diagnostic(seed.owner_id, small_id)
        assert len(small_result.questions) == 8
    with factory() as session:
        large_result = AssessmentAssemblyService(session).assemble_initial_diagnostic(seed.owner_id, large_id)
        assert len(large_result.questions) == 20


def test_insufficient_bank_returns_explainable_statistics(database) -> None:
    factory, seed = database
    with factory() as session, session.begin():
        course, _ = add_course_bank(
            session,
            owner_id=seed.owner_id,
            name="Insufficient Course",
            node_count=1,
            questions_per_node=7,
        )
        course_id = course.id
    with factory() as session:
        with pytest.raises(AssessmentAssemblyError) as captured:
            AssessmentAssemblyService(session).assemble_initial_diagnostic(seed.owner_id, course_id)
        assert captured.value.code == "QUESTION_BANK_INSUFFICIENT"
        assert captured.value.statistics is not None
        assert captured.value.statistics.available_questions == 7
        assert captured.value.statistics.required_questions == 8
        assert session.scalar(select(func.count(Assessment.id)).where(Assessment.course_id == course_id)) == 0


def test_missing_core_node_coverage_is_rejected_even_with_eight_questions(database) -> None:
    factory, seed = database
    with factory() as session, session.begin():
        course = Course(owner_id=seed.owner_id, name="Coverage Gap Course", description="")
        session.add(course)
        session.flush()
        nodes = []
        for index in range(2):
            node = KnowledgeNode(
                course_id=course.id,
                name=f"Required node {index}",
                normalized_name=f"required node {index}",
                description="Required.",
                importance=KnowledgeImportance.HIGH,
                difficulty=KnowledgeDifficulty.BASIC,
                is_active=True,
                managed_by_canonicalization=True,
            )
            session.add(node)
            session.flush()
            nodes.append(node)
        for index in range(8):
            add_question(session, course_id=course.id, node_id=nodes[0].id, index=200 + index)
        course_id = course.id
    with factory() as session:
        with pytest.raises(AssessmentAssemblyError) as captured:
            AssessmentAssemblyService(session).assemble_initial_diagnostic(seed.owner_id, course_id)
        assert captured.value.code == "QUESTION_BANK_INSUFFICIENT"
        assert captured.value.statistics is not None
        assert captured.value.statistics.eligible_knowledge_nodes == 2
        assert captured.value.statistics.covered_knowledge_nodes == 1


def test_type_and_difficulty_targets_degrade_to_available_quality_bank(database) -> None:
    factory, seed = database
    with factory() as session, session.begin():
        course, _ = add_course_bank(
            session,
            owner_id=seed.owner_id,
            name="Graceful Degradation Course",
            node_count=1,
            questions_per_node=8,
            all_easy_single=True,
        )
        course_id = course.id
    with factory() as session:
        result = AssessmentAssemblyService(session).assemble_initial_diagnostic(seed.owner_id, course_id)
        assert result.metadata.question_type_distribution == {QuestionType.SINGLE_CHOICE: 8}
        assert result.metadata.difficulty_distribution == {QuestionDifficulty.EASY: 8}


def test_assembly_snapshot_is_complete_immutable_and_candidate_safe(database) -> None:
    factory, seed = database
    with factory() as session:
        result = AssessmentAssemblyService(session).assemble_initial_diagnostic(seed.owner_id, seed.course_id)
        assessment_id = result.assessment.id
        first = result.questions[0]
        snapshot_id = first.id
        expected = deepcopy(first.question_snapshot)
        question_id = expected["source_question_id"]
        node_id = expected["knowledge_nodes"][0]["id"]
        candidates = AssessmentAssemblyService(session).candidate_questions(seed.owner_id, assessment_id)
        public = candidates[0].model_dump(mode="json")
        assert set(public) == {
            "assessment_question_id",
            "order_index",
            "question_type",
            "stem",
            "options",
            "difficulty",
        }
        assert "correct_answer" not in public
        assert "explanation" not in public
        assert "scoring_policy" not in public
    with factory() as session, session.begin():
        question = session.get(Question, question_id)
        node = session.get(KnowledgeNode, node_id)
        assert question is not None and node is not None
        question.stem = "Changed live question"
        question.correct_answer = ["B"]
        node.name = "Changed live node"
    with factory() as session:
        stored = session.get(AssessmentQuestion, snapshot_id)
        assert stored is not None
        assert stored.question_snapshot == expected


def snapshot_for(question_type: QuestionType) -> dict[str, object]:
    options, correct = _options(question_type)
    return {
        "schema_version": "assessment_question_v1",
        "source_question_id": 1,
        "source_question_version": 1,
        "question_type": question_type.value,
        "stem": "Deterministic scoring question?",
        "options": options,
        "correct_answer": correct,
        "explanation": "Deterministic explanation.",
        "difficulty": "medium",
        "knowledge_nodes": [{"id": 1, "name": "Node", "role": "primary"}],
        "source_refs": [],
        "scoring_policy": {"version": "objective_exact_match_v1", "max_points": 1},
    }


@pytest.mark.parametrize(
    ("question_type", "selected", "expected"),
    [
        (QuestionType.SINGLE_CHOICE, ["A"], True),
        (QuestionType.SINGLE_CHOICE, ["B"], False),
        (QuestionType.TRUE_FALSE, ["TRUE"], True),
        (QuestionType.TRUE_FALSE, ["FALSE"], False),
        (QuestionType.MULTIPLE_CHOICE, ["C", "A"], True),
        (QuestionType.MULTIPLE_CHOICE, ["A"], False),
        (QuestionType.MULTIPLE_CHOICE, [], False),
    ],
)
def test_deterministic_objective_scoring(question_type, selected, expected) -> None:
    scorer = DeterministicObjectiveScorer()
    first = scorer.score(snapshot_for(question_type), {"selected_options": selected})
    second = scorer.score(snapshot_for(question_type), {"selected_options": selected})
    assert first == second
    assert first.is_correct is expected
    assert first.points_awarded == (Decimal("1") if expected else Decimal("0"))
    assert first.max_points == Decimal("1")
    assert first.scoring_policy_version == "objective_exact_match_v1"


def test_scorer_rejects_unknown_policy_and_illegal_answer() -> None:
    scorer = DeterministicObjectiveScorer()
    unknown = snapshot_for(QuestionType.SINGLE_CHOICE)
    unknown["scoring_policy"] = {"version": "future_policy", "max_points": 1}
    with pytest.raises(DeterministicScoringError) as policy_error:
        scorer.score(unknown, {"selected_options": ["A"]})
    assert policy_error.value.code == "SCORING_POLICY_UNSUPPORTED"
    with pytest.raises(DeterministicScoringError) as answer_error:
        scorer.score(snapshot_for(QuestionType.TRUE_FALSE), {"selected_options": ["对"]})
    assert answer_error.value.code == "SCORING_ANSWER_INVALID"


def wrong_answer(snapshot: AssessmentQuestionSnapshotSchema) -> ObjectiveAnswerSchema:
    for option in snapshot.options:
        if option.key not in snapshot.correct_answer:
            return ObjectiveAnswerSchema(selected_options=[option.key])
    raise AssertionError("Fixture requires a distractor.")


def final_answers_for(rows: list[AssessmentQuestion]) -> dict[int, ObjectiveAnswerSchema]:
    result: dict[int, ObjectiveAnswerSchema] = {}
    for index, row in enumerate(rows):
        snapshot = AssessmentQuestionSnapshotSchema.model_validate(row.question_snapshot)
        if index % 3 == 0:
            result[row.id] = ObjectiveAnswerSchema(selected_options=snapshot.correct_answer)
        elif index % 3 == 1:
            result[row.id] = wrong_answer(snapshot)
        else:
            result[row.id] = ObjectiveAnswerSchema()
    return result


def test_submission_scores_atomically_and_summary_survives_reload(database) -> None:
    factory, seed = database
    with factory() as session:
        assembled = AssessmentAssemblyService(session).assemble_initial_diagnostic(seed.owner_id, seed.course_id)
        assessment_id = assembled.assessment.id
        domain = DiagnosticDomainService(session)
        domain.start_assessment(seed.owner_id, assessment_id)
        rows = list(assembled.questions)
        answers = final_answers_for(rows)
        submitted = domain.submit_assessment(seed.owner_id, assessment_id, answers)
        assert submitted.status == AssessmentStatus.SUBMITTED
    with factory() as session:
        stored = list(session.scalars(select(Response).where(Response.assessment_id == assessment_id)))
        assert len(stored) == 10
        assert all(response.submitted_at is not None for response in stored)
        assert all(response.is_correct is not None and response.points_awarded is not None for response in stored)
        session.rollback()
        summary = AssessmentAssemblyService(session).score_summary(seed.owner_id, assessment_id)
        assert summary.total_questions == 10
        assert summary.answered_questions == 7
        assert summary.correct_questions == 4
        assert summary.total_points == Decimal("10")
        assert summary.earned_points == Decimal("4")
        assert summary.accuracy == Decimal("0.4")


def test_repeated_submission_is_idempotent_and_changed_answers_are_rejected(database) -> None:
    factory, seed = database
    with factory() as session:
        assembled = AssessmentAssemblyService(session).assemble_initial_diagnostic(seed.owner_id, seed.course_id)
        assessment_id = assembled.assessment.id
        domain = DiagnosticDomainService(session)
        domain.start_assessment(seed.owner_id, assessment_id)
        rows = list(assembled.questions)
        answers = final_answers_for(rows)
        domain.submit_assessment(seed.owner_id, assessment_id, answers)
    with factory() as session:
        domain = DiagnosticDomainService(session)
        assert domain.submit_assessment(seed.owner_id, assessment_id, answers).status == AssessmentStatus.SUBMITTED
        response_count = session.scalar(select(func.count(Response.id)).where(Response.assessment_id == assessment_id))
        assert response_count == 10
    with factory() as session:
        domain = DiagnosticDomainService(session)
        changed = dict(answers)
        changed[rows[0].id] = wrong_answer(AssessmentQuestionSnapshotSchema.model_validate(rows[0].question_snapshot))
        with pytest.raises(DiagnosticDomainError) as captured:
            domain.submit_assessment(seed.owner_id, assessment_id, changed)
        assert captured.value.code == "ASSESSMENT_ALREADY_SUBMITTED"
        with pytest.raises(DiagnosticDomainError):
            domain.save_draft_response(seed.owner_id, assessment_id, rows[0].id, ObjectiveAnswerSchema())


def test_scoring_failure_rolls_back_answers_scores_and_submission(database) -> None:
    factory, seed = database
    with factory() as session:
        assembled = AssessmentAssemblyService(session).assemble_initial_diagnostic(seed.owner_id, seed.course_id)
        assessment_id = assembled.assessment.id
        first_id = assembled.questions[0].id
        answers = final_answers_for(list(assembled.questions))
        DiagnosticDomainService(session).start_assessment(seed.owner_id, assessment_id)
    with factory() as session, session.begin():
        row = session.get(AssessmentQuestion, first_id)
        assert row is not None
        corrupted = deepcopy(row.question_snapshot)
        corrupted["scoring_policy"] = {"version": "unknown_policy", "max_points": 1}
        row.question_snapshot = corrupted
    with factory() as session:
        with pytest.raises(DiagnosticDomainError) as captured:
            DiagnosticDomainService(session).submit_assessment(seed.owner_id, assessment_id, answers)
        assert captured.value.code == "SCORING_POLICY_UNSUPPORTED"
    with factory() as session:
        assessment = session.get(Assessment, assessment_id)
        assert assessment is not None
        assert assessment.status == AssessmentStatus.IN_PROGRESS
        assert session.scalar(select(func.count(Response.id)).where(Response.assessment_id == assessment_id)) == 0


def test_assembly_and_candidate_access_enforce_ownership(database) -> None:
    factory, seed = database
    with factory() as session:
        with pytest.raises(AssessmentAssemblyError) as course_error:
            AssessmentAssemblyService(session).assemble_initial_diagnostic(seed.other_owner_id, seed.course_id)
        assert course_error.value.code == "COURSE_NOT_FOUND"
        assembled = AssessmentAssemblyService(session).assemble_initial_diagnostic(seed.owner_id, seed.course_id)
        assessment_id = assembled.assessment.id
    with factory() as session:
        with pytest.raises(AssessmentAssemblyError) as assessment_error:
            AssessmentAssemblyService(session).candidate_questions(seed.other_owner_id, assessment_id)
        assert assessment_error.value.code == "ASSESSMENT_NOT_FOUND"
        with pytest.raises(DiagnosticDomainError) as submit_error:
            DiagnosticDomainService(session).start_assessment(seed.other_owner_id, assessment_id)
        assert submit_error.value.code == "ASSESSMENT_NOT_FOUND"


def test_snapshot_insert_failure_rolls_back_entire_assessment(database, monkeypatch: pytest.MonkeyPatch) -> None:
    factory, seed = database
    original = AssessmentRepository.add_question_snapshot
    calls = 0

    def fail_on_third(repository, row):
        nonlocal calls
        calls += 1
        if calls == 3:
            raise RuntimeError("simulated snapshot failure")
        return original(repository, row)

    monkeypatch.setattr(AssessmentRepository, "add_question_snapshot", fail_on_third)
    with factory() as session:
        with pytest.raises(RuntimeError, match="snapshot failure"):
            AssessmentAssemblyService(session).assemble_initial_diagnostic(seed.owner_id, seed.course_id)
        assert session.scalar(select(func.count(Assessment.id)).where(Assessment.course_id == seed.course_id)) == 0
