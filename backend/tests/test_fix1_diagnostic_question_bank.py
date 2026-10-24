from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from backend.app.ai import AIServiceError
from backend.app.api.diagnostics import (
    approve_diagnostic_question,
    generate_diagnostic_question,
    list_diagnostic_questions,
    prepare_course_diagnostic_questions,
    reject_diagnostic_question,
)
from backend.app.core.errors import ApiError
from backend.app.core.settings import Settings
from backend.app.db.models import KnowledgeNode, KnowledgeSource, Question, QuestionKnowledgeNode
from backend.app.models import (
    KnowledgeDifficulty,
    KnowledgeImportance,
    KnowledgeRelationRole,
    QuestionDifficulty,
    QuestionType,
    QuestionValidationStatus,
)
from backend.app.schemas.question_generation import DiagnosticQuestionGenerateRequestSchema
from backend.app.services.diagnostic_question_bank_service import (
    DiagnosticQuestionBankError,
    DiagnosticQuestionBankService,
)
from backend.main import app
from backend.tests.test_m4b_question_generation import (
    ScriptedLLMClient,
    Seed,
    candidate,
)
from backend.tests.test_m4b_question_generation import (
    database as m4b_database,
)

database = m4b_database


def _settings() -> Settings:
    return Settings(
        database_url="sqlite+pysqlite:///:memory:",
        legacy_bootstrap_user="m4b-owner@example.test",
        llm_max_attempts=1,
        diagnostic_question_max_count=4,
        diagnostic_question_similarity_threshold=0.9,
    )


def _service(session: Session, client: ScriptedLLMClient | None = None) -> DiagnosticQuestionBankService:
    factory = (lambda _settings: client) if client is not None else None
    return DiagnosticQuestionBankService(session, _settings(), factory)


def _add_question(
    session: Session,
    *,
    course_id: int,
    node_id: int,
    material_id: int,
    stem: str,
    status: QuestionValidationStatus,
) -> Question:
    question = Question(
        course_id=course_id,
        question_type=QuestionType.SINGLE_CHOICE,
        stem=stem,
        options=[
            {"key": "A", "text": "Correct option"},
            {"key": "B", "text": "Incorrect option"},
        ],
        correct_answer=["A"],
        explanation="Grounded explanation for the correct option.",
        difficulty=QuestionDifficulty.EASY,
        validation_status=status,
        source_refs=[
            {
                "material_id": material_id,
                "material_title": "Course notes",
                "source_reference": "PDF 第2页",
                "excerpt": "Verified course evidence.",
            }
        ],
        generation_metadata={"prompt_version": "diagnostic_questions_v1"},
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
    return question


def _seed_readiness_nodes(factory: sessionmaker[Session], seed: Seed) -> list[int]:
    with factory() as session, session.begin():
        for index in range(8):
            session.add(
                KnowledgeNode(
                    course_id=seed.course_id,
                    name=f"High core {index}",
                    normalized_name=f"high core {index}",
                    description="Core diagnostic topic.",
                    importance=KnowledgeImportance.HIGH,
                    difficulty=KnowledgeDifficulty.BASIC,
                    is_active=True,
                    managed_by_canonicalization=True,
                )
            )
        session.flush()
        nodes = list(
            session.scalars(
                select(KnowledgeNode)
                .where(
                    KnowledgeNode.course_id == seed.course_id,
                    KnowledgeNode.is_active.is_(True),
                    KnowledgeNode.importance == KnowledgeImportance.HIGH,
                )
                .order_by(KnowledgeNode.id)
            )
        )
        return [node.id for node in nodes]


def test_generation_api_creates_pending_and_blocks_duplicate_pending(database) -> None:
    factory, seed = database
    payload = candidate(seed, difficulty=QuestionDifficulty.MEDIUM)
    llm = ScriptedLLMClient([{"questions": [payload]}])

    with factory() as session:
        service = _service(session, llm)
        response = generate_diagnostic_question(
            seed.course_id,
            DiagnosticQuestionGenerateRequestSchema(knowledge_node_id=seed.node_id),
            service,
        )
        assert response.accepted_count == 1
        assert response.questions[0].validation_status == QuestionValidationStatus.PENDING

        with pytest.raises(ApiError) as captured:
            generate_diagnostic_question(
                seed.course_id,
                DiagnosticQuestionGenerateRequestSchema(knowledge_node_id=seed.node_id),
                service,
            )
        assert captured.value.status_code == 409
        assert captured.value.code == "QUESTION_INVALID_STATE"
        assert llm.calls == 1

    with factory() as session:
        assert session.scalar(select(func.count(Question.id))) == 1


def test_question_listing_filters_and_review_api_exposes_answers(database) -> None:
    factory, seed = database
    llm = ScriptedLLMClient([{"questions": [candidate(seed, difficulty=QuestionDifficulty.MEDIUM)]}])
    with factory() as session:
        service = _service(session, llm)
        generated = generate_diagnostic_question(
            seed.course_id,
            DiagnosticQuestionGenerateRequestSchema(knowledge_node_id=seed.node_id),
            service,
        )
        question_id = generated.questions[0].question_id

        pending = list_diagnostic_questions(
            seed.course_id,
            QuestionValidationStatus.PENDING,
            service,
        )
        assert pending.count == 1
        assert pending.questions[0].correct_answer == ["B"]
        assert pending.questions[0].explanation

        validated = list_diagnostic_questions(
            seed.course_id,
            QuestionValidationStatus.VALIDATED,
            service,
        )
        assert validated.count == 0

        approved = approve_diagnostic_question(seed.course_id, question_id, service)
        assert approved.question.validation_status == QuestionValidationStatus.VALIDATED

        with pytest.raises(ApiError) as captured:
            approve_diagnostic_question(seed.course_id, question_id, service)
        assert captured.value.status_code == 409
        assert captured.value.code == "QUESTION_INVALID_STATE"


def test_pending_question_can_be_rejected_but_not_rejected_twice(database) -> None:
    factory, seed = database
    llm = ScriptedLLMClient([{"questions": [candidate(seed, difficulty=QuestionDifficulty.MEDIUM)]}])
    with factory() as session:
        service = _service(session, llm)
        generated = generate_diagnostic_question(
            seed.course_id,
            DiagnosticQuestionGenerateRequestSchema(knowledge_node_id=seed.node_id),
            service,
        )
        question_id = generated.questions[0].question_id
        rejected = reject_diagnostic_question(seed.course_id, question_id, service)
        assert rejected.question.validation_status == QuestionValidationStatus.REJECTED

        with pytest.raises(ApiError) as captured:
            reject_diagnostic_question(seed.course_id, question_id, service)
        assert captured.value.status_code == 409
        assert captured.value.code == "QUESTION_INVALID_STATE"


def test_cross_course_generation_listing_and_review_are_hidden(database) -> None:
    factory, seed = database
    llm = ScriptedLLMClient([{"questions": [candidate(seed, difficulty=QuestionDifficulty.MEDIUM)]}])
    with factory() as session:
        service = _service(session, llm)
        with pytest.raises(ApiError) as listing:
            list_diagnostic_questions(seed.other_course_id, None, service)
        assert listing.value.status_code == 404

        with pytest.raises(ApiError) as generation:
            generate_diagnostic_question(
                seed.course_id,
                DiagnosticQuestionGenerateRequestSchema(knowledge_node_id=seed.foreign_node_id),
                service,
            )
        assert generation.value.status_code == 404
        assert llm.calls == 0


def test_approval_revalidates_current_sources(database) -> None:
    factory, seed = database
    llm = ScriptedLLMClient([{"questions": [candidate(seed, difficulty=QuestionDifficulty.MEDIUM)]}])
    with factory() as session:
        service = _service(session, llm)
        generated = service.generate_pending(course_id=seed.course_id, knowledge_node_id=seed.node_id)
        question_id = generated.questions[0].question_id

    with factory() as session, session.begin():
        node = session.get(KnowledgeNode, seed.node_id)
        assert node is not None
        for source in list(node.sources):
            session.delete(source)

    with factory() as session:
        with pytest.raises(DiagnosticQuestionBankError) as captured:
            _service(session).approve(seed.course_id, question_id)
        assert captured.value.code == "QUESTION_SOURCE_INVALID"
        question = session.get(Question, question_id)
        assert question is not None
        assert question.validation_status == QuestionValidationStatus.PENDING


@pytest.mark.parametrize("pending_index", [None, 7])
def test_readiness_reuses_validated_count_and_required_node_coverage(database, pending_index) -> None:
    factory, seed = database
    high_node_ids = _seed_readiness_nodes(factory, seed)
    required_ids = high_node_ids[:8]
    with factory() as session, session.begin():
        for index, node_id in enumerate(required_ids):
            status = QuestionValidationStatus.PENDING if pending_index == index else QuestionValidationStatus.VALIDATED
            _add_question(
                session,
                course_id=seed.course_id,
                node_id=node_id,
                material_id=seed.material_id,
                stem=f"Deterministic core diagnostic question {index}?",
                status=status,
            )

    with factory() as session:
        readiness = _service(session).readiness(seed.course_id)
        assert readiness.can_start is (pending_index is None)
        assert readiness.covered_core_nodes == (8 if pending_index is None else 7)
        assert readiness.pending_count == (0 if pending_index is None else 1)
        assert [node.knowledge_node_id for node in readiness.required_nodes] == required_ids


def test_ninth_validated_question_requires_ninth_core_node_coverage(database) -> None:
    factory, seed = database
    high_node_ids = _seed_readiness_nodes(factory, seed)
    with factory() as session, session.begin():
        for index, node_id in enumerate(high_node_ids[:8]):
            _add_question(
                session,
                course_id=seed.course_id,
                node_id=node_id,
                material_id=seed.material_id,
                stem=f"Covered core diagnostic question {index}?",
                status=QuestionValidationStatus.VALIDATED,
            )
        _add_question(
            session,
            course_id=seed.course_id,
            node_id=high_node_ids[0],
            material_id=seed.material_id,
            stem="Additional unique question on an already covered core node?",
            status=QuestionValidationStatus.VALIDATED,
        )

    with factory() as session:
        readiness = _service(session).readiness(seed.course_id)
        assert readiness.validated_count == 9
        assert readiness.required_questions == 9
        assert readiness.can_start is False
        assert len(readiness.required_nodes) == 9
        assert readiness.required_nodes[-1].knowledge_node_id == high_node_ids[8]
        assert readiness.required_nodes[-1].has_validated_question is False


def test_unconfigured_provider_and_invalid_output_leave_no_questions(database) -> None:
    factory, seed = database
    with factory() as session:
        service = DiagnosticQuestionBankService(
            session,
            Settings(
                database_url="sqlite+pysqlite:///:memory:",
                legacy_bootstrap_user="m4b-owner@example.test",
                llm_mode="provider",
                llm_api_key="",
                llm_base_url="",
                llm_model="",
                llm_max_attempts=1,
            ),
        )
        with pytest.raises(ApiError) as unconfigured:
            generate_diagnostic_question(
                seed.course_id,
                DiagnosticQuestionGenerateRequestSchema(knowledge_node_id=seed.node_id),
                service,
            )
        assert unconfigured.value.code == "AI_NOT_CONFIGURED"

    malformed = ScriptedLLMClient([{"questions": [{"stem": "missing fields"}]}])
    with factory() as session:
        with pytest.raises(ApiError) as invalid:
            generate_diagnostic_question(
                seed.course_id,
                DiagnosticQuestionGenerateRequestSchema(knowledge_node_id=seed.node_id),
                _service(session, malformed),
            )
        assert invalid.value.code == "QUESTION_INVALID_OUTPUT"

    with factory() as session:
        assert session.scalar(select(func.count(Question.id))) == 0


def test_approval_rejects_missing_primary_link(database) -> None:
    factory, seed = database
    llm = ScriptedLLMClient([{"questions": [candidate(seed, difficulty=QuestionDifficulty.MEDIUM)]}])
    with factory() as session:
        generated = _service(session, llm).generate_pending(
            course_id=seed.course_id,
            knowledge_node_id=seed.node_id,
        )
        question_id = generated.questions[0].question_id

    with factory() as session, session.begin():
        question = session.get(Question, question_id)
        assert question is not None
        for link in list(question.knowledge_links):
            session.delete(link)

    with factory() as session:
        with pytest.raises(DiagnosticQuestionBankError) as captured:
            _service(session).approve(seed.course_id, question_id)
        assert captured.value.code == "QUESTION_ALIGNMENT_INVALID"
        question = session.get(Question, question_id)
        assert question is not None
        assert question.validation_status == QuestionValidationStatus.PENDING


def test_cross_course_question_review_is_hidden(database) -> None:
    factory, seed = database
    with factory() as session, session.begin():
        foreign = _add_question(
            session,
            course_id=seed.other_course_id,
            node_id=seed.foreign_node_id,
            material_id=seed.foreign_material_id,
            stem="Foreign pending diagnostic question?",
            status=QuestionValidationStatus.PENDING,
        )
        foreign_id = foreign.id

    with factory() as session:
        with pytest.raises(ApiError) as captured:
            approve_diagnostic_question(seed.other_course_id, foreign_id, _service(session))
        assert captured.value.status_code == 404
        assert captured.value.code == "COURSE_NOT_FOUND"


def test_question_bank_routes_are_registered_with_expected_methods() -> None:
    paths = app.openapi()["paths"]
    assert "get" in paths["/api/diagnostics/courses/{course_id}/question-bank"]
    assert {"get"} <= set(paths["/api/diagnostics/courses/{course_id}/questions"])
    assert "post" in paths["/api/diagnostics/courses/{course_id}/questions/generate"]
    assert "post" in paths["/api/diagnostics/courses/{course_id}/questions/prepare"]
    assert "post" in paths["/api/diagnostics/courses/{course_id}/questions/{question_id}/approve"]
    assert "post" in paths["/api/diagnostics/courses/{course_id}/questions/{question_id}/reject"]


def test_course_preparation_plans_missing_nodes_once_and_creates_pending_questions(database) -> None:
    factory, seed = database
    with factory() as session, session.begin():
        secondary = session.get(KnowledgeNode, seed.secondary_node_id)
        assert secondary is not None
        secondary.importance = KnowledgeImportance.HIGH
        secondary_source = session.scalar(
            select(KnowledgeSource).where(KnowledgeSource.knowledge_node_id == secondary.id)
        )
        assert secondary_source is not None
        secondary_material_id = secondary_source.material_id
        secondary_reference = secondary_source.source_reference

    outputs = [
        {
            "questions": [
                candidate(
                    seed,
                    question_type=QuestionType.SINGLE_CHOICE,
                    difficulty=QuestionDifficulty.MEDIUM,
                )
            ]
        },
        {
            "questions": [
                candidate(
                    seed,
                    question_type=QuestionType.TRUE_FALSE,
                    difficulty=QuestionDifficulty.EASY,
                    stem="A cache hit means requested data is already cached.",
                    node_id=seed.secondary_node_id,
                    material_id=secondary_material_id,
                    source_reference=secondary_reference,
                )
            ]
        },
    ]
    llm = ScriptedLLMClient(outputs)

    with factory() as session:
        service = _service(session, llm)
        response = prepare_course_diagnostic_questions(seed.course_id, service)
        assert response.planned_count == 2
        assert response.generated_count == 2
        assert response.failed_count == 0
        assert response.pending_review_count == 2
        assert {item.knowledge_node_id for item in response.questions} == {
            seed.node_id,
            seed.secondary_node_id,
        }
        assert all(item.validation_status == QuestionValidationStatus.PENDING for item in response.questions)

        repeated = prepare_course_diagnostic_questions(seed.course_id, service)
        assert repeated.planned_count == 0
        assert repeated.generated_count == 0
        assert repeated.pending_review_count == 2
        assert llm.calls == 2


def test_course_preparation_reports_partial_failure_without_rolling_back_valid_items(database) -> None:
    factory, seed = database
    with factory() as session, session.begin():
        secondary = session.get(KnowledgeNode, seed.secondary_node_id)
        assert secondary is not None
        secondary.importance = KnowledgeImportance.HIGH

    llm = ScriptedLLMClient(
        [
            {
                "questions": [
                    candidate(
                        seed,
                        question_type=QuestionType.SINGLE_CHOICE,
                        difficulty=QuestionDifficulty.MEDIUM,
                    )
                ]
            },
            AIServiceError("AI_PROVIDER_ERROR", "Provider unavailable.", retryable=False),
        ]
    )
    with factory() as session:
        response = _service(session, llm).prepare_course(seed.course_id)
        assert response.planned_count == 2
        assert response.generated_count == 1
        assert response.failed_count == 1
        assert response.failures[0].knowledge_node_id == seed.secondary_node_id
        assert response.failures[0].code == "AI_PROVIDER_ERROR"

    with factory() as session:
        stored = list(session.scalars(select(Question)))
        assert len(stored) == 1
        assert stored[0].validation_status == QuestionValidationStatus.PENDING
