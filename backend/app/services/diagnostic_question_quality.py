from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from backend.app.ai.models import DiagnosticQuestionDraft


def normalize_question_stem(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


@dataclass(frozen=True)
class DuplicateDecision:
    duplicate: bool
    reason: str | None = None


class DiagnosticQuestionQualityValidator:
    """Deterministic quality gates; this is not an educational correctness oracle."""

    def __init__(self, similarity_threshold: float) -> None:
        self.similarity_threshold = similarity_threshold

    def validate_basic_quality(self, draft: DiagnosticQuestionDraft) -> None:
        if len(draft.stem) < 6:
            raise ValueError("Question stem is too short to be reviewable.")
        if len(draft.explanation) < 8 or normalize_question_stem(draft.explanation) == normalize_question_stem(
            draft.stem
        ):
            raise ValueError("Question explanation is missing meaningful answer rationale.")
        option_texts = [normalize_question_stem(option.text) for option in draft.options]
        if any(not text for text in option_texts) or len(option_texts) != len(set(option_texts)):
            raise ValueError("Question options must contain distinct, non-empty text.")
        if re.search(r"\b(?:maybe|possibly|usually)\b|通常来说是否可能", draft.stem.casefold()):
            raise ValueError("Question wording is too ambiguous for deterministic scoring.")

    def detect_duplicate(
        self,
        *,
        stem: str,
        course_stems: list[str] | tuple[str, ...],
        primary_node_stems: list[str] | tuple[str, ...],
        accepted_stems: list[str],
    ) -> DuplicateDecision:
        normalized = normalize_question_stem(stem)
        if not normalized:
            return DuplicateDecision(True, "empty normalized stem")
        for existing in course_stems:
            if normalize_question_stem(existing) == normalized:
                return DuplicateDecision(True, "exact course duplicate")
        for accepted in accepted_stems:
            accepted_normalized = normalize_question_stem(accepted)
            if accepted_normalized == normalized:
                return DuplicateDecision(True, "duplicate within generation request")
            if SequenceMatcher(None, accepted_normalized, normalized).ratio() >= self.similarity_threshold:
                return DuplicateDecision(True, "near duplicate within generation request")
        for existing in primary_node_stems:
            similarity = SequenceMatcher(None, normalize_question_stem(existing), normalized).ratio()
            if similarity >= self.similarity_threshold:
                return DuplicateDecision(True, "near duplicate for primary knowledge node")
        return DuplicateDecision(False)
