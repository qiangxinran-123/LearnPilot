from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select, update

from backend.app.db.models import LearningEvidence, LearningSession, Question, Response, StudentKnowledgeState
from backend.app.models import EvidenceSourceType, QuestionValidationStatus
from backend.app.services.learning_session_service import LearningSessionError, LearningSessionService
from backend.app.services.learning_settlement_service import LearningSettlementService
from backend.app.services.recommendation_context_service import RecommendationContextService
from backend.tests.test_m7_4_adaptive_practice import (
    _answer,
    _next,
    _ready_session,
    _settings,
)
from backend.tests.test_m7_4_adaptive_practice import practice_database as practice_database


def _finished(factory, ids, correct, url, *, wrong=False):
    session_id = _ready_session(factory, ids, url)
    state = _next(factory, url, session_id)
    for index in range(5):
        question = state.current_question
        assert question is not None
        answer = correct[question.question_id]
        if wrong:
            answer = ["FALSE"] if question.question_type.value == "true_false" else ["B"]
        state = _answer(factory, url, session_id, question.assessment_question_id, answer)
        if index < 4:
            state = _next(factory, url, session_id)
    return session_id


def _add_unseen_questions(factory, ids, correct):
    from copy import deepcopy

    from backend.app.db.models import QuestionKnowledgeNode
    from backend.app.models import KnowledgeRelationRole

    with factory() as db, db.begin():
        templates = [db.get(Question, question_id) for question_id in list(correct)[:5]]
        for index, template in enumerate(templates):
            question = Question(
                course_id=template.course_id,
                question_type=template.question_type,
                stem=f"Independent new concept question {index}",
                options=deepcopy(template.options),
                correct_answer=deepcopy(template.correct_answer),
                explanation=template.explanation,
                difficulty=template.difficulty,
                validation_status=QuestionValidationStatus.VALIDATED,
                source_refs=deepcopy(template.source_refs),
                generation_metadata={},
                content_version=1,
            )
            db.add(question)
            db.flush()
            correct[question.id] = question.correct_answer
            db.add(
                QuestionKnowledgeNode(
                    course_id=ids["course"],
                    question_id=question.id,
                    knowledge_node_id=ids["cache"],
                    relation_role=KnowledgeRelationRole.PRIMARY,
                )
            )


def test_settlement_reuses_evidence_and_mastery_on_retry(practice_database):
    factory, ids, correct, url = practice_database
    session_id = _finished(factory, ids, correct, url)
    with factory() as db:
        first = LearningSettlementService(db, _settings(url)).complete_for_configured_user(session_id)
    with factory() as db:
        second = LearningSettlementService(db, _settings(url)).complete_for_configured_user(session_id)
    assert first.status.value == "completed"
    assert first.completion_summary == second.completion_summary
    assert first.completion_summary["practice_summary"]["correct_answers"] == 5
    assert len(first.completion_summary["evidence_ids"]) == 5
    with factory() as db:
        evidence = list(db.scalars(select(LearningEvidence)))
        assert len(evidence) == 5
        assert all(row.source_type == EvidenceSourceType.PRACTICE for row in evidence)
        assert db.scalar(select(func.count()).select_from(StudentKnowledgeState)) == 1
    with factory() as db:
        context = RecommendationContextService(db).build_recommendation_context(
            user_id=ids["owner"], course_id=ids["course"]
        )
        target = next(state for state in context.mastery_states if state.knowledge_node_id == ids["cache"])
        assert target.calculation_state.value == "calculated"
        assert float(target.mastery_score) == first.completion_summary["mastery_changes"][0]["after"]


def test_settlement_uses_mastery_before_first_answer(practice_database):
    factory, ids, correct, url = practice_database
    first_id = _finished(factory, ids, correct, url)
    with factory() as db:
        first = LearningSettlementService(db, _settings(url)).complete_for_configured_user(first_id)
    baseline = first.completion_summary["mastery_changes"][0]["after"]
    _add_unseen_questions(factory, ids, correct)
    second_id = _finished(factory, ids, correct, url, wrong=True)
    with factory() as db:
        second = LearningSettlementService(db, _settings(url)).complete_for_configured_user(second_id)
    change = second.completion_summary["mastery_changes"][0]
    assert change["before"] == baseline
    assert change["after"] < baseline
    assert change["delta"] == round(change["after"] - baseline, 2)


def test_unfinished_and_other_user_rejected(practice_database):
    factory, ids, _, url = practice_database
    session_id = _ready_session(factory, ids, url)
    with factory() as db, pytest.raises(LearningSessionError):
        LearningSettlementService(db, _settings(url)).complete_for_configured_user(session_id)
    with factory() as db, pytest.raises(LearningSessionError) as captured:
        LearningSettlementService(db, _settings(url, "other@example.test")).complete_for_configured_user(session_id)
    assert captured.value.code == "SESSION_NOT_FOUND"


def test_completed_details_restore_attempts_and_enforce_scope(practice_database):
    from backend.app.db.models import Assessment

    factory, ids, correct, url = practice_database
    session_id = _finished(factory, ids, correct, url, wrong=True)
    with factory() as db:
        LearningSettlementService(db, _settings(url)).complete_for_configured_user(session_id)
    with factory() as db:
        result = LearningSessionService(db, _settings(url)).get_for_configured_user(session_id)
        assert len(result.practice_attempts) == 5
        first = result.practice_attempts[0]
        assert first.stem and first.selected_options and first.correct_answer and first.explanation
        assert first.is_correct is False
    with factory() as db, pytest.raises(LearningSessionError) as captured:
        LearningSessionService(db, _settings(url, "other@example.test")).get_for_configured_user(session_id)
    assert captured.value.code == "SESSION_NOT_FOUND"
    with factory() as db, db.begin():
        item = db.get(LearningSession, session_id)
        assessment = db.get(Assessment, item.practice_assessment_id)
        assessment.course_id = ids["other_course"]
    with factory() as db, pytest.raises(LearningSessionError) as captured:
        LearningSessionService(db, _settings(url)).get_for_configured_user(session_id)
    assert captured.value.code == "PRACTICE_SCOPE_MISMATCH"


def test_continuation_checks_ownership_completion_and_course(practice_database):
    factory, ids, correct, url = practice_database
    session_id = _finished(factory, ids, correct, url)
    with factory() as db, pytest.raises(LearningSessionError) as captured:
        LearningSessionService(db, _settings(url)).continuation_for_configured_user(session_id, set())
    assert captured.value.code == "SESSION_NOT_READY"
    with factory() as db:
        LearningSettlementService(db, _settings(url)).complete_for_configured_user(session_id)
    with factory() as db, pytest.raises(LearningSessionError) as captured:
        LearningSessionService(db, _settings(url, "other@example.test")).continuation_for_configured_user(
            session_id, set()
        )
    assert captured.value.code == "SESSION_NOT_FOUND"
    with factory() as db:
        result = LearningSessionService(db, _settings(url)).continuation_for_configured_user(session_id, {ids["empty"]})
        assert result.recommendation is None


def test_single_question_resume_settlement_and_explicit_relearn(practice_database):
    factory, ids, correct, url = practice_database
    only_id = min(correct)
    with factory() as db, db.begin():
        db.execute(
            update(Question)
            .where(Question.course_id == ids["course"], Question.id != only_id)
            .values(validation_status=QuestionValidationStatus.REJECTED)
        )
    session_id = _ready_session(factory, ids, url)
    question = _next(factory, url, session_id).current_question
    assert question is not None and question.question_id == only_id
    first = _answer(factory, url, session_id, question.assessment_question_id, correct[only_id])
    replay = _answer(factory, url, session_id, question.assessment_question_id, correct[only_id])
    assert first.attempts[0].attempt_id == replay.attempts[0].attempt_id
    assert _next(factory, url, session_id).status == "question_bank_empty"
    with factory() as db, pytest.raises(LearningSessionError) as captured:
        LearningSettlementService(db, _settings(url)).complete_for_configured_user(session_id)
    assert captured.value.code == "SESSION_NOT_READY"
    with factory() as db:
        service = LearningSessionService(db, _settings(url))
        assert service.get_for_configured_user(session_id).status.value == "in_progress"
        service.cancel_for_configured_user(session_id)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Response)) == 1
        assert db.scalar(select(func.count()).select_from(LearningEvidence)) == 1
    # A new session is allowed, but previously seen content is not offered again.
    relearn_id = _ready_session(factory, ids, url)
    assert relearn_id != session_id
    state = _next(factory, url, relearn_id)
    assert state.status == "question_bank_empty" and state.current_question is None


def test_failure_rolls_back_and_recommendation_failure_can_retry(practice_database, monkeypatch):
    factory, ids, correct, url = practice_database
    session_id = _finished(factory, ids, correct, url)
    from backend.app.services.learning_settlement_service import LearningPlanService, MasteryService

    # All answers have already refreshed mastery: settlement must not repeat it.
    monkeypatch.setattr(MasteryService, "refresh_state", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError()))
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(LearningEvidence)) == 5
        assert db.scalar(select(func.count()).select_from(StudentKnowledgeState)) == 1
    original_generate = LearningPlanService.generate
    monkeypatch.setattr(LearningPlanService, "generate", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError()))
    with factory() as db:
        failed = LearningSettlementService(db, _settings(url)).complete_for_configured_user(session_id)
    assert failed.recommendation_refresh_status.value == "failed"
    monkeypatch.setattr(LearningPlanService, "generate", original_generate)
    with factory() as db:
        retried = LearningSettlementService(db, _settings(url)).complete_for_configured_user(session_id)
    assert retried.recommendation_refresh_status.value == "succeeded"
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(LearningEvidence)) == 5


def test_parallel_settlement_has_one_effect(practice_database):
    factory, ids, correct, url = practice_database
    session_id = _finished(factory, ids, correct, url)

    def settle():
        with factory() as db:
            try:
                return LearningSettlementService(db, _settings(url)).complete_for_configured_user(session_id)
            except LearningSessionError as error:
                assert error.code == "LEARNING_SESSION_CONFLICT"
                return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: settle(), range(2)))
    assert any(result is not None for result in results)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(LearningEvidence)) == 5
        assert db.scalar(select(func.count()).select_from(StudentKnowledgeState)) == 1


def test_before_after_uses_persisted_mastery_and_can_decrease(practice_database):
    factory, ids, correct, url = practice_database
    _add_unseen_questions(factory, ids, correct)
    first_id = _finished(factory, ids, correct, url)
    with factory() as db:
        first = LearningSettlementService(db, _settings(url)).complete_for_configured_user(first_id)
    before = first.completion_summary["mastery_changes"][0]["after"]
    second_id = _finished(factory, ids, correct, url, wrong=True)
    with factory() as db:
        second = LearningSettlementService(db, _settings(url)).complete_for_configured_user(second_id)
    change = second.completion_summary["mastery_changes"][0]
    assert change["before"] == before
    assert change["after"] < before
    assert change["delta"] == round(change["after"] - before, 2)


def test_wrong_target_and_evidence_failure_roll_back(practice_database, monkeypatch):
    factory, ids, correct, url = practice_database
    session_id = _finished(factory, ids, correct, url)
    with factory() as db, db.begin():
        session = db.get(LearningSession, session_id)
        session.target_knowledge_node_id = ids["empty"]
    with factory() as db, pytest.raises(LearningSessionError) as captured:
        LearningSettlementService(db, _settings(url)).complete_for_configured_user(session_id)
    assert captured.value.code == "PRACTICE_SCOPE_MISMATCH"
    with factory() as db, db.begin():
        session = db.get(LearningSession, session_id)
        assert session.status.value == "in_progress"
        session.target_knowledge_node_id = ids["cache"]
    from backend.app.services.learning_settlement_service import LearningEvidenceService

    def fail(*args, **kwargs):
        raise RuntimeError("evidence insert failed")

    # Evidence was already committed with each answer; settlement must reuse it.
    monkeypatch.setattr(LearningEvidenceService, "create", fail)
    with factory() as db:
        result = LearningSettlementService(db, _settings(url)).complete_for_configured_user(session_id)
        assert len(result.completion_summary["evidence_ids"]) == 5
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(LearningEvidence)) == 5
        assert db.scalar(select(func.count()).select_from(StudentKnowledgeState)) == 1
        assert db.get(LearningSession, session_id).status.value == "completed"


def test_mastery_can_increase_after_more_correct_answers(practice_database):
    factory, ids, correct, url = practice_database
    _add_unseen_questions(factory, ids, correct)
    first_id = _finished(factory, ids, correct, url, wrong=True)
    with factory() as db:
        first = LearningSettlementService(db, _settings(url)).complete_for_configured_user(first_id)
    before = first.completion_summary["mastery_changes"][0]["after"]
    second_id = _finished(factory, ids, correct, url)
    with factory() as db:
        second = LearningSettlementService(db, _settings(url)).complete_for_configured_user(second_id)
    change = second.completion_summary["mastery_changes"][0]
    assert change["before"] == before
    assert change["after"] > before
