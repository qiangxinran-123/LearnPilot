from __future__ import annotations

import pytest
from sqlalchemy import func, select

from backend.app.ai import AIServiceError
from backend.app.ai.client import ExplicitMockLLMClient
from backend.app.ai.models import DiagnosticQuestionGenerationOutput
from backend.app.ai.prompts.diagnostic_questions import messages
from backend.app.core.settings import Settings
from backend.app.db.models import Question
from backend.app.models import QuestionDifficulty, QuestionType, QuestionValidationStatus
from backend.app.services.diagnostic_question_bank_service import DiagnosticQuestionBankService
from backend.app.services.diagnostic_question_generation import DiagnosticQuestionGenerationService
from backend.tests.test_m4b_question_generation import database as database


def _messages(question_type=QuestionType.SINGLE_CHOICE, count=1, context=None):
    return messages(
        node_id=17,
        node_name="缓存策略",
        node_description="复习资料",
        question_type=question_type,
        difficulty=QuestionDifficulty.MEDIUM,
        count=count,
        context=context
        if context is not None
        else "[material_id=9; source_reference=TXT 行 3]\n缓存替换依据最近访问时间进行判断。",
    )


@pytest.mark.parametrize("kind", list(QuestionType))
def test_mock_diagnostic_is_valid_deterministic_and_source_bound(kind):
    client = ExplicitMockLLMClient()
    params = dict(
        operation="diagnostic_question_generation", messages=_messages(kind), schema=DiagnosticQuestionGenerationOutput
    )
    first = client.generate_structured(**params)
    second = client.generate_structured(**params)
    assert first.data == second.data
    assert len(first.data.questions) == 1
    draft = first.data.questions[0]
    assert draft.question_type == kind
    assert draft.knowledge_node_ids == [17]
    assert draft.source_refs[0].material_id == 9
    assert draft.source_refs[0].source_reference == "TXT 行 3"
    assert set(draft.correct_answer).issubset({item.key for item in draft.options})
    assert "模拟题" in draft.stem


@pytest.mark.parametrize(
    "messages_value",
    [
        _messages(count=2),
        _messages(context="无来源"),
        _messages(context="[material_id=9; source_reference=TXT 行 3]\n短"),
    ],
)
def test_mock_rejects_unsupported_count_and_missing_source(messages_value):
    with pytest.raises(AIServiceError) as error:
        ExplicitMockLLMClient().generate_structured(
            operation="diagnostic_question_generation",
            messages=messages_value,
            schema=DiagnosticQuestionGenerationOutput,
        )
    assert error.value.code == "AI_INVALID_OUTPUT"
    assert not error.value.retryable


def test_builtin_mock_formal_generation_and_manual_review(database):
    factory, seed = database
    settings = Settings(legacy_bootstrap_user="m4b-owner@example.test", llm_mode="mock", llm_max_attempts=1)
    with factory() as db:
        bank = DiagnosticQuestionBankService(db, settings)
        before = bank.readiness(seed.course_id)
        result = bank.generate_pending(course_id=seed.course_id, knowledge_node_id=seed.node_id)
        assert result.provider == "mock"
        assert result.requested_count == result.accepted_count == 1
        question = result.questions[0]
        assert question.validation_status == QuestionValidationStatus.PENDING
        assert question.knowledge_node_id == seed.node_id
        eligibility = bank.review_eligibility(seed.course_id)
        assert question.question_id in eligibility.eligible_ids
        reviewed = bank.approve(seed.course_id, question.question_id)
        assert reviewed.question.validation_status == QuestionValidationStatus.VALIDATED
        after = bank.readiness(seed.course_id)
        assert after.validated_count == before.validated_count + 1
        assert not after.can_start
        assert after.available_questions < after.required_questions
    with factory() as db:
        assert db.scalar(select(func.count()).select_from(Question)) == 1


def test_builtin_mock_all_supported_types_pass_generation_service(database):
    factory, seed = database
    settings = Settings(llm_mode="mock", llm_max_attempts=1)
    with factory() as db:
        result = DiagnosticQuestionGenerationService(db, settings).generate_questions_for_node(
            owner_id=seed.owner_id,
            course_id=seed.course_id,
            knowledge_node_id=seed.node_id,
            question_type=QuestionType.TRUE_FALSE,
            difficulty=QuestionDifficulty.EASY,
            count=1,
        )
        assert result.provider == "mock"
        assert result.accepted_count == 1
        assert result.questions[0].correct_answer == ["TRUE"]


def test_builtin_mock_prepare_course_persists_and_reviews_batch(database):
    factory, seed = database
    settings = Settings(legacy_bootstrap_user="m4b-owner@example.test", llm_mode="mock", llm_max_attempts=1)
    with factory() as db:
        bank = DiagnosticQuestionBankService(db, settings)
        batch = bank.prepare_course(seed.course_id)
        assert batch.planned_count == 2
        assert batch.generated_count == 2
        assert batch.failed_count == 0
        assert len({question.knowledge_node_id for question in batch.questions}) == 2
        eligibility = bank.review_eligibility(seed.course_id)
        assert len(eligibility.eligible_ids) == 2
        for question_id in eligibility.eligible_ids:
            assert (
                bank.approve(seed.course_id, question_id).question.validation_status
                == QuestionValidationStatus.VALIDATED
            )
        assert bank.review_eligibility(seed.course_id).eligible_ids == []
        readiness = bank.readiness(seed.course_id)
        assert readiness.available_questions == 2
        assert readiness.required_questions == 8
        assert not readiness.can_start
