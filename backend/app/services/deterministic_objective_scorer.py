from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import ValidationError

from backend.app.models import QuestionType
from backend.app.schemas.assessment_scoring import ObjectiveScoreResultSchema
from backend.app.schemas.diagnostic import AssessmentQuestionSnapshotSchema, ObjectiveAnswerSchema


class DeterministicScoringError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class DeterministicObjectiveScorer:
    POLICY_VERSION = "objective_exact_match_v1"

    def score(
        self,
        question_snapshot: AssessmentQuestionSnapshotSchema | dict[str, Any],
        submitted_answer: ObjectiveAnswerSchema | dict[str, Any] | None,
    ) -> ObjectiveScoreResultSchema:
        raw_snapshot = (
            question_snapshot.model_dump(mode="json")
            if isinstance(question_snapshot, AssessmentQuestionSnapshotSchema)
            else question_snapshot
        )
        policy = raw_snapshot.get("scoring_policy") if isinstance(raw_snapshot, dict) else None
        version = policy.get("version") if isinstance(policy, dict) else None
        if version != self.POLICY_VERSION:
            raise DeterministicScoringError(
                "SCORING_POLICY_UNSUPPORTED", "Stored scoring policy version is not supported."
            )
        try:
            snapshot = AssessmentQuestionSnapshotSchema.model_validate(raw_snapshot)
            answer = (
                ObjectiveAnswerSchema()
                if submitted_answer is None
                else ObjectiveAnswerSchema.model_validate(submitted_answer)
            )
        except ValidationError as error:
            raise DeterministicScoringError("SCORING_INPUT_INVALID", "Scoring input is invalid.") from error

        selected = answer.selected_options
        option_keys = {option.key for option in snapshot.options}
        if not set(selected).issubset(option_keys):
            raise DeterministicScoringError("SCORING_ANSWER_INVALID", "Answer contains an unknown option key.")
        if snapshot.question_type in {QuestionType.SINGLE_CHOICE, QuestionType.TRUE_FALSE} and len(selected) > 1:
            raise DeterministicScoringError(
                "SCORING_ANSWER_INVALID", "Single choice and true/false answers may contain at most one option."
            )

        is_correct = bool(selected) and set(selected) == set(snapshot.correct_answer)
        max_points = Decimal(snapshot.scoring_policy.max_points)
        return ObjectiveScoreResultSchema(
            is_correct=is_correct,
            points_awarded=max_points if is_correct else Decimal("0"),
            max_points=max_points,
            scoring_policy_version=version,
        )


__all__ = ["DeterministicObjectiveScorer", "DeterministicScoringError"]
