from sqlalchemy import func, select, update

from backend.app.db.models import LearningEvidence, MasteryHistory, Question, Response, StudentKnowledgeState
from backend.app.models import QuestionValidationStatus
from backend.app.services.learning_session_service import LearningSessionService
from backend.app.services.learning_settlement_service import LearningSettlementService
from backend.tests.test_m7_4_adaptive_practice import _answer, _next, _ready_session, _settings
from backend.tests.test_m7_4_adaptive_practice import practice_database as practice_database


def test_same_source_relearn_keeps_attempt_but_not_independent_evidence(practice_database):
    factory, ids, correct, url = practice_database
    source_id = min(correct)
    with factory() as db, db.begin():
        db.execute(
            update(Question)
            .where(Question.course_id == ids["course"], Question.id != source_id)
            .values(validation_status=QuestionValidationStatus.REJECTED)
        )
    first_id = _ready_session(factory, ids, url)
    question = _next(factory, url, first_id).current_question
    assert question is not None and question.question_id == source_id
    first = _answer(factory, url, first_id, question.assessment_question_id, correct[source_id])
    replay = _answer(factory, url, first_id, question.assessment_question_id, correct[source_id])
    assert first.attempts[0].attempt_id == replay.attempts[0].attempt_id
    assert _next(factory, url, first_id).status == "question_bank_empty"
    with factory() as db:
        state = db.scalar(select(StudentKnowledgeState))
        original = (state.mastery_score, state.confidence_level, state.evidence_fingerprint, state.calculated_at)
        history_count = db.scalar(select(func.count()).select_from(MasteryHistory))
    with factory() as db:
        LearningSessionService(db, _settings(url)).cancel_for_configured_user(first_id)
    second_id = _ready_session(factory, ids, url)
    assert second_id != first_id
    second = _next(factory, url, second_id)
    assert second.status == "question_bank_empty" and second.current_question is None
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Response)) == 1
        assert db.scalar(select(func.count()).select_from(LearningEvidence)) == 1
        state = db.scalar(select(StudentKnowledgeState))
        assert (
            state.mastery_score,
            state.confidence_level,
            state.evidence_fingerprint,
            state.calculated_at,
        ) == original
        assert db.scalar(select(func.count()).select_from(MasteryHistory)) == history_count


def test_mixed_same_node_sources_only_add_new_evidence(practice_database):
    from backend.app.db.models import AssessmentQuestion
    from backend.tests.test_m7_5_settlement import _add_unseen_questions, _finished

    factory, ids, correct, url = practice_database
    first_id = _finished(factory, ids, correct, url)
    with factory() as db:
        first = LearningSettlementService(db, _settings(url)).complete_for_configured_user(first_id)
    with factory() as db:
        state = db.scalar(select(StudentKnowledgeState))
        fingerprint_before = state.evidence_fingerprint
        history_before = db.scalar(select(func.count()).select_from(MasteryHistory))
        first_sources = {
            row.question_snapshot["source_question_id"]
            for row in db.scalars(
                select(AssessmentQuestion).join(
                    LearningEvidence, LearningEvidence.source_question_snapshot_id == AssessmentQuestion.id
                )
            )
        }
        assert len(first_sources) == 5
    # New content is required: the second session cannot repeat the old five.
    _add_unseen_questions(factory, ids, correct)
    second_id = _finished(factory, ids, correct, url, wrong=True)
    with factory() as db:
        second = LearningSettlementService(db, _settings(url)).complete_for_configured_user(second_id)
    with factory() as db:
        state = db.scalar(select(StudentKnowledgeState))
        rows = list(db.scalars(select(LearningEvidence)))
        assert len(rows) == 10
        assert len(second.completion_summary["evidence_ids"]) == 5
        assert db.scalar(select(func.count()).select_from(Response)) == 10
        assert state.evidence_fingerprint != fingerprint_before
        assert db.scalar(select(func.count()).select_from(MasteryHistory)) == history_before + 5
    assert first.completion_summary["practice_summary"]["total_questions"] == 5
    assert second.completion_summary["practice_summary"]["total_questions"] == 5


def test_new_question_version_is_independent(practice_database):
    factory, ids, correct, url = practice_database
    source_id = min(correct)
    with factory() as db, db.begin():
        db.execute(
            update(Question)
            .where(Question.course_id == ids["course"], Question.id != source_id)
            .values(validation_status=QuestionValidationStatus.REJECTED)
        )
    first_id = _ready_session(factory, ids, url)
    first_question = _next(factory, url, first_id).current_question
    _answer(factory, url, first_id, first_question.assessment_question_id, correct[source_id])
    with factory() as db:
        LearningSessionService(db, _settings(url)).cancel_for_configured_user(first_id)
    with factory() as db, db.begin():
        question = db.get(Question, source_id)
        question.content_version += 1
        question.stem = "Updated independent content for the same node"
    second_id = _ready_session(factory, ids, url)
    second_question = _next(factory, url, second_id).current_question
    assert second_question is not None and second_question.question_id == source_id
    assert second_question.stem != first_question.stem
    _answer(factory, url, second_id, second_question.assessment_question_id, correct[source_id])
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Response)) == 2
        assert db.scalar(select(func.count()).select_from(LearningEvidence)) == 2
        assert db.scalar(select(func.count()).select_from(MasteryHistory)) == 2


def test_old_duplicate_evidence_and_snapshots_are_not_rewritten(practice_database, monkeypatch):
    from backend.app.db.models import QuestionKnowledgeNode
    from backend.app.repositories.learning_evidence_repository import LearningEvidenceRepository

    factory, ids, correct, url = practice_database
    source_id = min(correct)
    with factory() as db, db.begin():
        db.execute(
            update(Question)
            .where(Question.course_id == ids["course"], Question.id != source_id)
            .values(validation_status=QuestionValidationStatus.REJECTED)
        )
    first_id = _ready_session(factory, ids, url)
    question = _next(factory, url, first_id).current_question
    _answer(factory, url, first_id, question.assessment_question_id, correct[source_id])
    with factory() as db:
        LearningSessionService(db, _settings(url)).cancel_for_configured_user(first_id)
    with factory() as db:
        old_evidence_ids = list(db.scalars(select(LearningEvidence.id).order_by(LearningEvidence.id)))
        old_history_ids = list(db.scalars(select(MasteryHistory.id).order_by(MasteryHistory.id)))
        state = db.scalar(select(StudentKnowledgeState))
        old_state = (state.evidence_fingerprint, state.mastery_score, state.confidence_level, state.calculated_at)
    # An alternate ID with identical normalized content cannot bypass exclusion,
    # even if the old source lookup were accidentally disabled.
    with factory() as db, db.begin():
        original = db.get(Question, source_id)
        duplicate = Question(
            course_id=ids["course"],
            question_type=original.question_type,
            stem=original.stem.upper() + "!",
            options=original.options,
            correct_answer=original.correct_answer,
            explanation=original.explanation,
            difficulty=original.difficulty,
            validation_status=QuestionValidationStatus.VALIDATED,
            source_refs=original.source_refs,
            generation_metadata={},
            content_version=1,
        )
        db.add(duplicate)
        db.flush()
        from backend.app.models import KnowledgeRelationRole

        db.add(
            QuestionKnowledgeNode(
                course_id=ids["course"],
                question_id=duplicate.id,
                knowledge_node_id=ids["cache"],
                relation_role=KnowledgeRelationRole.PRIMARY,
            )
        )
    with monkeypatch.context() as patch:
        patch.setattr(LearningEvidenceRepository, "has_source_question_evidence", lambda *args, **kwargs: False)
        second_id = _ready_session(factory, ids, url)
        second = _next(factory, url, second_id)
        assert second.status == "question_bank_empty" and second.current_question is None
    with factory() as db:
        assert list(db.scalars(select(LearningEvidence.id).order_by(LearningEvidence.id))) == old_evidence_ids
        assert list(db.scalars(select(MasteryHistory.id).order_by(MasteryHistory.id))) == old_history_ids
        state = db.scalar(select(StudentKnowledgeState))
        assert (
            state.evidence_fingerprint,
            state.mastery_score,
            state.confidence_level,
            state.calculated_at,
        ) == old_state
        assert db.scalar(select(func.count()).select_from(Response)) == 1


def test_source_lookup_respects_user_course_and_question_version(practice_database):
    from backend.app.repositories.learning_evidence_repository import LearningEvidenceRepository

    factory, ids, correct, url = practice_database
    source_id = min(correct)
    with factory() as db, db.begin():
        db.execute(
            update(Question)
            .where(Question.course_id == ids["course"], Question.id != source_id)
            .values(validation_status=QuestionValidationStatus.REJECTED)
        )
    session_id = _ready_session(factory, ids, url)
    question = _next(factory, url, session_id).current_question
    _answer(factory, url, session_id, question.assessment_question_id, correct[source_id])
    params = dict(
        user_id=ids["owner"],
        course_id=ids["course"],
        source_question_id=source_id,
        source_question_version=1,
        historical_knowledge_node_ref=ids["cache"],
    )
    with factory() as db:
        repo = LearningEvidenceRepository(db)
        assert repo.has_source_question_evidence(**params)
        assert not repo.has_source_question_evidence(**{**params, "user_id": ids["owner"] + 1000})
        assert not repo.has_source_question_evidence(**{**params, "course_id": ids["other_course"]})
        assert not repo.has_source_question_evidence(**{**params, "source_question_version": 2})
        assert not repo.has_source_question_evidence(**{**params, "historical_knowledge_node_ref": ids["empty"]})


def test_near_simultaneous_same_answer_is_safe_or_retryable(practice_database):
    from concurrent.futures import ThreadPoolExecutor

    from backend.app.services.adaptive_practice_service import AdaptivePracticeError

    factory, ids, correct, url = practice_database
    session_id = _ready_session(factory, ids, url)
    question = _next(factory, url, session_id).current_question

    def answer():
        try:
            return _answer(factory, url, session_id, question.assessment_question_id, correct[question.question_id])
        except AdaptivePracticeError as error:
            assert error.code == "PRACTICE_STATE_CONFLICT"
            return None

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: answer(), range(2)))
    assert any(result is not None for result in results)
    retry = answer()
    assert retry is not None
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Response)) == 1
        assert db.scalar(select(func.count()).select_from(LearningEvidence)) == 1
        state = db.scalar(select(StudentKnowledgeState))
        assert state is not None and state.independent_evidence_count == 1


def test_relearning_only_existing_sources_preserves_calculated_mastery(practice_database):
    from backend.tests.test_m7_5_settlement import _finished

    factory, ids, correct, url = practice_database
    first_id = _finished(factory, ids, correct, url)
    with factory() as db:
        first = LearningSettlementService(db, _settings(url)).complete_for_configured_user(first_id)
    with factory() as db, db.begin():
        # No previously seen question can be used as a new independent source.
        db.execute(
            update(Question)
            .where(Question.course_id == ids["course"])
            .values(validation_status=QuestionValidationStatus.REJECTED)
        )
        state = db.scalar(select(StudentKnowledgeState))
        original = (state.mastery_score, state.confidence_level, state.evidence_fingerprint, state.calculated_at)
        count = db.scalar(select(func.count()).select_from(MasteryHistory))
    assert original[0] is not None
    second_id = _ready_session(factory, ids, url)
    second = _next(factory, url, second_id)
    assert second.status == "question_bank_empty" and second.current_question is None
    assert first.completion_summary["practice_summary"]["total_questions"] == 5
    with factory() as db:
        state = db.scalar(select(StudentKnowledgeState))
        assert (
            state.mastery_score,
            state.confidence_level,
            state.evidence_fingerprint,
            state.calculated_at,
        ) == original
        assert db.scalar(select(func.count()).select_from(MasteryHistory)) == count
        assert db.scalar(select(func.count()).select_from(Response)) == 5
        assert db.scalar(select(func.count()).select_from(LearningEvidence)) == 5
