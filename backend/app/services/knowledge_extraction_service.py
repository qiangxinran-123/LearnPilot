from __future__ import annotations

import logging
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.ai import AIServiceError, LLMClient, get_llm_client
from backend.app.ai.chunking import chunk_segments
from backend.app.ai.models import KnowledgeCandidateDraft, KnowledgeExtractionOutput
from backend.app.ai.prompts import knowledge_extraction as extraction_prompt
from backend.app.ai.references import resolve_source_reference
from backend.app.core.settings import Settings, get_settings
from backend.app.db.models import (
    KnowledgeCandidate,
    KnowledgeCandidateSource,
    KnowledgeExtractionRun,
    Material,
    User,
)
from backend.app.db.session import get_db
from backend.app.models import KnowledgeExtractionStatus, normalize_knowledge_name
from backend.app.repositories import (
    CourseRepository,
    KnowledgeCandidateRepository,
    KnowledgeCandidateSourceRepository,
    KnowledgeExtractionRunRepository,
    MaterialContentRepository,
    MaterialRepository,
    UserRepository,
)
from backend.app.services.course_service import ResourceNotFoundError

logger = logging.getLogger(__name__)


class KnowledgeExtractionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class ReadyExtractionMaterial:
    course_id: int
    material_id: int
    material_content_hash: str
    plain_text: str
    segments: list[dict[str, object]]


@dataclass(frozen=True)
class ExtractionBatch:
    context: str
    evidence_by_reference: dict[str, str]


@dataclass(frozen=True)
class ValidatedCandidate:
    draft: KnowledgeCandidateDraft
    evidence_by_reference: dict[str, str]


@dataclass
class CandidateAggregate:
    draft: KnowledgeCandidateDraft
    normalized_name: str
    evidence_by_reference: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class KnowledgeExtractionResult:
    run: KnowledgeExtractionRun
    candidates: list[KnowledgeCandidate]
    reused: bool


class KnowledgeExtractionService:
    def __init__(
        self,
        session: Session,
        course_repository: CourseRepository,
        material_repository: MaterialRepository,
        content_repository: MaterialContentRepository,
        run_repository: KnowledgeExtractionRunRepository,
        candidate_repository: KnowledgeCandidateRepository,
        source_repository: KnowledgeCandidateSourceRepository,
        user_repository: UserRepository,
        settings: Settings,
        llm_client_factory: Callable[[Settings], LLMClient] = get_llm_client,
    ) -> None:
        self.session = session
        self.course_repository = course_repository
        self.material_repository = material_repository
        self.content_repository = content_repository
        self.run_repository = run_repository
        self.candidate_repository = candidate_repository
        self.source_repository = source_repository
        self.user_repository = user_repository
        self.settings = settings
        self.llm_client_factory = llm_client_factory

    def get_extraction(self, course_id: int, material_id: int) -> KnowledgeExtractionResult:
        with self.session.begin():
            owner = self._get_or_create_owner()
            self._require_course(course_id, owner.id)
            self._require_material_for_course(course_id, material_id)
            run = self.run_repository.get_current_for_material(material_id)
            content = self.content_repository.get_for_material(material_id)
            if run is not None and (content is None or run.material_content_hash != content.content_hash):
                run = None
            if run is None:
                run = self.run_repository.get_latest_for_material(material_id)
                if run is not None and (content is None or run.material_content_hash != content.content_hash):
                    run = None
            if run is None:
                raise KnowledgeExtractionError(
                    "KNOWLEDGE_EXTRACTION_NOT_READY",
                    "Knowledge extraction has not been run for this material.",
                )
            candidates = (
                self.candidate_repository.list_for_run(run.id)
                if run.status == KnowledgeExtractionStatus.SUCCESS
                else []
            )
            return KnowledgeExtractionResult(run=run, candidates=candidates, reused=True)

    def extract(
        self,
        course_id: int,
        material_id: int,
        *,
        regenerate: bool = False,
    ) -> KnowledgeExtractionResult:
        ready = self._load_ready_material(course_id, material_id)
        try:
            client = self.llm_client_factory(self.settings)
        except AIServiceError as error:
            raise self._map_ai_error(error) from error
        provider, model = self._client_identity(client)

        with self.session.begin():
            if not regenerate:
                current = self.run_repository.find_current_by_key(
                    ready.material_id,
                    ready.material_content_hash,
                    extraction_prompt.PROMPT_VERSION,
                    model,
                )
                if current is not None:
                    return KnowledgeExtractionResult(
                        run=current,
                        candidates=self.candidate_repository.list_for_run(current.id),
                        reused=True,
                    )
            run = self.run_repository.create(
                KnowledgeExtractionRun(
                    course_id=ready.course_id,
                    material_id=ready.material_id,
                    material_content_hash=ready.material_content_hash,
                    status=KnowledgeExtractionStatus.RUNNING,
                    provider=provider,
                    model=model,
                    prompt_version=extraction_prompt.PROMPT_VERSION,
                    candidate_count=0,
                    is_current=False,
                )
            )
            run_id = run.id

        try:
            aggregates = self._extract_candidates(client, ready)
            with self.session.begin():
                self._require_unchanged_content(ready)
                run = self.run_repository.get_by_id(run_id)
                if run is None:
                    raise KnowledgeExtractionError(
                        "KNOWLEDGE_EXTRACTION_FAILED",
                        "Knowledge extraction run no longer exists.",
                    )
                candidates = self._persist_candidates(run, aggregates)
                self.run_repository.clear_current(material_id)
                run.status = KnowledgeExtractionStatus.SUCCESS
                run.candidate_count = len(candidates)
                run.error_code = None
                run.error_message = None
                run.is_current = True
                run.completed_at = datetime.now(timezone.utc)
                self.run_repository.save(run)
                return KnowledgeExtractionResult(
                    run=run,
                    candidates=self.candidate_repository.list_for_run(run.id),
                    reused=False,
                )
        except KnowledgeExtractionError as error:
            self._mark_failed(run_id, error.code, error.message)
            raise
        except AIServiceError as error:
            mapped = self._map_ai_error(error)
            self._mark_failed(run_id, mapped.code, mapped.message)
            raise mapped from error
        except Exception as error:
            logger.exception("knowledge_extraction_failed run_id=%s", run_id)
            mapped = KnowledgeExtractionError(
                "KNOWLEDGE_EXTRACTION_FAILED",
                "Knowledge extraction failed before a valid candidate set could be saved.",
            )
            self._mark_failed(run_id, mapped.code, mapped.message)
            raise mapped from error

    def _load_ready_material(self, course_id: int, material_id: int) -> ReadyExtractionMaterial:
        with self.session.begin():
            owner = self._get_or_create_owner()
            self._require_course(course_id, owner.id)
            material = self._require_material_for_course(course_id, material_id)
            content = self.content_repository.get_for_material(material.id)
            if (
                content is None
                or material.extraction_status not in {"SUCCESS", "EXTRACTED"}
                or not content.plain_text.strip()
            ):
                raise KnowledgeExtractionError(
                    "KNOWLEDGE_EXTRACTION_NOT_READY",
                    "Material must have non-empty successfully parsed content before knowledge extraction.",
                )
            if len(content.plain_text) > self.settings.knowledge_extraction_max_input_chars:
                raise KnowledgeExtractionError(
                    "KNOWLEDGE_EXTRACTION_NOT_READY",
                    "Material exceeds the configured knowledge extraction input limit.",
                )
            return ReadyExtractionMaterial(
                course_id=course_id,
                material_id=material.id,
                material_content_hash=content.content_hash,
                plain_text=content.plain_text,
                segments=content.segments,
            )

    def _extract_candidates(
        self,
        client: LLMClient,
        ready: ReadyExtractionMaterial,
    ) -> list[CandidateAggregate]:
        aggregates: OrderedDict[str, CandidateAggregate] = OrderedDict()
        for batch in self._build_batches(ready):
            for validated in self._extract_batch(client, batch):
                normalized_name = normalize_knowledge_name(validated.draft.name)
                existing = aggregates.get(normalized_name)
                if existing is None:
                    existing = CandidateAggregate(
                        draft=validated.draft,
                        normalized_name=normalized_name,
                    )
                    aggregates[normalized_name] = existing
                for reference, excerpt in validated.evidence_by_reference.items():
                    existing.evidence_by_reference.setdefault(reference, excerpt)
                if len(aggregates) > self.settings.knowledge_extraction_max_candidates:
                    raise KnowledgeExtractionError(
                        "KNOWLEDGE_EXTRACTION_INVALID_OUTPUT",
                        "Knowledge extraction exceeded the configured candidate limit.",
                    )
        return list(aggregates.values())

    def _extract_batch(self, client: LLMClient, batch: ExtractionBatch) -> list[ValidatedCandidate]:
        messages = extraction_prompt.messages(batch.context)
        last_error: KnowledgeExtractionError | None = None
        for attempt in range(self.settings.llm_max_attempts):
            output = client.generate_structured(
                operation="knowledge_extraction",
                messages=messages,
                schema=KnowledgeExtractionOutput,
            )
            data = output.data
            if not isinstance(data, KnowledgeExtractionOutput):
                raise KnowledgeExtractionError(
                    "KNOWLEDGE_EXTRACTION_INVALID_OUTPUT",
                    "AI returned an invalid knowledge extraction structure.",
                )
            try:
                return self._validate_batch_candidates(data, batch)
            except KnowledgeExtractionError as error:
                last_error = error
                if error.code != "KNOWLEDGE_EXTRACTION_INVALID_REFERENCE":
                    raise
                if attempt + 1 >= self.settings.llm_max_attempts:
                    break
                allowed = ", ".join(sorted(batch.evidence_by_reference))
                messages = extraction_prompt.messages(batch.context)
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "上一次结果含无效来源。请重新输出完整 JSON，且 source_references "
                            f"只能使用这些标签：{allowed}"
                        ),
                    }
                )
        if last_error is None:
            raise KnowledgeExtractionError(
                "KNOWLEDGE_EXTRACTION_INVALID_OUTPUT",
                "AI did not return a valid candidate set.",
            )
        raise last_error

    @staticmethod
    def _validate_batch_candidates(
        data: KnowledgeExtractionOutput,
        batch: ExtractionBatch,
    ) -> list[ValidatedCandidate]:
        allowed_references = set(batch.evidence_by_reference)
        validated: list[ValidatedCandidate] = []
        for draft in data.candidates:
            resolved = list(
                dict.fromkeys(
                    resolve_source_reference(reference, allowed_references) for reference in draft.source_references
                )
            )
            if not resolved or any(reference not in allowed_references for reference in resolved):
                raise KnowledgeExtractionError(
                    "KNOWLEDGE_EXTRACTION_INVALID_REFERENCE",
                    "AI returned a source reference that was not present in the supplied material context.",
                )
            validated.append(
                ValidatedCandidate(
                    draft=draft,
                    evidence_by_reference={
                        reference: batch.evidence_by_reference[reference]
                        for reference in resolved
                        if reference is not None
                    },
                )
            )
        return validated

    def _build_batches(self, ready: ReadyExtractionMaterial) -> list[ExtractionBatch]:
        max_reference_chars = 255
        effective_chunk_chars = min(
            self.settings.llm_chunk_chars,
            self.settings.llm_context_chars - max_reference_chars - 3,
        )
        chunks = chunk_segments(
            ready.segments,
            max_chars=effective_chunk_chars,
            overlap_chars=min(self.settings.llm_chunk_overlap_chars, effective_chunk_chars - 1),
        )
        if not chunks:
            chunks = chunk_segments(
                [{"text": ready.plain_text, "source_reference": "资料内容"}],
                max_chars=effective_chunk_chars,
                overlap_chars=min(self.settings.llm_chunk_overlap_chars, effective_chunk_chars - 1),
            )
        if not chunks:
            raise KnowledgeExtractionError(
                "KNOWLEDGE_EXTRACTION_NOT_READY",
                "Material has no extractable text chunks.",
            )

        batches: list[ExtractionBatch] = []
        pieces: list[str] = []
        evidence_by_reference: dict[str, str] = {}
        context_chars = 0
        for chunk in chunks:
            reference = chunk.source_reference.strip()
            if not reference or len(reference) > max_reference_chars:
                raise KnowledgeExtractionError(
                    "KNOWLEDGE_EXTRACTION_NOT_READY",
                    "Material contains an invalid source reference.",
                )
            piece = f"[{reference}]\n{chunk.text}"
            separator_chars = 2 if pieces else 0
            if pieces and context_chars + separator_chars + len(piece) > self.settings.llm_context_chars:
                batches.append(ExtractionBatch("\n\n".join(pieces), evidence_by_reference))
                pieces = []
                evidence_by_reference = {}
                context_chars = 0
                separator_chars = 0
            if len(piece) > self.settings.llm_context_chars:
                raise KnowledgeExtractionError(
                    "KNOWLEDGE_EXTRACTION_NOT_READY",
                    "A material chunk exceeds the configured LLM context limit.",
                )
            pieces.append(piece)
            context_chars += separator_chars + len(piece)
            existing = evidence_by_reference.get(reference)
            combined = chunk.text if existing is None else f"{existing}\n{chunk.text}"
            evidence_by_reference[reference] = combined[:1000]
        if pieces:
            batches.append(ExtractionBatch("\n\n".join(pieces), evidence_by_reference))
        return batches

    def _persist_candidates(
        self,
        run: KnowledgeExtractionRun,
        aggregates: list[CandidateAggregate],
    ) -> list[KnowledgeCandidate]:
        candidates: list[KnowledgeCandidate] = []
        for aggregate in aggregates:
            candidate = self.candidate_repository.create(
                KnowledgeCandidate(
                    extraction_run_id=run.id,
                    course_id=run.course_id,
                    material_id=run.material_id,
                    name=aggregate.draft.name,
                    normalized_name=aggregate.normalized_name,
                    description=aggregate.draft.description,
                    importance=aggregate.draft.importance,
                    difficulty=aggregate.draft.difficulty,
                )
            )
            for reference, excerpt in aggregate.evidence_by_reference.items():
                self.source_repository.create(
                    KnowledgeCandidateSource(
                        candidate_id=candidate.id,
                        material_id=run.material_id,
                        source_reference=reference,
                        excerpt=excerpt,
                    )
                )
            candidates.append(candidate)
        return candidates

    def _require_unchanged_content(self, ready: ReadyExtractionMaterial) -> None:
        owner = self._get_or_create_owner()
        self._require_course(ready.course_id, owner.id)
        material = self._require_material_for_course(ready.course_id, ready.material_id)
        content = self.content_repository.get_for_material(material.id)
        if (
            content is None
            or material.extraction_status not in {"SUCCESS", "EXTRACTED"}
            or content.content_hash != ready.material_content_hash
        ):
            raise KnowledgeExtractionError(
                "KNOWLEDGE_EXTRACTION_NOT_READY",
                "Material content changed during knowledge extraction; no candidates were saved.",
            )

    def _mark_failed(self, run_id: int, code: str, message: str) -> None:
        with self.session.begin():
            run = self.run_repository.get_by_id(run_id)
            if run is None:
                return
            run.status = KnowledgeExtractionStatus.FAILED
            run.candidate_count = 0
            run.error_code = code[:64]
            run.error_message = message[:255]
            run.is_current = False
            run.completed_at = datetime.now(timezone.utc)
            self.run_repository.save(run)

    @staticmethod
    def _map_ai_error(error: AIServiceError) -> KnowledgeExtractionError:
        if error.code == "AI_INVALID_OUTPUT":
            return KnowledgeExtractionError(
                "KNOWLEDGE_EXTRACTION_INVALID_OUTPUT",
                "AI returned output that did not match the required knowledge candidate schema.",
            )
        return KnowledgeExtractionError(
            "KNOWLEDGE_EXTRACTION_FAILED",
            "The AI provider could not complete knowledge extraction.",
        )

    @staticmethod
    def _client_identity(client: LLMClient) -> tuple[str, str]:
        provider = str(getattr(client, "provider", "")).strip()
        model = str(getattr(client, "model", "")).strip()
        if not provider or not model:
            raise KnowledgeExtractionError(
                "KNOWLEDGE_EXTRACTION_FAILED",
                "The configured AI provider did not expose traceable provider and model identifiers.",
            )
        return provider[:80], model[:160]

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

    def _require_course(self, course_id: int, owner_id: int) -> None:
        if self.course_repository.get_for_owner(course_id, owner_id) is None:
            raise ResourceNotFoundError("Course")

    def _require_material_for_course(self, course_id: int, material_id: int) -> Material:
        material = self.material_repository.get_by_id(material_id)
        if material is None or material.course_id != course_id:
            raise ResourceNotFoundError("Material")
        return material


def get_knowledge_extraction_service(
    session: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> KnowledgeExtractionService:
    return KnowledgeExtractionService(
        session=session,
        course_repository=CourseRepository(session),
        material_repository=MaterialRepository(session),
        content_repository=MaterialContentRepository(session),
        run_repository=KnowledgeExtractionRunRepository(session),
        candidate_repository=KnowledgeCandidateRepository(session),
        source_repository=KnowledgeCandidateSourceRepository(session),
        user_repository=UserRepository(session),
        settings=settings,
    )


__all__ = [
    "KnowledgeExtractionError",
    "KnowledgeExtractionResult",
    "KnowledgeExtractionService",
    "get_knowledge_extraction_service",
]
