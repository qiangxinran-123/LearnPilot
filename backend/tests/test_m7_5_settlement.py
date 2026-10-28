from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select

from backend.app.db.models import LearningEvidence, LearningSession, StudentKnowledgeState
from backend.app.models import EvidenceSourceType
from backend.app.services.learning_session_service import LearningSessionError
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


def test_unfinished_and_other_user_rejected(practice_database):
    factory, ids, _, url = practice_database
    session_id = _ready_session(factory, ids, url)
    with factory() as db, pytest.raises(LearningSessionError):
        LearningSettlementService(db, _settings(url)).complete_for_configured_user(session_id)
    with factory() as db, pytest.raises(LearningSessionError) as captured:
        LearningSettlementService(db, _settings(url, "other@example.test")).complete_for_configured_user(session_id)
    assert captured.value.code == "SESSION_NOT_FOUND"


def test_failure_rolls_back_and_recommendation_failure_can_retry(practice_database, monkeypatch):
    factory, ids, correct, url = practice_database
    session_id = _finished(factory, ids, correct, url)
    from backend.app.services.learning_settlement_service import LearningPlanService, MasteryService

    original = MasteryService.refresh_state
    monkeypatch.setattr(MasteryService, "refresh_state", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError()))
    with factory() as db, pytest.raises(RuntimeError):
        LearningSettlementService(db, _settings(url)).complete_for_configured_user(session_id)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(LearningEvidence)) == 0
        assert db.scalar(select(func.count()).select_from(StudentKnowledgeState)) == 0
    monkeypatch.setattr(MasteryService, "refresh_state", original)
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

    monkeypatch.setattr(LearningEvidenceService, "create", fail)
    with factory() as db, pytest.raises(RuntimeError):
        LearningSettlementService(db, _settings(url)).complete_for_configured_user(session_id)
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(LearningEvidence)) == 0
        assert db.scalar(select(func.count()).select_from(StudentKnowledgeState)) == 0
        assert db.get(LearningSession, session_id).status.value == "in_progress"


def test_mastery_can_increase_after_more_correct_answers(practice_database):
    factory, ids, correct, url = practice_database
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
