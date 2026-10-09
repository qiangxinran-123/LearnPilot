from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.ai import AIServiceError, GeneratedStructuredOutput, LLMClient, get_llm_client
from backend.app.ai.chunking import TextChunk, chunk_segments, relevant_chunks
from backend.app.ai.models import CardsOutput, QAOutput, SummaryOutput
from backend.app.ai.prompts import cards as cards_prompt
from backend.app.ai.prompts import material_qa as qa_prompt
from backend.app.ai.prompts import summary as summary_prompt
from backend.app.ai.references import normalize_source_reference
from backend.app.ai.references import (
    resolve_source_reference as _resolve_source_reference,
)
from backend.app.core.settings import Settings, get_settings
from backend.app.db.models import Material, MaterialSummary, StudyCard, User
from backend.app.db.session import get_db
from backend.app.repositories import (
    MaterialContentRepository,
    MaterialRepository,
    MaterialSummaryRepository,
    StudyCardRepository,
    UserRepository,
)
from backend.app.schemas.course import MaterialQAResponse
from backend.app.services.course_service import MaterialNotParsedError, ResourceNotFoundError, serialize_study_card

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReadyMaterial:
    material_id: int
    plain_text: str
    segments: list[dict[str, object]]


def _normalize_source_reference(reference: str | None) -> str | None:
    """Compatibility wrapper for the M2-tested private helper."""

    return normalize_source_reference(reference)


class MaterialAIService:
    def __init__(
        self,
        session: Session,
        material_repository: MaterialRepository,
        content_repository: MaterialContentRepository,
        summary_repository: MaterialSummaryRepository,
        card_repository: StudyCardRepository,
        user_repository: UserRepository,
        settings: Settings,
    ) -> None:
        self.session = session
        self.material_repository = material_repository
        self.content_repository = content_repository
        self.summary_repository = summary_repository
        self.card_repository = card_repository
        self.user_repository = user_repository
        self.settings = settings

    def get_summary(self, material_id: int) -> MaterialSummary | None:
        with self.session.begin():
            self._require_material(material_id)
            return self.summary_repository.get_for_material(material_id)

    def generate_summary(self, material_id: int) -> MaterialSummary:
        ready = self._load_ready_material(material_id)
        client = get_llm_client(self.settings)
        output = self._generate_summary_output(client, ready)
        data = output.data
        if not isinstance(data, SummaryOutput):
            raise AIServiceError("AI_INVALID_OUTPUT", "AI 返回摘要结构不正确。")

        with self.session.begin():
            material = self._require_material(material_id)
            summary = self.summary_repository.get_for_material(material_id)
            if summary is None:
                summary = MaterialSummary(
                    material_id=material_id,
                    overview=data.overview,
                    key_concepts=data.key_concepts,
                    important_points=data.important_points,
                    common_mistakes=data.common_mistakes,
                    review_suggestions=data.review_suggestions,
                    model_provider=output.provider,
                    model_name=output.model,
                    prompt_version=summary_prompt.PROMPT_VERSION,
                )
            else:
                summary.overview = data.overview
                summary.key_concepts = data.key_concepts
                summary.important_points = data.important_points
                summary.common_mistakes = data.common_mistakes
                summary.review_suggestions = data.review_suggestions
                summary.model_provider = output.provider
                summary.model_name = output.model
                summary.prompt_version = summary_prompt.PROMPT_VERSION
            material.ai_summary = data.overview
            material.summary_generated = True
            material.summary_method = output.provider
            material.summary_updated_at = datetime.now(timezone.utc)
            return self.summary_repository.save(summary)

    def get_cards(self, material_id: int) -> list[StudyCard]:
        with self.session.begin():
            self._require_material(material_id)
            return self.card_repository.list_for_material(material_id)

    def generate_cards(self, material_id: int) -> list[StudyCard]:
        ready = self._load_ready_material(material_id)
        chunks = self._chunks_for(ready)
        source, allowed_references = self._bounded_chunk_text(chunks)
        client = get_llm_client(self.settings)
        output = client.generate_structured(
            operation="ai_cards", messages=cards_prompt.messages(source), schema=CardsOutput
        )
        data = output.data
        if not isinstance(data, CardsOutput):
            raise AIServiceError("AI_INVALID_OUTPUT", "AI 返回学习卡片结构不正确。")
        normalized_references = [
            _resolve_source_reference(draft.source_reference, allowed_references) for draft in data.cards
        ]
        invalid_references = {
            reference
            for reference in normalized_references
            if reference is not None and reference not in allowed_references
        }
        if invalid_references:
            raise AIServiceError("AI_INVALID_OUTPUT", "AI 引用了当前资料以外的来源。")
        replacements = [
            StudyCard(
                material_id=material_id,
                question=draft.question,
                answer=draft.answer,
                knowledge_hint=draft.knowledge_hint,
                source_reference=source_reference,
                order_index=index,
                model_provider=output.provider,
                model_name=output.model,
                prompt_version=cards_prompt.PROMPT_VERSION,
            )
            for index, (draft, source_reference) in enumerate(
                zip(data.cards, normalized_references, strict=True), start=1
            )
        ]
        with self.session.begin():
            material = self._require_material(material_id)
            cards = self.card_repository.replace_for_material(material_id, replacements)
            material.cards = [serialize_study_card(card) for card in cards]
            material.cards_generated = True
            material.cards_generated_at = datetime.now(timezone.utc)
            material.cards_method = output.provider
            self.session.flush()
            return cards

    def answer_question(self, material_id: int, question: str) -> MaterialQAResponse:
        ready = self._load_ready_material(material_id)
        matches = relevant_chunks(question, self._chunks_for(ready), limit=4)
        if not matches:
            return MaterialQAResponse(
                material_id=material_id,
                answer="当前资料中没有足够信息回答这个问题。",
                references=[],
                grounded=False,
            )
        context = "\n\n".join(f"[{chunk.source_reference}]\n{chunk.text}" for chunk in matches)
        client = get_llm_client(self.settings)
        output = client.generate_structured(
            operation="material_qa", messages=qa_prompt.messages(question, context), schema=QAOutput
        )
        data = output.data
        if not isinstance(data, QAOutput):
            raise AIServiceError("AI_INVALID_OUTPUT", "AI 返回问答结构不正确。")
        if not data.sufficient_evidence:
            return MaterialQAResponse(
                material_id=material_id,
                answer="当前资料中没有足够信息回答这个问题。",
                references=[],
                grounded=False,
                provider=output.provider,
                model=output.model,
                prompt_version=qa_prompt.PROMPT_VERSION,
            )
        allowed_references = {chunk.source_reference for chunk in matches}
        references = list(
            dict.fromkeys(_resolve_source_reference(reference, allowed_references) for reference in data.references)
        )
        if not references or any(reference not in allowed_references for reference in references):
            raise AIServiceError("AI_INVALID_OUTPUT", "AI 引用了当前资料以外的来源。")
        return MaterialQAResponse(
            material_id=material_id,
            answer=data.answer,
            references=references,
            grounded=True,
            provider=output.provider,
            model=output.model,
            prompt_version=qa_prompt.PROMPT_VERSION,
        )

    def _generate_summary_output(self, client: LLMClient, ready: ReadyMaterial) -> GeneratedStructuredOutput:
        input_chars = len(ready.plain_text)
        if input_chars > self.settings.llm_summary_max_input_chars:
            raise AIServiceError("AI_INPUT_TOO_LARGE", "资料文本超过当前摘要处理上限。")
        logger.info("ai_summary_input material_id=%s input_chars=%s", ready.material_id, input_chars)
        if input_chars <= self.settings.llm_context_chars:
            return client.generate_structured(
                operation="ai_summary", messages=summary_prompt.messages(ready.plain_text), schema=SummaryOutput
            )

        pieces = [f"[{chunk.source_reference}]\n{chunk.text}" for chunk in self._chunks_for(ready)]
        partials: list[GeneratedStructuredOutput] = []
        for group in self._summary_groups(pieces):
            source = "\n\n".join(pieces[index] for index in group)
            result = client.generate_structured(
                operation="ai_summary_map", messages=summary_prompt.messages(source), schema=SummaryOutput
            )
            if not isinstance(result.data, SummaryOutput):
                raise AIServiceError("AI_INVALID_OUTPUT", "AI 返回分段摘要结构不正确。")
            partials.append(result)

        while len(partials) > 1:
            pieces = [self._summary_partial_text(result.data) for result in partials]
            groups = self._summary_groups(pieces)
            if len(groups) == len(partials):
                raise AIServiceError("AI_INVALID_OUTPUT", "分段摘要过长，无法在上下文限制内归约。")
            next_partials: list[GeneratedStructuredOutput] = []
            for group in groups:
                if len(group) == 1:
                    next_partials.append(partials[group[0]])
                    continue
                source = "\n\n".join(pieces[index] for index in group)
                result = client.generate_structured(
                    operation="ai_summary_reduce", messages=summary_prompt.messages(source), schema=SummaryOutput
                )
                if not isinstance(result.data, SummaryOutput):
                    raise AIServiceError("AI_INVALID_OUTPUT", "AI 返回归约摘要结构不正确。")
                next_partials.append(result)
            partials = next_partials
        return partials[0]

    def _summary_groups(self, pieces: list[str]) -> list[list[int]]:
        groups: list[list[int]] = []
        current: list[int] = []
        current_chars = 0
        for index, piece in enumerate(pieces):
            if len(piece) > self.settings.llm_context_chars:
                raise AIServiceError("AI_INPUT_TOO_LARGE", "摘要输入片段超过模型上下文限制。")
            separator_chars = 2 if current else 0
            if current and (
                len(current) >= self.settings.llm_summary_max_chunks
                or current_chars + separator_chars + len(piece) > self.settings.llm_context_chars
            ):
                groups.append(current)
                current = []
                current_chars = 0
                separator_chars = 0
            current.append(index)
            current_chars += separator_chars + len(piece)
        if current:
            groups.append(current)
        return groups

    @staticmethod
    def _summary_partial_text(data: SummaryOutput) -> str:
        return "\n".join(
            [
                "核心概览",
                data.overview,
                "关键概念",
                *data.key_concepts,
                "重要内容",
                *data.important_points,
                "易错点",
                *data.common_mistakes,
                "复习建议",
                *data.review_suggestions,
            ]
        )

    def _load_ready_material(self, material_id: int) -> ReadyMaterial:
        with self.session.begin():
            material = self._require_material(material_id)
            content = self.content_repository.get_for_material(material.id)
            if content is None or material.extraction_status not in {"SUCCESS", "EXTRACTED"}:
                raise MaterialNotParsedError("Material has not been parsed successfully.")
            return ReadyMaterial(material.id, content.plain_text, content.segments)

    def _chunks_for(self, ready: ReadyMaterial) -> list[TextChunk]:
        chunks = chunk_segments(
            ready.segments,
            max_chars=self.settings.llm_chunk_chars,
            overlap_chars=self.settings.llm_chunk_overlap_chars,
        )
        if chunks:
            return chunks
        return chunk_segments(
            [{"text": ready.plain_text, "source_reference": "资料内容"}],
            max_chars=self.settings.llm_chunk_chars,
            overlap_chars=self.settings.llm_chunk_overlap_chars,
        )

    def _bounded_chunk_text(self, chunks: list[TextChunk]) -> tuple[str, set[str]]:
        selected: list[str] = []
        references: set[str] = set()
        remaining = self.settings.llm_context_chars
        for chunk in chunks:
            prefix = f"[{chunk.source_reference}]\n"
            separator = "\n\n" if selected else ""
            available = remaining - len(separator) - len(prefix)
            if available <= 0:
                break
            text = chunk.text[:available]
            if not text:
                break
            selected.append(f"{prefix}{text}")
            references.add(chunk.source_reference)
            remaining -= len(separator) + len(prefix) + len(text)
        return "\n\n".join(selected), references

    def _get_or_create_owner(self) -> User:
        owner = self.user_repository.get_by_email(self.settings.legacy_bootstrap_user)
        if owner is not None:
            return owner
        return self.user_repository.add(
            User(
                email=self.settings.legacy_bootstrap_user,
                display_name=self.settings.legacy_bootstrap_user_display_name,
                is_active=True,
            )
        )

    def _require_material(self, material_id: int) -> Material:
        owner = self._get_or_create_owner()
        material = self.material_repository.get_for_owner(material_id, owner.id)
        if material is None:
            raise ResourceNotFoundError("Material")
        return material


def get_material_ai_service(
    session: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> MaterialAIService:
    return MaterialAIService(
        session=session,
        material_repository=MaterialRepository(session),
        content_repository=MaterialContentRepository(session),
        summary_repository=MaterialSummaryRepository(session),
        card_repository=StudyCardRepository(session),
        user_repository=UserRepository(session),
        settings=settings,
    )


def serialize_summary(summary: MaterialSummary | None, material_id: int) -> dict[str, object]:
    if summary is None:
        return {
            "id": material_id,
            "material_id": material_id,
            "summary": None,
            "ai_summary": None,
            "summary_generated": False,
            "summary_method": None,
            "summary_updated_at": None,
        }
    return {
        "id": material_id,
        "material_id": material_id,
        "summary": {
            "overview": summary.overview,
            "key_concepts": summary.key_concepts,
            "important_points": summary.important_points,
            "common_mistakes": summary.common_mistakes,
            "review_suggestions": summary.review_suggestions,
            "provider": summary.model_provider,
            "model": summary.model_name,
            "prompt_version": summary.prompt_version,
            "generated_at": summary.created_at,
            "updated_at": summary.updated_at,
        },
        "ai_summary": summary.overview,
        "summary_generated": True,
        "summary_method": summary.model_provider,
        "summary_updated_at": summary.updated_at,
    }
