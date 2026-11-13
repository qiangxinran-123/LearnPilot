from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher

from backend.app.ai.models import DiagnosticQuestionDraft


def normalize_question_stem(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def question_angle(stem: str) -> str | None:
    """Conservative, explainable categories for the supported two's-complement topic."""
    text = unicodedata.normalize("NFKC", stem).casefold()
    if "补码" not in text:
        return None
    if any(word in text for word in ("范围", "最小值", "最大值", "最小数", "最大数", "上限", "下限")):
        return "表示范围"
    if any(word in text for word in ("溢出", "加法", "减法", "运算")):
        return "运算与溢出"
    if any(word in text for word in ("真值", "十进制", "对应的整数", "表示的整数")):
        return "补码转真值"
    if any(word in text for word in ("求补码", "补码是", "补码为", "补码表示为", "补码表示是什么")):
        return "整数转补码"
    if any(word in text for word in ("定义", "原理", "权重", "符号位")):
        return "表示原理"
    return None


def same_question_angle(first: str, second: str) -> bool:
    angle = question_angle(first)
    numbers_a = set(re.findall(r"(?<![a-z])\d+", unicodedata.normalize("NFKC", first).casefold()))
    numbers_b = set(re.findall(r"(?<![a-z])\d+", unicodedata.normalize("NFKC", second).casefold()))
    if angle is not None and angle == question_angle(second):
        return numbers_a == numbers_b or not numbers_a or not numbers_b
    left = normalize_question_stem(first)
    right = normalize_question_stem(second)
    if min(len(left), len(right)) < 12 or numbers_a != numbers_b:
        return False
    overlap = sum((Counter(left) & Counter(right)).values())
    return 2 * overlap / (len(left) + len(right)) >= 0.94


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
