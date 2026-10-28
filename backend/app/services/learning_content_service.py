from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends
from sqlalchemy.orm import Session

from backend.app.ai.chunking import TextChunk, chunk_segments, relevant_chunks
from backend.app.core.settings import Settings, get_settings
from backend.app.db.models import Material, MaterialContent
from backend.app.db.session import get_db
from backend.app.models import LearningSessionTaskPhase
from backend.app.repositories import CourseRepository, LearningSessionRepository, UserRepository
from backend.app.repositories.learning_content_repository import LearningContentRepository
from backend.app.schemas.learning_content import (
    LearningContentLimits,
    LearningContentRead,
    LearningContentRelevance,
    LearningContentSegmentRead,
    LearningContentStatus,
)

MAX_SEGMENTS = 6
MAX_SEGMENTS_PER_MATERIAL = 2
MAX_TOTAL_CONTEXT_CHARS = 8_000
SOURCE_CONTEXT_RATIO = 0.55


class LearningContentError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class _Candidate:
    material: Material
    content: MaterialContent
    segment_index: int
    fragment_index: int
    chunk: TextChunk
    original_text_length: int
    relevance: LearningContentRelevance


class LearningContentService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.sessions = LearningSessionRepository(session)
        self.users = UserRepository(session)
        self.courses = CourseRepository(session)
        self.contents = LearningContentRepository(session)

    def get_for_configured_user(
        self,
        *,
        session_id: int,
        phase: LearningSessionTaskPhase,
        query: str | None = None,
    ) -> LearningContentRead:
        if phase == LearningSessionTaskPhase.ADAPTIVE_PRACTICE:
            raise LearningContentError(
                "CONTENT_PHASE_NOT_AVAILABLE",
                "Adaptive practice content becomes available in M7-4.",
            )

        with self.session.begin():
            owner = self.users.get_by_email(self.settings.legacy_bootstrap_user)
            if owner is None:
                raise LearningContentError("USER_NOT_FOUND", "User not found.")
            learning_session = self.sessions.get_owned(session_id=session_id, user_id=owner.id)
            if learning_session is None:
                raise LearningContentError("SESSION_NOT_FOUND", "Learning session not found.")
            if self.courses.get_for_owner(learning_session.course_id, owner.id) is None:
                raise LearningContentError("SESSION_NOT_FOUND", "Learning session not found.")
            node = learning_session.target_knowledge_node
            if node.course_id != learning_session.course_id:
                raise LearningContentError(
                    "SESSION_SCOPE_INVALID",
                    "The learning session target is outside its course.",
                )

            max_segment_chars = self.settings.llm_chunk_chars
            max_total_chars = min(
                int(self.settings.llm_context_chars * SOURCE_CONTEXT_RATIO),
                MAX_TOTAL_CONTEXT_CHARS,
            )
            direct = self._direct_candidates(
                course_id=learning_session.course_id,
                knowledge_node_id=node.id,
                max_segment_chars=max_segment_chars,
            )
            selected = self._select(direct, max_total_chars=max_total_chars)
            if len(selected) < MAX_SEGMENTS:
                fallback_query = " ".join(
                    part.strip() for part in (node.name, node.description, query or "") if part and part.strip()
                )
                supplemental = self._supplemental_candidates(
                    course_id=learning_session.course_id,
                    query=fallback_query,
                    max_segment_chars=max_segment_chars,
                )
                selected = self._select(
                    [*selected, *supplemental],
                    max_total_chars=max_total_chars,
                )

            response_segments = self._read_segments(selected, max_total_chars=max_total_chars)
            return LearningContentRead(
                session_id=learning_session.id,
                course_id=learning_session.course_id,
                knowledge_node_id=node.id,
                knowledge_node_name=node.name,
                knowledge_node_description=node.description,
                phase=phase,
                status=(LearningContentStatus.READY if response_segments else LearningContentStatus.EMPTY),
                grounded=any(item.relevance == LearningContentRelevance.DIRECT for item in selected),
                segments=response_segments,
                limits=LearningContentLimits(
                    max_segments=MAX_SEGMENTS,
                    max_segment_chars=max_segment_chars,
                    max_total_chars=max_total_chars,
                    max_segments_per_material=MAX_SEGMENTS_PER_MATERIAL,
                ),
            )

    def _direct_candidates(self, *, course_id: int, knowledge_node_id: int, max_segment_chars: int) -> list[_Candidate]:
        candidates: list[_Candidate] = []
        for source, material, content in self.contents.list_direct_sources(
            course_id=course_id,
            knowledge_node_id=knowledge_node_id,
        ):
            if not isinstance(content.segments, list):
                continue
            matched = next(
                (
                    (index, segment)
                    for index, segment in enumerate(content.segments)
                    if isinstance(segment, dict)
                    and segment.get("source_reference") == source.source_reference
                    and isinstance(segment.get("text"), str)
                    and segment["text"].strip()
                ),
                None,
            )
            if matched is None:
                continue
            segment_index, segment = matched
            original_text = str(segment["text"]).strip()
            chunks = chunk_segments(
                [segment],
                max_chars=max_segment_chars,
                overlap_chars=self.settings.llm_chunk_overlap_chars,
            )
            candidates.extend(
                _Candidate(
                    material=material,
                    content=content,
                    segment_index=segment_index,
                    fragment_index=fragment_index,
                    chunk=chunk,
                    original_text_length=len(original_text),
                    relevance=LearningContentRelevance.DIRECT,
                )
                for fragment_index, chunk in enumerate(chunks)
            )
        return candidates

    def _supplemental_candidates(self, *, course_id: int, query: str, max_segment_chars: int) -> list[_Candidate]:
        candidates: list[_Candidate] = []
        for material, content in self.contents.list_course_contents(course_id=course_id):
            if not isinstance(content.segments, list):
                continue
            for segment_index, segment in enumerate(content.segments):
                if not isinstance(segment, dict):
                    continue
                text = segment.get("text")
                reference = segment.get("source_reference")
                if (
                    not isinstance(text, str)
                    or not text.strip()
                    or not isinstance(reference, str)
                    or not reference.strip()
                ):
                    continue
                chunks = chunk_segments(
                    [segment],
                    max_chars=max_segment_chars,
                    overlap_chars=self.settings.llm_chunk_overlap_chars,
                )
                candidates.extend(
                    _Candidate(
                        material=material,
                        content=content,
                        segment_index=segment_index,
                        fragment_index=fragment_index,
                        chunk=chunk,
                        original_text_length=len(text.strip()),
                        relevance=LearningContentRelevance.SUPPLEMENTAL,
                    )
                    for fragment_index, chunk in enumerate(chunks)
                )

        chunks = [candidate.chunk for candidate in candidates]
        ranked = relevant_chunks(query, chunks, limit=len(chunks))
        by_identity = {id(candidate.chunk): candidate for candidate in candidates}
        return [by_identity[id(chunk)] for chunk in ranked]

    @staticmethod
    def _select(candidates: list[_Candidate], *, max_total_chars: int) -> list[_Candidate]:
        selected: list[_Candidate] = []
        seen: set[tuple[int, str, str]] = set()
        per_material: dict[int, int] = {}
        total_chars = 0
        for candidate in candidates:
            key = (candidate.material.id, candidate.chunk.source_reference, candidate.chunk.text)
            if key in seen or per_material.get(candidate.material.id, 0) >= MAX_SEGMENTS_PER_MATERIAL:
                continue
            if total_chars >= max_total_chars or len(selected) >= MAX_SEGMENTS:
                break
            selected.append(candidate)
            seen.add(key)
            per_material[candidate.material.id] = per_material.get(candidate.material.id, 0) + 1
            total_chars += min(len(candidate.chunk.text), max_total_chars - total_chars)
        return selected

    @staticmethod
    def _read_segments(candidates: list[_Candidate], *, max_total_chars: int) -> list[LearningContentSegmentRead]:
        result: list[LearningContentSegmentRead] = []
        remaining = max_total_chars
        for candidate in candidates:
            if remaining <= 0:
                break
            text = candidate.chunk.text[:remaining]
            if not text:
                continue
            result.append(
                LearningContentSegmentRead(
                    material_id=candidate.material.id,
                    material_title=candidate.material.title,
                    material_type=candidate.material.extension or candidate.material.material_type,
                    segment_index=candidate.segment_index,
                    fragment_index=candidate.fragment_index,
                    text=text,
                    source_reference=candidate.chunk.source_reference,
                    relevance=candidate.relevance,
                    content_hash=candidate.content.content_hash,
                    text_truncated=(
                        candidate.original_text_length > len(candidate.chunk.text)
                        or len(text) < len(candidate.chunk.text)
                    ),
                )
            )
            remaining -= len(text)
        return result


def get_learning_content_service(
    session: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> LearningContentService:
    return LearningContentService(session, settings)


__all__ = [
    "LearningContentError",
    "LearningContentService",
    "get_learning_content_service",
]
