from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.ai import AIServiceError, LLMClient, get_llm_client
from backend.app.ai.models import DiagnosticQuestionDraft, DiagnosticQuestionGenerationOutput
from backend.app.ai.prompts import diagnostic_questions as question_prompt
from backend.app.ai.references import normalize_source_reference, resolve_source_reference
from backend.app.core.settings import Settings
from backend.app.db.models import (
    CourseKnowledgeBuildState,
    KnowledgeNode,
    KnowledgeSource,
    Material,
    MaterialContent,
    Question,
    QuestionKnowledgeNode,
)
from backend.app.models import KnowledgeRelationRole, QuestionValidationStatus
from backend.app.repositories import CourseRepository, QuestionRepository
from backend.app.schemas.diagnostic import (
    QuestionContentSchema,
    QuestionKnowledgeBindingSchema,
    QuestionOptionSchema,
    QuestionSourceRefSchema,
)
from backend.app.schemas.question_generation import QuestionGenerationRequestSchema
from backend.app.services.diagnostic_question_quality import DiagnosticQuestionQualityValidator

logger = logging.getLogger(__name__)


class DiagnosticQuestionGenerationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class VerifiedSourceContext:
    material_id: int
    material_title: str
    source_reference: str
    excerpt: str


@dataclass(frozen=True)
class ReadyQuestionContext:
    node_id: int
    node_name: str
    node_description: str
    sources: tuple[VerifiedSourceContext, ...]
    rendered_context: str
    course_stems: tuple[str, ...]
    primary_node_stems: tuple[str, ...]


@dataclass(frozen=True)
class GeneratedQuestionBatch:
    questions: tuple[Question, ...]
    provider: str
    model: str
    prompt_version: str
    requested_count: int
    accepted_count: int
    rejected_count: int


class DiagnosticQuestionGenerationService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        llm_client_factory: Callable[[Settings], LLMClient] = get_llm_client,
    ) -> None:
        self.session = session
        self.settings = settings
        self.llm_client_factory = llm_client_factory
        self.courses = CourseRepository(session)
        self.questions = QuestionRepository(session)
        self.quality = DiagnosticQuestionQualityValidator(settings.diagnostic_question_similarity_threshold)

    def generate_questions_for_node(
        self,
        *,
        owner_id: int,
        course_id: int,
        knowledge_node_id: int,
        question_type: object,
        difficulty: object,
        count: int,
    ) -> GeneratedQuestionBatch:
        started = time.monotonic()
        try:
            request = self._validate_request(course_id, knowledge_node_id, question_type, difficulty, count)
            ready = self._load_ready_context(owner_id, request)
        except DiagnosticQuestionGenerationError as error:
            self._log_failure(course_id, knowledge_node_id, question_type, difficulty, count, error.code, started)
            raise
        try:
            client = self.llm_client_factory(self.settings)
        except AIServiceError as error:
            mapped = self._map_ai_error(error)
            self._log_failure(course_id, knowledge_node_id, question_type, difficulty, count, mapped.code, started)
            raise mapped from error

        messages = question_prompt.messages(
            node_id=ready.node_id,
            node_name=ready.node_name,
            node_description=ready.node_description,
            question_type=request.question_type,
            difficulty=request.difficulty,
            count=request.count,
            context=ready.rendered_context,
        )
        last_error: DiagnosticQuestionGenerationError | None = None
        for attempt in range(self.settings.llm_max_attempts):
            try:
                generated = client.generate_structured(
                    operation="diagnostic_question_generation",
                    messages=messages,
                    schema=DiagnosticQuestionGenerationOutput,
                )
                output = DiagnosticQuestionGenerationOutput.model_validate(generated.data)
                contents = self._validate_candidates(request, ready, output.questions)
                result = self._persist(owner_id, request, ready, contents, generated.provider, generated.model)
                logger.info(
                    "diagnostic_question_generation operation=generate course_id=%s knowledge_node_id=%s "
                    "question_type=%s difficulty=%s requested_count=%s accepted_count=%s rejected_count=0 "
                    "provider=%s model=%s prompt_version=%s latency_ms=%s",
                    course_id,
                    knowledge_node_id,
                    request.question_type.value,
                    request.difficulty.value,
                    request.count,
                    len(result),
                    generated.provider,
                    generated.model,
                    question_prompt.PROMPT_VERSION,
                    int((time.monotonic() - started) * 1000),
                )
                return GeneratedQuestionBatch(
                    questions=tuple(result),
                    provider=generated.provider,
                    model=generated.model,
                    prompt_version=question_prompt.PROMPT_VERSION,
                    requested_count=request.count,
                    accepted_count=len(result),
                    rejected_count=0,
                )
            except AIServiceError as error:
                mapped = self._map_ai_error(error)
                if not error.retryable or attempt + 1 >= self.settings.llm_max_attempts:
                    self._log_failure(
                        course_id, knowledge_node_id, question_type, difficulty, count, mapped.code, started
                    )
                    raise mapped from error
                last_error = mapped
            except DiagnosticQuestionGenerationError as error:
                last_error = error
                if (
                    error.code
                    not in {
                        "QUESTION_INVALID_OUTPUT",
                        "QUESTION_SOURCE_INVALID",
                        "QUESTION_ALIGNMENT_INVALID",
                        "QUESTION_QUALITY_INVALID",
                        "QUESTION_DUPLICATE",
                    }
                    or attempt + 1 >= self.settings.llm_max_attempts
                ):
                    self._log_failure(
                        course_id, knowledge_node_id, question_type, difficulty, count, error.code, started
                    )
                    raise
            except Exception as error:
                logger.exception(
                    "diagnostic_question_generation_failed course_id=%s knowledge_node_id=%s",
                    course_id,
                    knowledge_node_id,
                )
                mapped = DiagnosticQuestionGenerationError(
                    "QUESTION_GENERATION_FAILED", "Question generation failed before a valid batch could be saved."
                )
                self._log_failure(course_id, knowledge_node_id, question_type, difficulty, count, mapped.code, started)
                raise mapped from error
        assert last_error is not None
        raise last_error

    def _validate_request(
        self,
        course_id: int,
        knowledge_node_id: int,
        question_type: object,
        difficulty: object,
        count: int,
    ) -> QuestionGenerationRequestSchema:
        try:
            request = QuestionGenerationRequestSchema.model_validate(
                {
                    "course_id": course_id,
                    "knowledge_node_id": knowledge_node_id,
                    "question_type": question_type,
                    "difficulty": difficulty,
                    "count": count,
                }
            )
        except ValidationError as error:
            raise DiagnosticQuestionGenerationError(
                "QUESTION_GENERATION_REQUEST_INVALID", "Question generation request is invalid."
            ) from error
        if request.count > self.settings.diagnostic_question_max_count:
            raise DiagnosticQuestionGenerationError(
                "QUESTION_GENERATION_REQUEST_INVALID",
                f"At most {self.settings.diagnostic_question_max_count} questions may be requested at once.",
            )
        return request

    def _load_ready_context(self, owner_id: int, request: QuestionGenerationRequestSchema) -> ReadyQuestionContext:
        with self.session.begin():
            if self.courses.get_by_id(request.course_id) is None:
                raise DiagnosticQuestionGenerationError("COURSE_NOT_FOUND", "Course was not found.")
            if self.courses.get_for_owner(request.course_id, owner_id) is None:
                raise DiagnosticQuestionGenerationError("COURSE_NOT_FOUND", "Course was not found.")
            node = self.session.scalar(
                select(KnowledgeNode).where(
                    KnowledgeNode.id == request.knowledge_node_id,
                    KnowledgeNode.course_id == request.course_id,
                )
            )
            if node is None:
                raise DiagnosticQuestionGenerationError(
                    "KNOWLEDGE_NODE_NOT_FOUND", "Knowledge node was not found in this course."
                )
            state = self.session.get(CourseKnowledgeBuildState, request.course_id)
            if not node.is_active or state is None or state.status != "success":
                raise DiagnosticQuestionGenerationError(
                    "KNOWLEDGE_MODEL_NOT_READY", "The course knowledge model is not ready for question generation."
                )
            sources = self._verified_sources(node.id, request.course_id)
            if not sources:
                raise DiagnosticQuestionGenerationError(
                    "QUESTION_SOURCE_INSUFFICIENT", "The knowledge node has no verified parsed source context."
                )
            rendered, rendered_sources = self._render_context(sources)
            if not rendered:
                raise DiagnosticQuestionGenerationError(
                    "QUESTION_SOURCE_INSUFFICIENT", "The verified source context is empty."
                )
            course_stems = tuple(
                question.stem for question in self.questions.list_for_course_owner(request.course_id, owner_id)
            )
            primary_node_stems = tuple(
                question.stem for question in self.questions.list_for_primary_node(request.course_id, node.id)
            )
            return ReadyQuestionContext(
                node.id,
                node.name,
                node.description,
                tuple(rendered_sources),
                rendered,
                course_stems,
                primary_node_stems,
            )

    def _verified_sources(self, node_id: int, course_id: int) -> list[VerifiedSourceContext]:
        statement = (
            select(KnowledgeSource, Material, MaterialContent)
            .join(Material, Material.id == KnowledgeSource.material_id)
            .join(MaterialContent, MaterialContent.material_id == Material.id)
            .where(KnowledgeSource.knowledge_node_id == node_id, Material.course_id == course_id)
            .order_by(KnowledgeSource.id)
        )
        verified: list[VerifiedSourceContext] = []
        seen: set[tuple[int, str]] = set()
        for source, material, content in self.session.execute(statement):
            segment_map: dict[str, str] = {}
            for segment in content.segments:
                reference = segment.get("source_reference")
                text = segment.get("text")
                if isinstance(reference, str) and isinstance(text, str) and text.strip():
                    segment_map[normalize_source_reference(reference)] = text.strip()
            resolved = resolve_source_reference(source.source_reference, set(segment_map))
            if resolved is None or (material.id, resolved) in seen:
                continue
            excerpt = (source.excerpt or segment_map[resolved]).strip()
            if not excerpt:
                continue
            seen.add((material.id, resolved))
            verified.append(VerifiedSourceContext(material.id, material.title, resolved, excerpt[:1000]))
        return verified

    def _render_context(self, sources: list[VerifiedSourceContext]) -> tuple[str, list[VerifiedSourceContext]]:
        blocks: list[str] = []
        included: list[VerifiedSourceContext] = []
        used = 0
        for source in sources:
            header = f"[material_id={source.material_id}; source_reference={source.source_reference}]\n"
            remaining = self.settings.llm_context_chars - used - len(header)
            if remaining <= 0:
                break
            excerpt = source.excerpt[:remaining]
            if not excerpt:
                continue
            block = f"{header}{excerpt}"
            blocks.append(block)
            included.append(
                VerifiedSourceContext(
                    source.material_id,
                    source.material_title,
                    source.source_reference,
                    excerpt,
                )
            )
            used += len(block)
        return "\n\n".join(blocks), included

    def _validate_candidates(
        self,
        request: QuestionGenerationRequestSchema,
        ready: ReadyQuestionContext,
        drafts: list[DiagnosticQuestionDraft],
    ) -> list[QuestionContentSchema]:
        if len(drafts) != request.count:
            raise DiagnosticQuestionGenerationError(
                "QUESTION_INVALID_OUTPUT", "Provider returned a different number of questions than requested."
            )
        allowed: dict[tuple[int, str], VerifiedSourceContext] = {
            (source.material_id, source.source_reference): source for source in ready.sources
        }
        contents: list[QuestionContentSchema] = []
        accepted_stems: list[str] = []
        for draft in drafts:
            if draft.question_type != request.question_type or draft.difficulty != request.difficulty:
                raise DiagnosticQuestionGenerationError(
                    "QUESTION_INVALID_OUTPUT", "Generated question type or difficulty does not match the request."
                )
            if draft.knowledge_node_ids != [request.knowledge_node_id]:
                raise DiagnosticQuestionGenerationError(
                    "QUESTION_ALIGNMENT_INVALID", "Generated knowledge node references do not match the target node."
                )
            source_refs: list[QuestionSourceRefSchema] = []
            seen_source_refs: set[tuple[int, str]] = set()
            for source_ref in draft.source_refs:
                candidates = {reference for material_id, reference in allowed if material_id == source_ref.material_id}
                resolved = resolve_source_reference(source_ref.source_reference, candidates)
                source = allowed.get((source_ref.material_id, resolved or ""))
                if source is None:
                    raise DiagnosticQuestionGenerationError(
                        "QUESTION_SOURCE_INVALID", "Generated question cites a source outside the verified context."
                    )
                source_key = (source.material_id, source.source_reference)
                if source_key in seen_source_refs:
                    raise DiagnosticQuestionGenerationError(
                        "QUESTION_SOURCE_INVALID", "Generated question repeats the same source reference."
                    )
                seen_source_refs.add(source_key)
                source_refs.append(
                    QuestionSourceRefSchema(
                        material_id=source.material_id,
                        material_title=source.material_title,
                        source_reference=source.source_reference,
                        excerpt=source.excerpt,
                    )
                )
            try:
                self.quality.validate_basic_quality(draft)
                content = QuestionContentSchema(
                    question_type=draft.question_type,
                    stem=draft.stem,
                    options=[QuestionOptionSchema.model_validate(option.model_dump()) for option in draft.options],
                    correct_answer=draft.correct_answer,
                    explanation=draft.explanation,
                    difficulty=draft.difficulty,
                    source_refs=source_refs,
                )
            except (ValidationError, ValueError) as error:
                raise DiagnosticQuestionGenerationError(
                    "QUESTION_QUALITY_INVALID", "Generated question failed deterministic quality validation."
                ) from error
            duplicate = self.quality.detect_duplicate(
                stem=content.stem,
                course_stems=ready.course_stems,
                primary_node_stems=ready.primary_node_stems,
                accepted_stems=accepted_stems,
            )
            if duplicate.duplicate:
                raise DiagnosticQuestionGenerationError("QUESTION_DUPLICATE", duplicate.reason or "Duplicate question.")
            accepted_stems.append(content.stem)
            contents.append(content)
        return contents

    def _persist(
        self,
        owner_id: int,
        request: QuestionGenerationRequestSchema,
        ready: ReadyQuestionContext,
        contents: list[QuestionContentSchema],
        provider: str,
        model: str,
    ) -> list[Question]:
        generated_at = datetime.now(timezone.utc).isoformat()
        saved: list[Question] = []
        with self.session.begin():
            if self.courses.get_for_owner(request.course_id, owner_id) is None:
                raise DiagnosticQuestionGenerationError("COURSE_NOT_FOUND", "Course was not found.")
            node = self.session.scalar(
                select(KnowledgeNode).where(
                    KnowledgeNode.id == ready.node_id,
                    KnowledgeNode.course_id == request.course_id,
                    KnowledgeNode.is_active.is_(True),
                )
            )
            if node is None:
                raise DiagnosticQuestionGenerationError(
                    "QUESTION_ALIGNMENT_INVALID", "Target knowledge node changed before persistence."
                )
            current_sources = self._verified_sources(ready.node_id, request.course_id)
            current_by_key = {
                (source.material_id, source.source_reference): source.excerpt for source in current_sources
            }
            if any(
                current_by_key.get((source.material_id, source.source_reference), "")[: len(source.excerpt)]
                != source.excerpt
                for source in ready.sources
            ):
                raise DiagnosticQuestionGenerationError(
                    "QUESTION_SOURCE_INVALID", "Verified source context changed before persistence."
                )
            for content in contents:
                question = self.questions.create(
                    Question(
                        course_id=request.course_id,
                        question_type=content.question_type,
                        stem=content.stem,
                        options=[option.model_dump(mode="json") for option in content.options],
                        correct_answer=list(content.correct_answer),
                        explanation=content.explanation,
                        difficulty=content.difficulty,
                        validation_status=QuestionValidationStatus.VALIDATED,
                        source_refs=[reference.model_dump(mode="json") for reference in content.source_refs],
                        generation_metadata={
                            "provider": provider,
                            "model": model,
                            "prompt_version": question_prompt.PROMPT_VERSION,
                            "generated_at": generated_at,
                            "target_knowledge_node_id": ready.node_id,
                            "validation": "automated",
                            "context_chars": len(ready.rendered_context),
                            "source_count": len(ready.sources),
                        },
                    )
                )
                binding = QuestionKnowledgeBindingSchema(
                    knowledge_node_id=ready.node_id,
                    relation_role=KnowledgeRelationRole.PRIMARY,
                )
                self.questions.add_knowledge_link(
                    QuestionKnowledgeNode(
                        question_id=question.id,
                        knowledge_node_id=binding.knowledge_node_id,
                        course_id=request.course_id,
                        relation_role=binding.relation_role,
                    )
                )
                saved.append(question)
        return saved

    @staticmethod
    def _map_ai_error(error: AIServiceError) -> DiagnosticQuestionGenerationError:
        if error.code == "AI_INVALID_OUTPUT":
            return DiagnosticQuestionGenerationError("QUESTION_INVALID_OUTPUT", error.message)
        supported = {
            "AI_NOT_CONFIGURED",
            "AI_TIMEOUT",
            "AI_RATE_LIMITED",
            "AI_AUTHENTICATION_FAILED",
            "AI_PROVIDER_ERROR",
        }
        code = error.code if error.code in supported else "QUESTION_GENERATION_FAILED"
        return DiagnosticQuestionGenerationError(code, error.message)

    @staticmethod
    def _log_failure(
        course_id: int,
        knowledge_node_id: int,
        question_type: object,
        difficulty: object,
        count: int,
        failure_category: str,
        started: float,
    ) -> None:
        logger.warning(
            "diagnostic_question_generation operation=generate course_id=%s knowledge_node_id=%s "
            "question_type=%s difficulty=%s requested_count=%s accepted_count=0 rejected_count=%s "
            "prompt_version=%s latency_ms=%s failure_category=%s",
            course_id,
            knowledge_node_id,
            getattr(question_type, "value", question_type),
            getattr(difficulty, "value", difficulty),
            count,
            max(count, 0),
            question_prompt.PROMPT_VERSION,
            int((time.monotonic() - started) * 1000),
            failure_category,
        )
