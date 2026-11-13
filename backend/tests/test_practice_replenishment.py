import pytest
from sqlalchemy import func, select, update

from backend.app.ai import AIServiceError
from backend.app.db.models import (
    CourseKnowledgeBuildState,
    KnowledgeEdge,
    LearningEvidence,
    Question,
    StudentKnowledgeState,
)
from backend.app.models import ConfidenceLevel, KnowledgeRelationType, QuestionDifficulty, QuestionValidationStatus
from backend.app.repositories import QuestionRepository
from backend.app.schemas.learning_session import LearningSessionCreate
from backend.app.services.adaptive_practice_service import AdaptivePracticeService
from backend.app.services.diagnostic_question_bank_service import (
    DiagnosticQuestionBankError,
    DiagnosticQuestionBankService,
)
from backend.app.services.diagnostic_question_generation import DiagnosticQuestionGenerationService
from backend.app.services.learning_plan_service import LearningPlanService
from backend.app.services.learning_session_service import LearningSessionService
from backend.app.services.learning_settlement_service import LearningSettlementService
from backend.tests.test_m4b_question_generation import ScriptedLLMClient, Seed, _add_material_source, candidate
from backend.tests.test_m7_4_adaptive_practice import _answer, _next, _ready_session, _settings
from backend.tests.test_m7_4_adaptive_practice import practice_database as practice_database
from backend.tests.test_m7_5_settlement import _finished


def _add_generation_context(factory, ids):
    with factory() as db, db.begin():
        db.add(CourseKnowledgeBuildState(course_id=ids["course"], status="success"))
        return _add_material_source(
            db,
            course_id=ids["course"],
            node_id=ids["cache"],
            title="Cache notes",
            extension="pdf",
            reference="PDF 第2页",
            text="LRU evicts the block whose last access was longest ago.",
        )


def _next_with_provider(factory, url, session_id, output):
    with factory() as db:
        settings = _settings(url)

        class TransactionCheckingClient(ScriptedLLMClient):
            def generate_structured(self, **kwargs):
                assert not db.in_transaction()
                return super().generate_structured(**kwargs)

        client = TransactionCheckingClient([output])
        generator = DiagnosticQuestionGenerationService(
            db, settings.model_copy(update={"llm_max_attempts": 1}), lambda _settings: client
        )
        result = AdaptivePracticeService(db, settings, question_generator=generator).start_or_next_for_configured_user(
            session_id
        )
    assert client.calls == 1
    return result


def test_practice_replenishes_with_checked_content_and_keeps_independent_evidence(practice_database):
    factory, ids, correct, url = practice_database
    material_id = _add_generation_context(factory, ids)
    first_id = _finished(factory, ids, correct, url)
    with factory() as db:
        finished = LearningSessionService(db, _settings(url)).get_for_configured_user(first_id)
        assert finished.tasks[-1].progress["completion_reason"] == "question_limit"
        assert finished.status.value == "in_progress"
    with factory() as db:
        LearningSettlementService(db, _settings(url)).complete_for_configured_user(first_id)
    with factory() as db, db.begin():
        db.execute(
            update(Question)
            .where(Question.course_id == ids["course"])
            .values(validation_status=QuestionValidationStatus.REJECTED)
        )
        db.add(
            KnowledgeEdge(
                course_id=ids["course"],
                source_node_id=ids["cache"],
                target_node_id=ids["empty"],
                relation_type=KnowledgeRelationType.PREREQUISITE,
            )
        )
        before = db.scalar(select(StudentKnowledgeState))
        assert before.independent_evidence_count == 5
        assert before.confidence_level == ConfidenceLevel.LOW
    session_id = _ready_session(factory, ids, url)
    seed = Seed()
    draft = candidate(seed, node_id=ids["cache"], material_id=material_id, difficulty=QuestionDifficulty.EASY)
    state = _next_with_provider(factory, url, session_id, {"questions": [draft]})
    question = state.current_question
    assert question is not None and question.auto_checked
    with factory() as db, db.begin():
        generated = db.get(Question, question.question_id)
        assert generated.validation_status == QuestionValidationStatus.PENDING
        assert generated.generation_metadata["practice_only"] is True
        assert generated.generation_metadata["validation"] == "auto_checked"
        assert generated.generation_metadata["semantic_review"] == "not_human_verified"
        assert not QuestionRepository(db).list_validated_for_course(ids["course"])
    with factory() as db:
        bank = DiagnosticQuestionBankService(db, _settings(url))
        assert bank.list_questions(ids["course"]).count == len(correct)
        with pytest.raises(DiagnosticQuestionBankError, match="Practice-only"):
            bank.approve(ids["course"], question.question_id)

    answer = draft["correct_answer"]
    completed = _answer(factory, url, session_id, question.assessment_question_id, answer)
    assert completed.completion_reason == "mastered" and completed.answered_count == 1
    assert completed.attempts[0].auto_checked
    replay = _answer(factory, url, session_id, question.assessment_question_id, answer)
    assert replay.reused and replay.completion_reason == "mastered"
    with factory() as db:
        evidence = list(db.scalars(select(LearningEvidence)))
        assert len({row.source_question_snapshot_id for row in evidence}) == len(evidence) == 6
        after = db.scalar(select(StudentKnowledgeState))
        assert after.independent_evidence_count == 6
        assert after.confidence_level == ConfidenceLevel.MEDIUM
        assert after.mastery_score >= 80
    with factory() as db:
        settings = _settings(url)
        service = LearningSessionService(db, settings)
        finished = service.get_for_configured_user(session_id)
        assert finished.status.value == "completed"
        assert finished.recommendation_refresh_status.value == "succeeded"
        assert finished.completion_summary["recommendation"]["knowledge_node_id"] == ids["empty"]
        recommendation = service.continuation_for_configured_user(session_id, set()).recommendation
        assert recommendation is not None and recommendation.knowledge_node_id == ids["empty"]
        plan = LearningPlanService(db, settings).get_current_for_configured_user(ids["course"]).plan
        assert plan is not None and plan.target_node_id == ids["empty"]
        next_session = service.create_for_configured_user(
            LearningSessionCreate(course_id=ids["course"], learning_plan_id=plan.plan_id)
        )
        assert next_session.target_knowledge_node_id == ids["empty"]


def test_generation_failure_pauses_existing_practice_without_losing_evidence(practice_database):
    factory, ids, correct, url = practice_database
    material_id = _add_generation_context(factory, ids)
    first_id = min(correct)
    with factory() as db, db.begin():
        db.execute(
            update(Question)
            .where(Question.course_id == ids["course"], Question.id != first_id)
            .values(validation_status=QuestionValidationStatus.REJECTED)
        )
    session_id = _ready_session(factory, ids, url)
    first = _next(factory, url, session_id).current_question
    assert first is not None and first.question_id == first_id
    _answer(factory, url, session_id, first.assessment_question_id, correct[first_id])
    paused = _next_with_provider(factory, url, session_id, AIServiceError("AI_TIMEOUT", "Fake timeout", retryable=True))
    assert paused.status == "question_bank_empty" and paused.answered_count == 1
    assert paused.current_question is None and paused.completion_reason is None
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(LearningEvidence)) == 1
        state = db.scalar(select(StudentKnowledgeState))
        assert state.confidence_level == ConfidenceLevel.INSUFFICIENT and state.mastery_score is None
    with factory() as db:
        assert (
            LearningSessionService(db, _settings(url)).get_for_configured_user(session_id).status.value == "in_progress"
        )

    draft = candidate(Seed(), node_id=ids["cache"], material_id=material_id, difficulty=paused.current_difficulty)
    resumed = _next_with_provider(factory, url, session_id, {"questions": [draft]})
    second = resumed.current_question
    assert resumed.assessment_id == paused.assessment_id and resumed.answered_count == 1
    assert second is not None and second.auto_checked and second.stem != first.stem
    answered = _answer(factory, url, session_id, second.assessment_question_id, draft["correct_answer"])
    assert answered.status == "in_progress" and answered.answered_count == 2
    with factory() as db:
        rows = list(db.scalars(select(LearningEvidence)))
        assert {row.source_question_snapshot_id for row in rows} == {
            first.assessment_question_id,
            second.assessment_question_id,
        }
