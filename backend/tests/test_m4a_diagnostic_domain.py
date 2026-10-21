from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Generator
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from backend.app.db.models import (
    Assessment,
    AssessmentQuestion,
    Course,
    KnowledgeNode,
    Material,
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
)
from backend.app.repositories import AssessmentRepository, QuestionRepository
from backend.app.schemas.diagnostic import (
    AssessmentQuestionSnapshotSchema,
    CandidateQuestionSchema,
    ObjectiveAnswerSchema,
    QuestionContentSchema,
    QuestionCreateSchema,
    QuestionKnowledgeBindingSchema,
    QuestionOptionSchema,
    QuestionSourceRefSchema,
)
from backend.app.services.diagnostic_domain_service import DiagnosticDomainError, DiagnosticDomainService


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


class Seed:
    def __init__(self, owner_id: int, other_owner_id: int, course_id: int, other_course_id: int, node_id: int):
        self.owner_id = owner_id
        self.other_owner_id = other_owner_id
        self.course_id = course_id
        self.other_course_id = other_course_id
        self.node_id = node_id


def seed_foundation(session: Session) -> Seed:
    with session.begin():
        owner = User(email="diagnostic-owner@example.test", display_name="Owner", is_active=True)
        other = User(email="other-owner@example.test", display_name="Other", is_active=True)
        session.add_all([owner, other])
        session.flush()
        course = Course(owner_id=owner.id, name="Computer Architecture", description="")
        other_course = Course(owner_id=other.id, name="Private Algorithms", description="")
        session.add_all([course, other_course])
        session.flush()
        node = KnowledgeNode(
            course_id=course.id,
            name="LRU Replacement",
            normalized_name="lru replacement",
            description="Cache replacement policy",
            importance=KnowledgeImportance.HIGH,
            difficulty=KnowledgeDifficulty.INTERMEDIATE,
            is_active=True,
            managed_by_canonicalization=True,
        )
        session.add(node)
        session.flush()
        return Seed(owner.id, other.id, course.id, other_course.id, node.id)


@pytest.fixture
def database(tmp_path: Path) -> Generator[tuple[sessionmaker[Session], Seed], None, None]:
    database_url = migrate_database(tmp_path / "m4a.sqlite3")
    engine = make_engine(database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        seed = seed_foundation(session)
    yield factory, seed
    engine.dispose()


def single_choice_content(*, stem: str = "Which block does LRU replace?", answer: str = "B") -> QuestionContentSchema:
    return QuestionContentSchema(
        question_type=QuestionType.SINGLE_CHOICE,
        stem=stem,
        options=[
            QuestionOptionSchema(key="A", text="Most recently used"),
            QuestionOptionSchema(key="B", text="Least recently used"),
        ],
        correct_answer=[answer],
        explanation="LRU replaces the block unused for the longest time.",
        difficulty=QuestionDifficulty.EASY,
        source_refs=[
            QuestionSourceRefSchema(
                material_id=1,
                material_title="Cache notes",
                source_reference="PDF page 12",
                excerpt="Least recently used replacement.",
            )
        ],
    )


def create_payload(node_id: int, *, content: QuestionContentSchema | None = None) -> QuestionCreateSchema:
    return QuestionCreateSchema(
        content=content or single_choice_content(),
        knowledge_nodes=[
            QuestionKnowledgeBindingSchema(
                knowledge_node_id=node_id,
                relation_role=KnowledgeRelationRole.PRIMARY,
            )
        ],
        generation_metadata={"fixture": True, "knowledge_model_version": "canonical-run-7"},
    )


def prepare_assessment(
    session: Session, seed: Seed, *, question_count: int = 1
) -> tuple[DiagnosticDomainService, list[Question], Assessment, list[AssessmentQuestion]]:
    service = DiagnosticDomainService(session)
    questions = [
        service.create_question(
            seed.owner_id,
            seed.course_id,
            create_payload(seed.node_id, content=single_choice_content(stem=f"Question {index + 1}")),
        )
        for index in range(question_count)
    ]
    assessment = service.create_assessment_draft(seed.owner_id, seed.course_id)
    snapshots = service.fix_question_snapshots(seed.owner_id, assessment.id, [item.id for item in questions])
    assessment = service.start_assessment(seed.owner_id, assessment.id)
    return service, questions, assessment, snapshots


@pytest.mark.parametrize(
    ("question_type", "options", "correct_answer"),
    [
        (QuestionType.SINGLE_CHOICE, [("A", "One"), ("B", "Two")], ["B"]),
        (QuestionType.TRUE_FALSE, [("TRUE", "True"), ("FALSE", "False")], ["TRUE"]),
        (QuestionType.MULTIPLE_CHOICE, [("A", "One"), ("B", "Two"), ("C", "Three")], ["C", "A"]),
    ],
)
def test_three_objective_question_contracts_are_normalized(question_type, options, correct_answer) -> None:
    content = QuestionContentSchema(
        question_type=question_type,
        stem="  Objective stem  ",
        options=[QuestionOptionSchema(key=key, text=text) for key, text in options],
        correct_answer=correct_answer,
        explanation="  Complete explanation  ",
        difficulty=QuestionDifficulty.MEDIUM,
    )
    assert content.stem == "Objective stem"
    assert content.correct_answer == [key for key, _text in options if key in correct_answer]


@pytest.mark.parametrize(
    "overrides",
    [
        {"correct_answer": ["Z"]},
        {"correct_answer": ["A", "B"]},
        {"options": [("A", "One"), ("A", "Duplicate")]},
        {"stem": " "},
        {"explanation": " "},
    ],
)
def test_invalid_question_content_is_rejected(overrides) -> None:
    values = {
        "question_type": QuestionType.SINGLE_CHOICE,
        "stem": "Stem",
        "options": [("A", "One"), ("B", "Two")],
        "correct_answer": ["A"],
        "explanation": "Explanation",
        "difficulty": QuestionDifficulty.EASY,
    }
    values.update(overrides)
    values["options"] = [QuestionOptionSchema(key=key, text=text) for key, text in values["options"]]
    with pytest.raises(ValidationError):
        QuestionContentSchema(**values)


def test_question_creation_primary_binding_and_candidate_redaction(database) -> None:
    factory, seed = database
    with factory() as session:
        service = DiagnosticDomainService(session)
        question = service.create_question(seed.owner_id, seed.course_id, create_payload(seed.node_id))
        stored = QuestionRepository(session).get_for_owner(question.id, seed.owner_id)
        assert stored is not None
        assert stored.content_version == 1
        assert [(link.knowledge_node_id, link.relation_role) for link in stored.knowledge_links] == [
            (seed.node_id, KnowledgeRelationRole.PRIMARY)
        ]
        candidate = CandidateQuestionSchema(
            question_type=stored.question_type,
            stem=stored.stem,
            options=stored.options,
            difficulty=stored.difficulty,
            order_index=0,
        ).model_dump()
        assert "correct_answer" not in candidate
        assert "explanation" not in candidate
        assert "scoring_policy" not in candidate


def test_question_binding_rejects_cross_course_and_duplicate_nodes(database) -> None:
    factory, seed = database
    with factory() as session:
        with session.begin():
            foreign = KnowledgeNode(
                course_id=seed.other_course_id,
                name="Foreign",
                normalized_name="foreign",
                description="",
                importance=KnowledgeImportance.MEDIUM,
                difficulty=KnowledgeDifficulty.BASIC,
                is_active=True,
                managed_by_canonicalization=False,
            )
            session.add(foreign)
        service = DiagnosticDomainService(session)
        with pytest.raises(DiagnosticDomainError) as mismatch:
            service.create_question(seed.owner_id, seed.course_id, create_payload(foreign.id))
        assert mismatch.value.code == "QUESTION_KNOWLEDGE_COURSE_MISMATCH"

        with pytest.raises(ValidationError):
            QuestionCreateSchema(
                content=single_choice_content(),
                knowledge_nodes=[
                    QuestionKnowledgeBindingSchema(
                        knowledge_node_id=seed.node_id, relation_role=KnowledgeRelationRole.PRIMARY
                    ),
                    QuestionKnowledgeBindingSchema(
                        knowledge_node_id=seed.node_id, relation_role=KnowledgeRelationRole.SECONDARY
                    ),
                ],
            )


def test_lifecycle_rejects_skips_and_locks_submitted_responses(database) -> None:
    factory, seed = database
    with factory() as session:
        service = DiagnosticDomainService(session)
        assessment = service.create_assessment_draft(seed.owner_id, seed.course_id)
        assessment_id = assessment.id
        with pytest.raises(DiagnosticDomainError) as start_error:
            service.start_assessment(seed.owner_id, assessment_id)
        assert start_error.value.code == "ASSESSMENT_INVALID_TRANSITION"

        question = service.create_question(seed.owner_id, seed.course_id, create_payload(seed.node_id))
        snapshots = service.fix_question_snapshots(seed.owner_id, assessment_id, [question.id])
        snapshot_id = snapshots[0].id
        with pytest.raises(DiagnosticDomainError):
            service.fix_question_snapshots(seed.owner_id, assessment_id, [question.id])
        service.start_assessment(seed.owner_id, assessment_id)
        response = service.save_draft_response(
            seed.owner_id, assessment_id, snapshot_id, ObjectiveAnswerSchema(selected_options=["A"])
        )
        updated = service.save_draft_response(
            seed.owner_id, assessment_id, snapshot_id, ObjectiveAnswerSchema(selected_options=["B"])
        )
        assert updated.id == response.id
        assert updated.answer_payload["selected_options"] == ["B"]
        submitted = service.submit_assessment(seed.owner_id, assessment_id)
        assert submitted.status == AssessmentStatus.SUBMITTED
        assert submitted.submitted_at is not None
        assert service.submit_assessment(seed.owner_id, assessment_id).id == assessment_id
        with pytest.raises(DiagnosticDomainError) as locked:
            service.save_draft_response(
                seed.owner_id, assessment_id, snapshot_id, ObjectiveAnswerSchema(selected_options=["A"])
            )
        assert locked.value.code == "ASSESSMENT_INVALID_TRANSITION"


def test_repeated_submission_is_idempotent_only_for_identical_answers(database) -> None:
    factory, seed = database
    with factory() as session:
        service, _questions, assessment, snapshots = prepare_assessment(session, seed)
        assessment_id = assessment.id
        snapshot_id = snapshots[0].id
        service.submit_assessment(
            seed.owner_id,
            assessment_id,
            {snapshot_id: ObjectiveAnswerSchema(selected_options=["B"])},
        )

    with factory() as session:
        service = DiagnosticDomainService(session)
        same = {snapshot_id: ObjectiveAnswerSchema(selected_options=["B"])}
        assert service.submit_assessment(seed.owner_id, assessment_id, same).status == AssessmentStatus.SUBMITTED

    with factory() as session:
        service = DiagnosticDomainService(session)
        with pytest.raises(DiagnosticDomainError) as changed:
            service.submit_assessment(
                seed.owner_id,
                assessment_id,
                {snapshot_id: ObjectiveAnswerSchema(selected_options=["A"])},
            )
        assert changed.value.code == "ASSESSMENT_ALREADY_SUBMITTED"


def test_historical_snapshot_survives_question_update_node_rebuild_and_source_delete(database) -> None:
    factory, seed = database
    with factory() as session:
        service = DiagnosticDomainService(session)
        question = service.create_question(seed.owner_id, seed.course_id, create_payload(seed.node_id))
        assessment = service.create_assessment_draft(seed.owner_id, seed.course_id)
        snapshot_row = service.fix_question_snapshots(seed.owner_id, assessment.id, [question.id])[0]
        assessment_id = assessment.id
        snapshot_id = snapshot_row.id
        question_id = question.id

    with factory() as session:
        service = DiagnosticDomainService(session)
        service.update_question_content(
            seed.owner_id,
            question_id,
            single_choice_content(stem="Question V2", answer="A"),
        )
        with session.begin():
            old_node = session.get(KnowledgeNode, seed.node_id)
            assert old_node is not None
            session.delete(old_node)
            replacement = KnowledgeNode(
                course_id=seed.course_id,
                name="Replacement Policy V2",
                normalized_name="replacement policy v2",
                description="rebuilt",
                importance=KnowledgeImportance.HIGH,
                difficulty=KnowledgeDifficulty.ADVANCED,
                is_active=True,
                managed_by_canonicalization=True,
            )
            session.add(replacement)
        service.delete_question(seed.owner_id, question_id)

    with factory() as session:
        assessment, snapshots, responses = DiagnosticDomainService(session).read_history(seed.owner_id, assessment_id)
        assert assessment.status == AssessmentStatus.READY
        assert responses == []
        assert snapshots[0].id == snapshot_id
        assert snapshots[0].question_id is None
        historical = AssessmentQuestionSnapshotSchema.model_validate(snapshots[0].question_snapshot)
        assert historical.stem == "Which block does LRU replace?"
        assert historical.correct_answer == ["B"]
        assert historical.explanation == "LRU replaces the block unused for the longest time."
        assert historical.knowledge_nodes[0].id == seed.node_id
        assert historical.knowledge_nodes[0].name == "LRU Replacement"
        assert historical.scoring_policy.version == "objective_exact_match_v1"
        assert historical.source_question_version == 1
        assert historical.knowledge_model_version == "canonical-run-7"


def test_response_validation_ownership_and_assessment_isolation(database) -> None:
    factory, seed = database
    with factory() as session:
        service, _questions, assessment, snapshots = prepare_assessment(session, seed)
        assessment_id = assessment.id
        source_snapshot_id = snapshots[0].id
        other_question = service.create_question(seed.owner_id, seed.course_id, create_payload(seed.node_id))
        other = service.create_assessment_draft(seed.owner_id, seed.course_id)
        other_id = other.id
        service.fix_question_snapshots(seed.owner_id, other_id, [other_question.id])
        service.start_assessment(seed.owner_id, other_id)
        with pytest.raises(DiagnosticDomainError) as wrong_owner:
            service.read_history(seed.other_owner_id, assessment_id)
        assert wrong_owner.value.code == "ASSESSMENT_NOT_FOUND"
        with pytest.raises(DiagnosticDomainError) as wrong_assessment:
            service.save_draft_response(
                seed.owner_id,
                other_id,
                source_snapshot_id,
                ObjectiveAnswerSchema(selected_options=["A"]),
            )
        assert wrong_assessment.value.code == "ASSESSMENT_QUESTION_NOT_FOUND"
        with pytest.raises(DiagnosticDomainError) as invalid_key:
            service.save_draft_response(
                seed.owner_id,
                assessment_id,
                source_snapshot_id,
                ObjectiveAnswerSchema(selected_options=["Z"]),
            )
        assert invalid_key.value.code == "ANSWER_INVALID"


def test_submission_transaction_rolls_back_all_answer_changes(database) -> None:
    factory, seed = database
    with factory() as session:
        service, _questions, assessment, snapshots = prepare_assessment(session, seed, question_count=2)
        assessment_id = assessment.id
        for item in snapshots:
            service.save_draft_response(
                seed.owner_id, assessment_id, item.id, ObjectiveAnswerSchema(selected_options=["A"])
            )
        with pytest.raises(DiagnosticDomainError) as invalid:
            service.submit_assessment(
                seed.owner_id,
                assessment_id,
                {
                    snapshots[0].id: ObjectiveAnswerSchema(selected_options=["B"]),
                    snapshots[1].id: ObjectiveAnswerSchema(selected_options=["Z"]),
                },
            )
        assert invalid.value.code == "ANSWER_INVALID"

    with factory() as session:
        stored = session.get(Assessment, assessment_id)
        answers = list(session.scalars(select(Response).where(Response.assessment_id == assessment_id)))
        assert stored is not None and stored.status == AssessmentStatus.IN_PROGRESS
        assert [item.answer_payload["selected_options"] for item in answers] == [["A"], ["A"]]
        assert all(item.submitted_at is None for item in answers)


def test_database_constraints_reject_duplicate_response_and_cross_assessment_reference(database) -> None:
    factory, seed = database
    with factory() as session:
        service, _questions, assessment, snapshots = prepare_assessment(session, seed)
        service.save_draft_response(
            seed.owner_id, assessment.id, snapshots[0].id, ObjectiveAnswerSchema(selected_options=["A"])
        )
        other_question = service.create_question(seed.owner_id, seed.course_id, create_payload(seed.node_id))
        other = service.create_assessment_draft(seed.owner_id, seed.course_id)
        other_snapshot = service.fix_question_snapshots(seed.owner_id, other.id, [other_question.id])[0]

        with pytest.raises(IntegrityError):
            with session.begin():
                session.add(
                    Response(
                        assessment_id=assessment.id,
                        assessment_question_id=snapshots[0].id,
                        answer_payload={"schema_version": "objective_answer_v1", "selected_options": ["B"]},
                        answered_at=assessment.started_at,
                    )
                )
        with pytest.raises(IntegrityError):
            with session.begin():
                session.add(
                    Response(
                        assessment_id=assessment.id,
                        assessment_question_id=other_snapshot.id,
                        answer_payload={"schema_version": "objective_answer_v1", "selected_options": ["A"]},
                        answered_at=assessment.started_at,
                    )
                )


def test_fresh_migration_contains_m4a_constraints(tmp_path: Path) -> None:
    database_url = migrate_database(tmp_path / "fresh.sqlite3")
    engine = make_engine(database_url)
    inspector = inspect(engine)
    assert {"questions", "question_knowledge_nodes", "assessments", "assessment_questions", "responses"}.issubset(
        inspector.get_table_names()
    )
    assert "assessment_status" in {item["name"] for item in inspector.get_check_constraints("assessments")}
    assert "ck_assessment_questions_order_index" in {
        item["name"] for item in inspector.get_check_constraints("assessment_questions")
    }
    assert "uq_responses_assessment_question_id" in {
        item["name"] for item in inspector.get_unique_constraints("responses")
    }
    engine.dispose()


def test_populated_m3_upgrades_without_data_loss(tmp_path: Path) -> None:
    path = tmp_path / "upgrade.sqlite3"
    database_url = migrate_database(path, "0007_m3e_workspace_build_state")
    engine = make_engine(database_url)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session, session.begin():
        owner = User(email="m3-owner@example.test", display_name="M3 Owner", is_active=True)
        session.add(owner)
        session.flush()
        course = Course(owner_id=owner.id, name="M3 Course", description="preserve")
        session.add(course)
        session.flush()
        material = Material(
            course_id=course.id,
            title="M3 Material",
            material_type="txt",
            summary="",
            storage_status="NOT_STORED",
            extraction_status="NOT_REQUESTED",
        )
        node = KnowledgeNode(
            course_id=course.id,
            name="M3 Node",
            normalized_name="m3 node",
            description="",
            importance=KnowledgeImportance.MEDIUM,
            difficulty=KnowledgeDifficulty.BASIC,
            is_active=True,
            managed_by_canonicalization=False,
        )
        session.add_all([material, node])
        session.flush()
        ids = (course.id, material.id, node.id)
    engine.dispose()

    migrate_database(path)
    engine = make_engine(database_url)
    with sessionmaker(bind=engine)() as session:
        assert session.get(Course, ids[0]).name == "M3 Course"
        assert session.get(Material, ids[1]).title == "M3 Material"
        assert session.get(KnowledgeNode, ids[2]).name == "M3 Node"
    assert "assessments" in inspect(engine).get_table_names()
    engine.dispose()


def test_database_rejects_duplicate_question_node_link(database) -> None:
    factory, seed = database
    with factory() as session:
        question = DiagnosticDomainService(session).create_question(
            seed.owner_id, seed.course_id, create_payload(seed.node_id)
        )
        with pytest.raises(IntegrityError):
            with session.begin():
                session.add(
                    QuestionKnowledgeNode(
                        course_id=seed.course_id,
                        question_id=question.id,
                        knowledge_node_id=seed.node_id,
                        relation_role=KnowledgeRelationRole.SECONDARY,
                    )
                )


def test_repository_has_no_snapshot_update_or_submitted_response_mutator() -> None:
    assert not hasattr(AssessmentRepository, "update_assessment_question")
    assert not hasattr(AssessmentRepository, "update_question_snapshot")
    assert not hasattr(QuestionRepository, "score")
